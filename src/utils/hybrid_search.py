from typing import List, Dict, Any
from loguru import logger
from src.utils.vector_store import query_vector_store
from src.utils.keyword_search import query_bm25
from src.utils.graph_store import get_neighbors, get_two_hop_neighbors
from src.utils.entity_extractor import extract_entities

def get_hybrid_context(
    query_text: str,
    top_k: int = 4,
    conversation_id: str | None = None,
) -> Dict[str, Any]:
    """
    Executes hybrid search combining:
    1. Pinecone Vector Search (Semantic)
    2. BM25 Search (Keyword)
    3. Neo4j Graph Search (Entity context)
    
    Returns a dictionary with text chunks and graph context.
    """
    logger.info(f"Initiating hybrid search for query: '{query_text}'")
    
    # 1. Pinecone search
    vector_results = []
    try:
        vector_results = query_vector_store(
            query_text,
            top_k=top_k,
            conversation_id=conversation_id,
        )
    except Exception as e:
        logger.error(f"Pinecone query failed: {e}")
        
    # 2. BM25 keyword search
    bm25_results = []
    try:
        bm25_results = query_bm25(query_text, top_k=top_k)
    except Exception as e:
        logger.error(f"BM25 query failed: {e}")
        
    # Combine text results (simple deduplication by text content)
    seen_texts = set()
    combined_chunks = []
    
    # Add vector results first (higher priority for semantic)
    for res in vector_results:
        text = res["text"]
        if text not in seen_texts:
            seen_texts.add(text)
            combined_chunks.append({
                "text": text,
                "source": "vector",
                "score": res.get("score", 0.0),
                "metadata": res.get("metadata", {})
            })
            
    # Add BM25 results
    for res in bm25_results:
        text = res["text"]
        if text not in seen_texts:
            seen_texts.add(text)
            combined_chunks.append({
                "text": text,
                "source": "bm25",
                "score": res.get("score", 0.0),
                "metadata": res.get("metadata", {})
            })
            
    # 3. Entity Graph context lookup
    graph_context = []
    extracted_entities = []
    graph_error = None
    try:
        # Extract entities from query
        entities = extract_entities(query_text)
        extracted_entities = [ent["name"] for ent in entities]
        logger.info(f"Extracted entities from query: {extracted_entities}")
        
        for ent in entities:
            name = ent["name"]
            label = ent.get("label", "").upper()
            
            # Check if this entity is a department or a person
            is_person_or_dept = (
                label in ("PERSON", "ORG") or 
                "department" in name.lower() or 
                "person" in label.lower()
            )
            
            if is_person_or_dept:
                logger.info(f"Performing 2-hop lookup for department/person: '{name}'")
                neighbors = get_two_hop_neighbors(name, limit=20)
                for record in neighbors:
                    e_name = record.get("entity_name")
                    n1_name = record.get("n1_name")
                    r1_type = record.get("r1_type")
                    n2_name = record.get("n2_name")
                    r2_type = record.get("r2_type")
                    
                    if n2_name and r2_type:
                        # 2-hop relationship
                        graph_context.append({
                            "entity": e_name,
                            "relation": f"{r1_type}-->({n1_name})--{r2_type}",
                            "neighbor": n2_name,
                            "neighbor_label": record.get("n2_label"),
                            "sources": record.get("r2_sources") or record.get("r1_sources") or [],
                            "document_ids": record.get("r2_document_ids") or record.get("r1_document_ids") or [],
                        })
                    else:
                        # 1-hop fallback
                        graph_context.append({
                            "entity": e_name,
                            "relation": r1_type,
                            "neighbor": n1_name,
                            "neighbor_label": record.get("n1_label"),
                            "sources": record.get("r1_sources") or [],
                            "document_ids": record.get("r1_document_ids") or [],
                        })
            else:
                logger.info(f"Performing 1-hop lookup for: '{name}'")
                neighbors = get_neighbors(name, limit=10)
                for neighbor in neighbors:
                    graph_context.append({
                        "entity": name,
                        "relation": neighbor.get("rel_type"),
                        "neighbor": neighbor.get("neighbor_name"),
                        "neighbor_label": neighbor.get("neighbor_label"),
                        "sources": neighbor.get("sources") or [],
                        "document_ids": neighbor.get("document_ids") or [],
                    })
    except Exception as e:
        logger.error(f"Graph context lookup failed: {e}")
        graph_error = str(e)
        
    return {
        "text_chunks": combined_chunks,
        "graph_context": graph_context,
        "extracted_entities": extracted_entities,
        "graph_error": graph_error
    }
