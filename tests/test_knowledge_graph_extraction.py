from unittest.mock import patch

from src.utils.entity_extractor import (
    extract_entities,
    extract_knowledge_graph_elements,
)
from src.utils.graph_store import upsert_entities_and_relations
from src.utils.graph_response import get_graph_only_context


WEKRAFT_TEXT = """
Ronit Rai leads Project WeKraft.
Akash Sharma develops the WeKraft API.
Riya Kapoor designs the WeKraft user experience.
Mia Chen tests the WeKraft release.
Project WeKraft depends on AWS infrastructure.
Project WeKraft extends Project Atlas.
Project WeKraft supports Project Orion.
"""


def test_wekraft_entities_and_connections_are_extracted():
    graph = extract_knowledge_graph_elements(WEKRAFT_TEXT)
    entity_names = {entity["name"] for entity in graph["entities"]}
    triples = {
        (relation["source"], relation["type"], relation["target"])
        for relation in graph["relations"]
    }

    assert {"Project WeKraft", "Ronit Rai", "Akash Sharma", "Riya Kapoor", "Mia Chen"} <= entity_names
    assert ("Ronit Rai", "LEAD", "Project WeKraft") in triples
    assert ("Project WeKraft", "EXTEND", "Project Atlas") in triples
    assert ("Project WeKraft", "SUPPORT", "Project Orion") in triples


def test_duplicate_relations_are_collapsed_before_neo4j():
    graph = extract_knowledge_graph_elements(
        "Ronit Rai leads Project WeKraft. Ronit Rai leads Project WeKraft."
    )
    assert graph["relations"] == [
        {"source": "Ronit Rai", "type": "LEAD", "target": "Project WeKraft"}
    ]


def test_wekraft_query_is_available_for_graph_retrieval():
    names = {
        entity["name"]
        for entity in extract_entities(
            "Who works on Project WeKraft and how is it connected to Project Atlas?"
        )
    }
    assert {"Project WeKraft", "Project Atlas"} <= names


def test_upsert_sends_each_unique_relation_once():
    graph = extract_knowledge_graph_elements(WEKRAFT_TEXT)
    calls = []

    def capture(query, parameters=None):
        calls.append((query, parameters or {}))
        return []

    with patch("src.utils.graph_store.run_write_query", side_effect=capture):
        upsert_entities_and_relations(graph["entities"], graph["relations"])

    relation_total = sum(len(parameters["rels"]) for _, parameters in calls[1:])
    assert relation_total == len(graph["relations"])


def test_skills_and_past_experience_are_extracted():
    graph = extract_knowledge_graph_elements(
        """
        Dev Patel develops the Graph Only RAG service.
        Dev Patel has skills in Python, Neo4j, Cypher, and LangGraph.
        Dev Patel previously built Knowledge Graph Audit Toolkit.
        Dev Patel formerly worked on Project Meridian.
        """
    )
    entity_names = {entity["name"] for entity in graph["entities"]}
    triples = {
        (relation["source"], relation["type"], relation["target"])
        for relation in graph["relations"]
    }

    assert {"Dev Patel", "Python", "Neo4j", "Cypher", "LangGraph"} <= entity_names
    assert ("Dev Patel", "DEVELOP", "Graph Only RAG service") in triples
    assert ("Dev Patel", "SKILLED_IN", "Python") in triples
    assert ("Dev Patel", "PREVIOUSLY_BUILT", "Knowledge Graph Audit Toolkit") in triples
    assert ("Dev Patel", "WORKED_ON", "Project Meridian") in triples


def test_upsert_adds_document_provenance_without_deleting_existing_graph():
    graph = extract_knowledge_graph_elements("Aarav Mehta leads OpenAI Agent Workspace.")
    calls = []

    def capture(query, parameters=None):
        calls.append((query, parameters or {}))
        return []

    with patch("src.utils.graph_store.run_write_query", side_effect=capture):
        upsert_entities_and_relations(
            graph["entities"],
            graph["relations"],
            document_id="doc_openai_prd",
            document_name="openai_prd_people_work_skills.txt",
        )

    assert calls[0][1]["document_id"] == "doc_openai_prd"
    assert "Document" in calls[1][0]
    assert calls[1][1]["document_name"] == "openai_prd_people_work_skills.txt"
    assert all("DELETE" not in query.upper() for query, _ in calls)


def test_graph_only_context_uses_neo4j_lookup_without_text_indexes():
    with patch("src.utils.graph_response.get_two_hop_neighbors") as two_hop, \
         patch("src.utils.graph_response.get_neighbors") as one_hop:
        two_hop.return_value = [
            {
                "entity_name": "Dev Patel",
                "r1_type": "DEVELOP",
                "n1_name": "Graph Only RAG",
                "n1_label": "PRODUCT",
                "r1_sources": ["openai_prd_people_work_skills.txt"],
                "r1_document_ids": ["doc_openai_prd"],
                "r2_type": None,
                "n2_name": None,
                "n2_label": None,
            }
        ]

        context = get_graph_only_context("What does Dev Patel develop?")

    assert context["text_chunks"] == []
    assert context["graph_context"][0]["relation"] == "DEVELOP"
    assert context["graph_context"][0]["neighbor"] == "Graph Only RAG"
    one_hop.assert_not_called()
