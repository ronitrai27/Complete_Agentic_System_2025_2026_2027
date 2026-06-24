"""
Composio-connected apps agent — simple LangGraph ReAct loop.

Separate from the RAG agent in rag_agent.py. Uses Composio sessions for
OAuth + pre-built tools (Gmail, Linear, Notion, etc.).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from composio import Composio
from composio_langchain import LangchainProvider
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.config import settings

# ─── Toolkit catalog (sidebar UI + session scope) ─────────────────────────────

TOOLKIT_CATALOG: list[dict[str, str]] = [
    {"slug": "jira", "name": "Jira", "icon": "📋"},
    {"slug": "linear", "name": "Linear", "icon": "📐"},
    {"slug": "gmail", "name": "Gmail", "icon": "✉️"},
    {"slug": "googlecalendar", "name": "Google Calendar", "icon": "📅"},
    {"slug": "notion", "name": "Notion", "icon": "📝"},
    {"slug": "github", "name": "GitHub", "icon": "🐙"},
    {"slug": "typeform", "name": "Typeform", "icon": "📊"},
    {"slug": "apollo", "name": "Apollo", "icon": "🚀"},
    {"slug": "todoist", "name": "Todoist", "icon": "✅"},
    {"slug": "slack", "name": "Slack", "icon": "💬"},
    {"slug": "reddit", "name": "Reddit", "icon": "🤖"},
    {"slug": "linkedin", "name": "LinkedIn", "icon": "💼"},
    {"slug": "googlemeet", "name": "Google Meet", "icon": "📹"},
]

TOOLKITS: list[str] = [t["slug"] for t in TOOLKIT_CATALOG]

SYSTEM_PROMPT = """You are a connected-apps assistant powered by Composio.

You can fetch and read data from the user's integrations:
Jira, Linear, Gmail, Google Calendar, Notion, GitHub, Typeform, Apollo, Todoist, Slack, Reddit, LinkedIn, and Google Meet.

When the user asks you to summarize or report on something:
1. Search for and call the right Composio tools to fetch the data.
2. Read the results carefully.
3. Reply with a clear, structured summary and cite which apps you used.

If an integration is not connected, tell the user to click Connect for that app
in the sidebar, then ask again. You may also share a Connect Link if Composio
returns one via COMPOSIO_MANAGE_CONNECTIONS.

IMPORTANT: Always use the slug 'googlecalendar' (without underscores) when referring to or managing Google Calendar. Do not use 'google_calendar'.

CRITICAL URL RULES:
- NEVER invent, guess, or output placeholder connection links like 'https://your-auth-link-here' or 'https://link-to-typeform'.
- ONLY share connection links if they are explicitly returned in a tool's output.
- If a toolkit is not connected and the tool call did not provide an authorization URL, explicitly instruct the user to use the 'Connect' button in the sidebar.

Do not invent data — only summarize what the tools return."""


# ─── Composio client + session ────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_composio() -> Composio:
    api_key = settings.composio_api_key or os.getenv("COMPOSIO_API_KEY")
    if api_key:
        return Composio(api_key=api_key, provider=LangchainProvider())
    return Composio(provider=LangchainProvider())


def create_user_session(user_id: str):
    """Per-user Composio session scoped to our toolkit list."""
    return get_composio().create(
        user_id=user_id,
        toolkits=TOOLKITS,
        manage_connections={"enable": True},
        workbench={"enable": False},
    )


def get_connect_url(session, toolkit_slug: str) -> str:
    request = session.authorize(toolkit_slug)
    return request.redirect_url


def get_toolkit_status(session) -> list[dict[str, Any]]:
    """Return catalog entries enriched with connected=True/False."""
    connected_slugs: set[str] = set()
    try:
        response = session.toolkits()
        items = response.items if hasattr(response, "items") else response
        for tk in items:
            slug = (getattr(tk, "slug", None) or getattr(tk, "name", "") or "").lower()
            slug = slug.replace(" ", "").replace("_", "")
            conn = getattr(tk, "connection", None)
            if conn and getattr(conn, "is_active", False):
                connected_slugs.add(slug)
                # googlecalendar may appear as google_calendar etc.
                if "gmail" in slug:
                    connected_slugs.add("gmail")
                if "calendar" in slug:
                    connected_slugs.add("googlecalendar")
                if "meet" in slug:
                    connected_slugs.add("googlemeet")
    except Exception:
        pass

    result = []
    for entry in TOOLKIT_CATALOG:
        slug = entry["slug"]
        result.append({
            **entry,
            "connected": slug in connected_slugs,
        })
    return result


# ─── LangGraph agent ──────────────────────────────────────────────────────────

def get_llm() -> ChatOpenAI:
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.2,
        api_key=api_key,
    )


def compile_composio_agent(session):
    """Build a LangGraph ReAct agent with Composio LangChain tools."""
    tools = session.tools()
    llm = get_llm()
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )


def chat_messages_to_lc(messages: list[dict[str, str]]) -> list[BaseMessage]:
    lc: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            lc.append(HumanMessage(content=content))
        else:
            lc.append(AIMessage(content=content))
    return lc


def run_agent_turn(
    session,
    chat_history: list[dict[str, str]],
    thread_id: str,
) -> str:
    """
    Run one user turn through the LangGraph agent.
    chat_history must include the latest user message as the last entry.
    """
    agent = compile_composio_agent(session)
    lc_messages = chat_messages_to_lc(chat_history)
    config = {"configurable": {"thread_id": thread_id}}

    result = agent.invoke({"messages": lc_messages}, config=config)
    out_messages = result.get("messages", [])
    if not out_messages:
        return "No response from agent."

    last = out_messages[-1]
    content = getattr(last, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        joined = "".join(parts).strip()
        if joined:
            return joined
    return str(content or "No response from agent.")


def run_agent_turn_stream(
    session,
    chat_history: list[dict[str, str]],
    thread_id: str,
):
    """
    Run one user turn through the LangGraph agent, yielding trace events.
    """
    agent = compile_composio_agent(session)
    lc_messages = chat_messages_to_lc(chat_history)
    config = {"configurable": {"thread_id": thread_id}}

    final_text = ""
    for chunk in agent.stream({"messages": lc_messages}, config=config, stream_mode="updates"):
        if "agent" in chunk:
            messages = chunk["agent"].get("messages", [])
            if messages:
                msg = messages[-1]
                content = getattr(msg, "content", None)
                if isinstance(content, str) and content.strip():
                    text_content = content.strip()
                    final_text = text_content
                    yield {"type": "thought", "content": text_content}
                
                tool_calls = getattr(msg, "tool_calls", [])
                for tc in tool_calls:
                    yield {
                        "type": "tool_call",
                        "name": tc.get("name", "unknown"),
                        "args": tc.get("args", {}),
                    }
        elif "tools" in chunk:
            messages = chunk["tools"].get("messages", [])
            for msg in messages:
                content = getattr(msg, "content", None)
                name = getattr(msg, "name", "unknown")
                yield {
                    "type": "tool_output",
                    "name": name,
                    "content": str(content or ""),
                }
    
    yield {"type": "final_answer", "content": final_text or "No response from agent."}
