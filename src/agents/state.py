"""
AgentState — Pydantic BaseModel schema for the LangGraph RAG agent.

All nodes read from and write to this shared state object.
LangGraph uses this as the graph's typed state annotation.
"""
import uuid
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from pydantic import BaseModel, Field
import operator



# ─── Sub-schemas ──────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    """A single web search result from Tavily or SerpAPI."""
    source: str          # "tavily" | "serpapi"
    title: str
    url: str
    snippet: str

class RagContext(BaseModel):
    """Context retrieved from hybrid RAG (Pinecone + BM25 + Neo4j)."""
    text_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    graph_context: List[Dict[str, Any]] = Field(default_factory=list)

class Message(BaseModel):
    """A single conversation turn."""
    role: str    # "user" | "assistant" | "system"
    content: str

class HitlDecision(BaseModel):
    """Decision made by the human at the HITL interrupt checkpoint."""
    approved: bool = False           # Did the user approve saving?
    notes: Optional[str] = None      # Optional annotation from the user


# ─── Main State Schema ─────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """
    Full state schema for the RAG LangGraph agent.
    
    - conversation_id: unique ID for this session (also SQLite primary key)
    - messages: full conversation history (accumulated with list merge)
    - user_query: the current user question
    - uploaded_file_path: path to an uploaded file (optional)
    - fast_path_text: raw text from LlamaParse for instant answering
    - search_results: aggregated from Tavily + SerpAPI parallel workers
    - rag_context: results from hybrid RAG retrieval
    - mcp_results: raw output from Arcade MCP tool calls
    - final_answer: the LLM's generated answer
    - hitl_decision: the human's decision at the save checkpoint
    - save_requested: flag set when HITL approves saving to memory
    - route: which path the router chose (search | rag | direct)
    """
    conversation_id: str
    
    # Conversation history — uses operator.add so each node APPENDS to this list
    messages: Annotated[List[Message], operator.add]

    # Current turn
    user_query: str
    uploaded_file_path: Optional[str]

    # Fast-path (instant answer from raw parsed text)
    fast_path_text: Optional[str]

    # Parallel web search results — uses operator.add so both workers append
    search_results: Annotated[List[SearchResult], operator.add]

    # Hybrid RAG context
    rag_context: Optional[RagContext]

    # MCP tool outputs
    mcp_results: Annotated[List[Dict[str, Any]], operator.add]

    # Final answer
    final_answer: Optional[str]

    # HITL
    hitl_decision: Optional[HitlDecision]
    save_requested: bool

    # Router decision
    route: str


def create_initial_state(
    user_query: str,
    conversation_id: str | None = None,
    uploaded_file_path: str | None = None,
) -> AgentState:
    """Helper to construct a fully initialized AgentState dictionary."""
    return {
        "conversation_id": conversation_id or str(uuid.uuid4()),
        "messages": [],
        "user_query": user_query,
        "uploaded_file_path": uploaded_file_path,
        "search_results": [],
        "rag_context": None,
        "mcp_results": [],
        "final_answer": None,
        "hitl_decision": None,
        "save_requested": False,
        "route": "direct",
    }

