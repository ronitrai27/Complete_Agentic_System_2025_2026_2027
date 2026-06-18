"""Graph-only retrieval and answering utilities.

This module intentionally does not import Pinecone, BM25, or the hybrid search
stack. Use it for a pure Neo4j flow:

    graph_context = get_graph_only_context("who built Project WeKraft?")
    answer = answer_from_graph_only("who built Project WeKraft?")
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from loguru import logger

from src.config import settings
from src.utils.entity_extractor import extract_entities
from src.utils.graph_store import get_graph_snapshot, get_neighbors, get_two_hop_neighbors


GRAPH_ONLY_SYSTEM_PROMPT = """You answer only from Neo4j knowledge-graph context.
If the graph context does not contain the answer, say that the graph does not
contain enough information. Do not use vector search, BM25, web search, or prior
knowledge to fill gaps."""


def get_graph_only_context(
    query_text: str,
    limit: int = 40,
    document_id: str | None = None,
) -> Dict[str, Any]:
    """Return graph-only context for a query using entity lookup plus fallback search."""
    extracted_entities = extract_entities(query_text)
    graph_context: List[Dict[str, Any]] = []
    seen = set()
    graph_error = None

    try:
        for entity in extracted_entities:
            name = entity["name"]
            label = entity.get("label", "").upper()
            use_two_hop = label in {"PERSON", "ORG", "ROLE"} or "department" in name.lower()

            records = (
                get_two_hop_neighbors(name, limit=limit, document_id=document_id)
                if use_two_hop
                else get_neighbors(name, limit=limit, document_id=document_id)
            )

            for record in records:
                if "n1_name" in record:
                    relation = record.get("r1_type")
                    neighbor = record.get("n1_name")
                    if record.get("n2_name") and record.get("r2_type"):
                        relation = f"{record.get('r1_type')}-->({record.get('n1_name')})--{record.get('r2_type')}"
                        neighbor = record.get("n2_name")
                    sources = record.get("r2_sources") or record.get("r1_sources") or []
                    doc_ids = record.get("r2_document_ids") or record.get("r1_document_ids") or []
                    row = {
                        "entity": record.get("entity_name") or name,
                        "relation": relation,
                        "neighbor": neighbor,
                        "sources": sources,
                        "document_ids": doc_ids,
                    }
                else:
                    row = {
                        "entity": name,
                        "relation": record.get("rel_type"),
                        "neighbor": record.get("neighbor_name"),
                        "sources": record.get("sources") or [],
                        "document_ids": record.get("document_ids") or [],
                    }

                key = (row["entity"], row["relation"], row["neighbor"], tuple(row["document_ids"]))
                if row["relation"] and row["neighbor"] and key not in seen:
                    seen.add(key)
                    graph_context.append(row)

        if not graph_context:
            snapshot = get_graph_snapshot(
                limit=limit,
                search=query_text,
                document_id=document_id or "",
                include_documents=False,
            )
            for rel in snapshot.get("relationships", []):
                graph_context.append(
                    {
                        "entity": rel.get("source"),
                        "relation": rel.get("relation"),
                        "neighbor": rel.get("target"),
                        "sources": rel.get("sources") or [],
                        "document_ids": rel.get("document_ids") or [],
                    }
                )
    except Exception as exc:
        logger.error(f"Graph-only lookup failed: {exc}")
        graph_error = str(exc)

    return {
        "text_chunks": [],
        "graph_context": graph_context[:limit],
        "extracted_entities": [entity["name"] for entity in extracted_entities],
        "graph_error": graph_error,
    }


def format_graph_context(graph_context: List[Dict[str, Any]]) -> str:
    if not graph_context:
        return "No graph relationships were retrieved."

    lines = []
    for item in graph_context:
        sources = ", ".join(item.get("sources") or [])
        suffix = f" | sources: {sources}" if sources else ""
        lines.append(
            f"- {item.get('entity')} --[{item.get('relation')}]--> {item.get('neighbor')}{suffix}"
        )
    return "\n".join(lines)


def answer_from_graph_only(
    query_text: str,
    limit: int = 40,
    document_id: str | None = None,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """Generate an answer using only Neo4j graph context."""
    context = get_graph_only_context(query_text, limit=limit, document_id=document_id)
    graph_text = format_graph_context(context["graph_context"])

    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=temperature, api_key=api_key)
    response = llm.invoke(
        [
            HumanMessage(
                content=(
                    f"{GRAPH_ONLY_SYSTEM_PROMPT}\n\n"
                    f"Graph context:\n{graph_text}\n\n"
                    f"Question: {query_text}\n\n"
                    "Answer from the graph only."
                )
            )
        ]
    )

    return {
        "answer": response.content,
        "graph_context": context["graph_context"],
        "extracted_entities": context["extracted_entities"],
        "graph_error": context["graph_error"],
    }
