
# ARCADE MCP (NOTION + GOOGLE DOC + GMAIL + MICROSOFT OUTLOOK MAIL)

import asyncio
import os
from typing import Any, List

from arcadepy import AsyncArcade
from arcadepy.types import ToolDefinition
from langchain_core.tools import StructuredTool
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from pydantic import BaseModel, Field, create_model

# ─── Config ───────────────────────────────────────────────────────────────────

MCP_SERVERS = ["Notion", "Gmail", "GoogleDocs", "MicrosoftOutlookMail"]
TOOL_LIMIT = 30

# ─── Type Mapping ─────────────────────────────────────────────────────────────

TYPE_MAPPING = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "json": dict,
}

def get_python_type(val_type: str) -> Any:
    _type = TYPE_MAPPING.get(val_type)
    if _type is None:
        raise ValueError(f"Invalid value type: {val_type}")
    return _type

# ─── Convert Arcade Schema → Pydantic Model ───────────────────────────────────

def arcade_schema_to_pydantic(tool_def: ToolDefinition) -> type[BaseModel]:
    try:
        fields: dict[str, Any] = {}
        for param in tool_def.input.parameters or []:
            param_type = get_python_type(param.value_schema.val_type)
            if param_type is list and param.value_schema.inner_val_type:
                inner_type: type[Any] = get_python_type(param.value_schema.inner_val_type)
                param_type = list[inner_type]
            param_description = param.description or "No description provided."
            default = ... if param.required else None
            fields[param.name] = (
                param_type,
                Field(default=default, description=param_description),
            )
        return create_model(f"{tool_def.name}Args", **fields)
    except ValueError as e:
        raise ValueError(
            f"Error converting {tool_def.name} parameters into pydantic model: {e}"
        )

# ─── Convert Arcade Tool → LangChain StructuredTool ──────────────────────────

async def arcade_to_langchain(
    arcade_client: AsyncArcade,
    arcade_tool: ToolDefinition,
) -> StructuredTool:
    args_schema = arcade_schema_to_pydantic(arcade_tool)

    async def tool_function(config: RunnableConfig, **kwargs: Any) -> Any:
        user_id = config.get("configurable", {}).get("user_id") if config else None
        if not user_id:
            raise ValueError("user_id is required in config to execute Arcade tools")

        # ── Check / trigger OAuth ──────────────────────────────────────────
        auth_response = await arcade_client.tools.authorize(
            tool_name=arcade_tool.qualified_name,
            user_id=user_id,
        )

        if auth_response.status != "completed":
            from src.utils.event_bus import emit
            emit(f"🔐 Authorization required for **{arcade_tool.qualified_name}**. [Click here to authorize]({auth_response.url})", "warning")
            # Pause the LangGraph agent and bubble up auth info
            interrupt_result = interrupt({
                "type": "authorization_required",
                "tool_name": arcade_tool.qualified_name,
                "auth_response": {
                    "id": auth_response.id,
                    "url": auth_response.url,
                },
            })

            authorized = interrupt_result.get("authorized")
            if not authorized:
                raise RuntimeError(
                    f"Authorization was not completed for tool: {arcade_tool.name}"
                )

        # ── Execute the tool ───────────────────────────────────────────────
        filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}

        response = await arcade_client.tools.execute(
            tool_name=arcade_tool.qualified_name,
            input=filtered_kwargs,
            user_id=user_id,
        )

        if response.output and response.output.value:
            return response.output.value

        # ── Handle errors ──────────────────────────────────────────────────
        error_details = {
            "error": "Unknown error occurred",
            "tool": arcade_tool.qualified_name,
        }

        if response.output is not None and response.output.error is not None:
            error = response.output.error
            error_message = str(error.message) if hasattr(error, "message") else "Unknown error"
            error_details["error"] = error_message

            for field in ["additional_prompt_content", "can_retry", "developer_message", "retry_after_ms"]:
                if (value := getattr(error, field, None)) is not None:
                    error_details[field] = str(value)

        return error_details

    return StructuredTool.from_function(
        coroutine=tool_function,
        name=arcade_tool.qualified_name.replace(".", "_"),
        description=arcade_tool.description,
        args_schema=args_schema,
    )

# ─── Fetch All 4 MCP Tools from Arcade ───────────────────────────────────────

async def get_arcade_tools(
    arcade_client: AsyncArcade | None = None,
    mcp_servers: List[str] | None = None,
    tool_limit: int = TOOL_LIMIT,
) -> List[StructuredTool]:

    if not arcade_client:
        arcade_client = AsyncArcade(api_key=os.getenv("ARCADE_API_KEY"))

    if not mcp_servers:
        mcp_servers = MCP_SERVERS

    # Fetch tool definitions from all 4 MCP servers in parallel
    tasks = [
        arcade_client.tools.list(toolkit=server, limit=tool_limit)
        for server in mcp_servers
    ]
    responses = await asyncio.gather(*tasks)

    # Deduplicate by fully qualified name
    tool_definitions: dict[str, ToolDefinition] = {}
    for response in responses:
        for tool in response.items:
            tool_definitions[tool.fully_qualified_name] = tool

    print(f"[Arcade] Fetched {len(tool_definitions)} tools from: {mcp_servers}")

    # Convert all to LangChain StructuredTools in parallel
    conversion_tasks = [
        arcade_to_langchain(arcade_client, tool_def)
        for tool_def in tool_definitions.values()
    ]
    langchain_tools = await asyncio.gather(*conversion_tasks)

    return list(langchain_tools)

# ─── Auth Interrupt Handler (call this from your agent harness) ───────────────

async def handle_authorization_interrupt(
    interrupt_value: dict,
    arcade_client: AsyncArcade,
) -> dict:
    auth_response = interrupt_value.get("auth_response", {})
    auth_id = auth_response.get("id")
    auth_url = auth_response.get("url")
    tool_name = interrupt_value.get("tool_name")

    if not auth_id or not auth_url:
        print("[Arcade] Authorization interrupt missing required context")
        return {"authorized": False}

    print(f"\n{'='*60}")
    print(f"Authorization required for: {tool_name}")
    print(f"Visit this URL to authorize:\n\n  {auth_url}\n")
    print("Waiting for authorization to complete...")
    print(f"{'='*60}\n")

    try:
        status_response = await arcade_client.auth.wait_for_completion(auth_id)

        if status_response.status == "completed":
            print("[Arcade] Authorization completed successfully!")
            return {"authorized": True}
        else:
            print(f"[Arcade] Authorization failed: {status_response.status}")
            return {"authorized": False}

    except Exception as e:
        print(f"[Arcade] Error during authorization: {e}")
        return {"authorized": False}

# ─── Quick Test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def test():
        tools = await get_arcade_tools()
        print(f"\nTotal tools loaded: {len(tools)}")
        for t in tools:
            print(f"  - {t.name}")

    asyncio.run(test())