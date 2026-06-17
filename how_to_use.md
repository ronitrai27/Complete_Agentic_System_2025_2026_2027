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

---

## 4. Production Best Practices & Setup

We have set up the project folder structure matching production standards, implementing 4 key best practices:

### I. Thin DAGs (Separation of Concerns)
*   **Concept**: Airflow DAGs should only schedule and orchestrate. They should never write core business or data logic inside the DAG files.
*   **File**: [dags/document_ingestion_dag.py](file:///r:/python/ai_flow/dags/document_ingestion_dag.py)
*   **Action**: The DAG file imports the core function `ingest_documents_pipeline` from our python package [src/pipelines/ingestion.py](file:///r:/python/ai_flow/src/pipelines/ingestion.py) and executes it inside a `PythonOperator`.

### II. Centralized Configuration Management
*   **Concept**: Use environment variables (`.env`) validated at boot time via Pydantic schemas instead of scattering `os.getenv` calls across the codebase.
*   **File**: [src/config.py](file:///r:/python/ai_flow/src/config.py)
*   **Action**: Pydantic's `BaseSettings` automatically parses and validates environment keys. You can import variables using `from src.config import settings`.

### III. Isolated Database Initialization Scripts
*   **Concept**: DDL schemas, constraints, and indexes for databases (Pinecone, Neo4j) should be executed in setup/deployment scripts, not during active request processing.
*   **File**: [scripts/init_databases.py](file:///r:/python/ai_flow/scripts/init_databases.py)
*   **Action**: Running `poetry run python scripts/init_databases.py` connects to Pinecone & Neo4j, checks if the required indices/constraints are set up, and constructs them if missing.

### IV. Mocking External API calls in Tests
*   **Concept**: Production test pipelines should run quickly, reliably, and without spending money or requiring active API credentials or internet connections.
*   **File**: [tests/test_agents.py](file:///r:/python/ai_flow/tests/test_agents.py)
*   **Action**: Demonstrates how to write tests with `unittest.mock.patch` to intercept requests made by agents to OpenAI or search engines. Run via:
    ```bash
    poetry run pytest
    ```

---

## 5. Production Directory Structure

Below is the directory map created for this project:

```text
ai_flow/
├── .github/workflows/test.yml     # Automated CI testing on push/PR
├── dags/                          # Thin Airflow orchestrator DAGs
│   └── document_ingestion_dag.py  # Daily ingestion DAG
├── src/                           # Main code package
│   ├── config.py                  # Settings loader
│   ├── agents/                    # LLM/LangGraph agents
│   ├── tools/                     # DB/API agent tools
│   ├── pipelines/                 # Business logic run by DAGs
│   │   └── ingestion.py           # Ingestion logic
│   └── utils/                     # Generic utility code
├── ui/                            # Streamlit Frontend
│   ├── app.py                     # Streamlit Main App entry point
│   ├── components/                # Modular UI widgets
│   └── pages/                     # Subpages
├── scripts/                       # Migration & setup scripts
│   └── init_databases.py          # Database setup
└── tests/                         # Automated test suite
    └── test_agents.py             # Mock-based testing examples
```
