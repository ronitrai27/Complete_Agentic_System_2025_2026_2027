"""
Workflow Agent — uses Composio meta-tools to discover tool schemas,
then calls set_workflow() to build the input form for the user to fill and run.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings
from src.agents.composio_agent import create_user_session


# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Workflow Designer Agent.

Your job is to:
1. Help the user understand what workflow they want to build.
2. Use COMPOSIO_SEARCH_TOOLS to find the right tool actions for each step.
3. Use COMPOSIO_GET_TOOL_SCHEMAS to get the parameter names and types for each action.
4. Call set_workflow() with all the steps and their fields — so the user can fill in the form and click Run.

## STEP-BY-STEP PROCESS (follow this every time):

STEP 1: Use COMPOSIO_SEARCH_TOOLS to find the right tool action for each step.
  - Example: search "send email via gmail" to find GMAIL_SEND_EMAIL
  - Example: search "post message to slack channel" to find SLACK_SEND_MESSAGE
  
STEP 2: Use COMPOSIO_GET_TOOL_SCHEMAS to get the parameter list of each found action.
  - Pass the exact tool_slug you found in Step 1.

STEP 3: Call set_workflow() with the workflow name, description, and all steps.
  - Each step MUST include: tool_name, step_description, and fields.
  - fields MUST list ONLY the important/essential parameters required to run the action (e.g. 'recipient_email', 'subject', and 'body' for Gmail; 'channel' and 'markdown_text' for Slack).
  - EXCLUDE all highly technical, secondary optional fields (such as 'cc', 'bcc', 'attachment', 'unfurl_links', 'unfurl_media', 'reply_broadcast', 'thread_ts', 'extra_recipients', etc.) unless the user explicitly requested them in their message. This keeps the user form clean and simple.

## CRITICAL RULES:
- You are a DESIGNER only. You do NOT have tools to execute actions. If the user asks you to run, execute, or test the workflow in the chat, explain that you are a designer and instruct them to click the "Run Workflow" button in the right-side panel.
- To pass the output of a previous step to a subsequent step, use the placeholder `{{step_N}}` where N is the 1-based index of the step (e.g., `{{step_1}}` for the output of Step 1, or `{{step_1.some_key}}` for a nested key if known).
- For example, if Step 1 is `LINKEDIN_GET_MY_INFO` and Step 2 is `GMAIL_SEND_EMAIL`, you must pre-fill the `body` field of the Gmail step with a value like: "Here is my LinkedIn profile info: {{step_1}}"
- Always populate "value" in fields when you can infer it from the user's message (or when it references a previous step using `{{step_N}}`).
- Leave "value" as "" for fields the user must fill in (e.g. recipient email, API keys).
- After calling set_workflow, tell the user to review the fields on the right panel and click "Run Workflow".
"""


# ─── set_workflow custom tool ─────────────────────────────────────────────────

def make_set_workflow_tool(workflow_holder: dict):
    @tool
    def set_workflow(name: str, description: str, steps: list[dict]) -> str:
        """
        Build or update the visual workflow on the right-side panel.
        Call this AFTER using COMPOSIO_GET_TOOL_SCHEMAS to get exact param names.

        Args:
            name: Short workflow title shown to the user.
            description: One-sentence summary of what this workflow does.
            steps: List of step dicts. Each must have:
              - tool_name: Exact action slug (e.g. 'GMAIL_SEND_EMAIL', 'SLACK_SEND_MESSAGE')
              - step_description: Friendly explanation of this step
              - fields: List of parameter dicts. Each must have:
                  - name: Exact parameter name from COMPOSIO_GET_TOOL_SCHEMAS
                  - type: 'string', 'boolean', 'integer', or 'number'
                  - description: What this parameter does
                  - value: Pre-filled value if known from user's message, else empty string ""
        """
        workflow_holder["name"] = name
        workflow_holder["description"] = description
        workflow_holder["steps"] = steps

        try:
            st.session_state["workflow"] = {
                "name": name,
                "description": description,
                "steps": steps,
            }
        except Exception:
            pass

        field_count = sum(len(s.get("fields", [])) for s in steps)
        print(
            f"\n[set_workflow called] name='{name}' steps={len(steps)} total_fields={field_count}",
            flush=True,
        )
        return (
            f"Workflow '{name}' set with {len(steps)} steps and {field_count} parameters. "
            "The user can now fill in the fields on the right panel and click Run Workflow."
        )

    return set_workflow


# ─── Agent compile ────────────────────────────────────────────────────────────

def get_llm() -> ChatOpenAI:
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    return ChatOpenAI(model="gpt-4.1-mini", temperature=0.1, api_key=api_key)


def compile_workflow_agent(session, workflow_holder: dict):
    """
    Attach set_workflow to the real Composio session tools.
    The session already provides COMPOSIO_SEARCH_TOOLS and COMPOSIO_GET_TOOL_SCHEMAS
    which the agent will use to discover actions and fetch schemas before building the workflow.
    """
    # These are the Composio meta-tools: COMPOSIO_SEARCH_TOOLS, COMPOSIO_GET_TOOL_SCHEMAS, etc.
    composio_tools = list(session.tools())
    print(f"[compile_workflow_agent] Composio meta-tools loaded: {[t.name for t in composio_tools]}", flush=True)

    # Filter out execution tools so the designer cannot run them directly in chat
    allowed_tools = [t for t in composio_tools if t.name != "COMPOSIO_MULTI_EXECUTE_TOOL"]

    # Add our custom set_workflow tool
    set_wf = make_set_workflow_tool(workflow_holder)
    tools = allowed_tools + [set_wf]

    llm = get_llm()
    return create_react_agent(model=llm, tools=tools, prompt=SYSTEM_PROMPT)


# ─── Streaming execution ──────────────────────────────────────────────────────

def chat_messages_to_lc(messages: list[dict]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for msg in messages:
        if msg.get("role") == "user":
            result.append(HumanMessage(content=msg["content"]))
        else:
            result.append(AIMessage(content=msg["content"]))
    return result


def run_workflow_agent_stream(
    session,
    chat_history: list[dict],
    thread_id: str,
    workflow_holder: dict,
):
    agent = compile_workflow_agent(session, workflow_holder)
    lc_messages = chat_messages_to_lc(chat_history)
    config = {"configurable": {"thread_id": thread_id}}

    final_text = ""
    for chunk in agent.stream({"messages": lc_messages}, config=config, stream_mode="updates"):
        if "agent" in chunk:
            for msg in chunk["agent"].get("messages", []):
                content = getattr(msg, "content", None)
                if isinstance(content, str) and content.strip():
                    final_text = content.strip()
                    yield {"type": "thought", "content": final_text}

                for tc in getattr(msg, "tool_calls", []):
                    yield {
                        "type": "tool_call",
                        "name": tc.get("name", "unknown"),
                        "args": tc.get("args", {}),
                    }

        elif "tools" in chunk:
            for msg in chunk["tools"].get("messages", []):
                yield {
                    "type": "tool_output",
                    "name": getattr(msg, "name", "unknown"),
                    "content": str(getattr(msg, "content", "") or ""),
                }

    yield {"type": "final_answer", "content": final_text or "Done."}
