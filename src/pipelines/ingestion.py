from loguru import logger
from src.config import settings

def ingest_documents_pipeline():
    """
    Core logic for ingesting raw documents into Pinecone & Neo4j.
    Keeping this logic in src/ allows it to be tested independently of Airflow.
    """
    logger.info("Initializing document ingestion pipeline...")
    
    # Verify we can access configuration
    logger.info(f"Configured Pinecone Index: {settings.pinecone_index_name}")
    if settings.neo4j_uri:
        logger.info(f"Configured Neo4j URI: {settings.neo4j_uri}")
    else:
        logger.warning("Neo4j URI is not configured!")

    # Simulate ingestion tasks...
    logger.info("Fetching raw documents...")
    logger.info("Embedding and indexing documents into Pinecone...")
    logger.info("Constructing knowledge graph relations in Neo4j...")
    
    logger.info("Document ingestion pipeline completed successfully.")
