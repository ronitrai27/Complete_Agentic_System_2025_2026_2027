import os
import time
from typing import List, Dict, Any
from loguru import logger
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from llama_index.core.node_parser import SentenceSplitter
from src.config import settings

# Initialize clients
def get_openai_client() -> OpenAI:
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=api_key)

def get_pinecone_index():
    if not settings.pinecone_api_key:
        raise ValueError("Pinecone API key is not configured in settings.")
    pc = Pinecone(api_key=settings.pinecone_api_key)
    existing_indexes = {item.name for item in pc.list_indexes()}
    if settings.pinecone_index_name not in existing_indexes:
        logger.warning(
            f"Pinecone index '{settings.pinecone_index_name}' does not exist; creating it."
        )
        pc.create_index(
            name=settings.pinecone_index_name,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        for _ in range(30):
            description = pc.describe_index(settings.pinecone_index_name)
            status = getattr(description, "status", None)
            ready = getattr(status, "ready", False)
            if isinstance(status, dict):
                ready = status.get("ready", False)
            if ready:
                break
            time.sleep(1)
    return pc.Index(settings.pinecone_index_name)

def chunk_text(text: str, chunk_size: int = 1024, chunk_overlap: int = 200) -> List[str]:
    """
    Split text into chunks using SentenceSplitter.
    """
    logger.info(f"Chunking text with SentenceSplitter (size={chunk_size}, overlap={chunk_overlap})...")
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    nodes = splitter.get_nodes_from_documents([
        # SentenceSplitter expects a list of Document objects or raw text depending on usage,
        # but in llama-index-core we can wrap it in Document or use split_text.
        # split_text is cleaner for raw string input.
    ])
    # split_text is the direct method on SentenceSplitter for raw strings.
    chunks = splitter.split_text(text)
    logger.info(f"Split text into {len(chunks)} chunks.")
    return chunks

def embed_text(text: str) -> List[float]:
    """
    Generate embedding for text using OpenAI's text-embedding-3-small model.
    """
    client = get_openai_client()
    # Clean up whitespace
    cleaned_text = text.replace("\n", " ")
    response = client.embeddings.create(
        input=[cleaned_text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def index_chunks(document_id: str, chunks: List[str], metadata_base: Dict[str, Any] = None) -> None:
    """
    Embed and index a list of chunks into Pinecone.
    """
    if not chunks:
        logger.warning("No chunks provided to index.")
        return

    logger.info(f"Indexing {len(chunks)} chunks for document {document_id} into Pinecone...")
    index = get_pinecone_index()
    vectors = []
    
    for i, chunk in enumerate(chunks):
        chunk_id = f"{document_id}#chunk_{i}"
        embedding = embed_text(chunk)
        
        # Prepare metadata
        metadata = (metadata_base or {}).copy()
        metadata["text"] = chunk
        metadata["document_id"] = document_id
        metadata["chunk_index"] = i
        
        vectors.append({
            "id": chunk_id,
            "values": embedding,
            "metadata": metadata
        })
        
        # Upsert in batches of 100
        if len(vectors) >= 100:
            index.upsert(vectors=vectors)
            vectors = []
            
    if vectors:
        index.upsert(vectors=vectors)
        
    logger.info(f"Successfully finished indexing document {document_id}.")


def query_vector_store(
    query_text: str,
    top_k: int = 5,
    conversation_id: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Queries Pinecone for the top_k matching chunks.
    """
    logger.info(f"Querying Pinecone for: '{query_text}'")
    query_vector = embed_text(query_text)
    index = get_pinecone_index()
    
    metadata_filter: Dict[str, Any] = {"type": {"$ne": "conversation"}}
    if conversation_id:
        metadata_filter = {
            "$or": [
                {"type": {"$ne": "conversation"}},
                {
                    "$and": [
                        {"type": {"$eq": "conversation"}},
                        {"conversation_id": {"$eq": conversation_id}},
                    ]
                },
            ]
        }

    response = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
        filter=metadata_filter,
    )
    
    results = []
    for match in response.matches:
        results.append({
            "id": match.id,
            "score": match.score,
            "text": match.metadata.get("text", ""),
            "metadata": match.metadata
        })
        
    return results
