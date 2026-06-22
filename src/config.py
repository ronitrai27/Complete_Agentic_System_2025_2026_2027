import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

# Force load .env from the project root and override any system environment variables
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=True)


class Settings(BaseSettings):
    # Instruct Pydantic to read from the .env file in the root directory
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # Ignore extra env variables not defined here
    )

    # API Keys
    anthropic_key: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_KEY")
    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_key: Optional[str] = Field(default=None, validation_alias="OPENAI_KEY")
    serpapi_api_key: Optional[str] = Field(default=None, validation_alias="SERPAPI_API_KEY")
    tavily_api_key: Optional[str] = Field(default=None, validation_alias="TAVILY_API_KEY")
    llama_cloud_api_key: Optional[str] = Field(default=None, validation_alias="LLAMA_CLOUD_API_KEY")
    composio_api_key: Optional[str] = Field(default=None, validation_alias="COMPOSIO_API_KEY")

    # Pinecone
    pinecone_index_name: str = Field(default="agentic-system", validation_alias="PINECONE_INDEX_NAME")
    pinecone_api_key: Optional[str] = Field(default=None, validation_alias="PINECONE_API_KEY")

    # Neo4j
    neo4j_uri: Optional[str] = Field(default=None, validation_alias="NEO4J_URI")
    neo4j_username: Optional[str] = Field(default=None, validation_alias="NEO4J_USERNAME")
    neo4j_password: Optional[str] = Field(default=None, validation_alias="NEO4J_PASSWORD")
    neo4j_database: Optional[str] = Field(default=None, validation_alias="NEO4J_DATABASE")

# Export a single, globally available settings object
settings = Settings()


