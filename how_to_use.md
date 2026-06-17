# How to Use & Installation Guide

## 1. Prerequisites & Environment Setup
This project requires **Python `>=3.12,<3.14`** due to Apache Airflow compatibility.

Ensure you have Poetry installed, then set up the environment and install all dependencies:
```bash
# Install all project dependencies
poetry install
```

## 2. Installed Packages
The project dependencies managed by Poetry are:
*   `langchain` - LLM application framework
*   `langchain-community` - Community integrations for LangChain
*   `langgraph` - Building stateful, multi-actor applications
*   `openai` - OpenAI API client
*   `tavily-python` - Tavily search API client
*   `google-search-results` - SerpApi client
*   `llama-cloud` - LlamaIndex cloud services
*   `pinecone-client` - Vector database client
*   `neo4j` - Neo4j graph database client
*   `rank-bm25` - BM25 ranking algorithm
*   `llama-index-core` - LlamaIndex core library
*   `streamlit` - Web application builder
*   `pyvis` - Interactive network visualization
*   `python-dotenv` - Environment variable management
*   `pydantic` - Data validation and settings
*   `loguru` - Advanced logging library
*   `requests` - HTTP requests library
*   `structlog (<25.5.0)` - Logging library pinned for Airflow compatibility
*   `apache-airflow (==3.1.0)` - Workflow orchestration

---

## 3. How Apache Airflow was Installed
Because Poetry doesn't support the `--constraint` parameter and Airflow has strict dependency limits, we performed the following:

1.  **Python Version Limit**: Updated `requires-python` in `pyproject.toml` to `">=3.12,<3.14"` (Airflow 3.1.0 does not support Python `>=3.14` yet).
2.  **Install Command**: Ran:
    ```bash
    poetry add "apache-airflow==3.1.0"
    ```
3.  **`structlog` Version Pin**: Airflow 3.1.0 has an import error (`ImportError: cannot import name 'Styles' from 'structlog.dev'`) with `structlog >= 25.5.0`. We resolved this by pinning and downgrading `structlog`:
    ```bash
    poetry add "structlog<25.5.0"
    ```

You can verify the installation is working by running:
```bash
poetry run airflow version
```
