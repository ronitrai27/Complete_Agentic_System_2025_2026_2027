from loguru import logger
from src.config import settings

def init_pinecone():
    """
    Initializes Pinecone vector indexes if they do not already exist.
    """
    logger.info("Initializing Pinecone Index setup...")
    if not settings.pinecone_api_key:
        logger.warning("PINECONE_API_KEY is not set. Skipping Pinecone setup.")
        return

    try:
        from pinecone import Pinecone, ServerlessSpec
        
        pc = Pinecone(api_key=settings.pinecone_api_key)
        existing_indexes = [idx.name for idx in pc.list_indexes()]
        
        if settings.pinecone_index_name not in existing_indexes:
            logger.info(f"Creating Pinecone index: '{settings.pinecone_index_name}'...")
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=1536,  # Default for OpenAI text-embedding-3-small / text-embedding-ada-002
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
            logger.info("Pinecone index created successfully.")
        else:
            logger.info(f"Pinecone index '{settings.pinecone_index_name}' already exists.")
            
    except Exception as e:
        logger.error(f"Failed to initialize Pinecone: {e}")


def init_neo4j():
    """
    Sets up Neo4j database schemas, indices, and constraints.
    """
    logger.info("Initializing Neo4j Graph DB constraints/indexes...")
    if not settings.neo4j_uri:
        logger.warning("NEO4J_URI is not set. Skipping Neo4j setup.")
        return

    try:
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password)
        )
        
        # Open a session to run schema updates
        db_name = settings.neo4j_database or "neo4j"
        with driver.session(database=db_name) as session:
            # Create a unique constraint on Entity nodes for Knowledge Graph RAG
            session.run(
                "CREATE CONSTRAINT unique_entity_name IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )
            logger.info("Neo4j unique constraint on (Entity.name) verified/created successfully.")
            
        driver.close()
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j: {e}")


if __name__ == "__main__":
    logger.info("Starting database initialization...")
    init_pinecone()
    init_neo4j()
    logger.info("Database initialization check complete.")
