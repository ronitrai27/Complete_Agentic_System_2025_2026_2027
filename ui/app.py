import streamlit as st
from src.config import settings

st.set_page_config(
    page_title="Production AI Flow Portal",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Production AI Flow Portal")
st.write("Welcome to your production-grade Streamlit Dashboard, integrated with Poetry, Airflow, Pinecone, and Neo4j.")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("🔌 Configuration Status")
    st.write("Status of database credentials loaded from `.env` via `Pydantic Settings`:")
    
    st.markdown(f"**Pinecone Index:** `{settings.pinecone_index_name}`")
    st.markdown(f"**Neo4j Host:** `{settings.neo4j_uri or '⚠️ Not Configured'}`")
    st.markdown(f"**Neo4j Database:** `{settings.neo4j_database or 'default'}`")
    st.markdown(f"**OpenAI API Key Configured?** `{'Yes' if settings.openai_api_key else 'No'}`")

with col2:
    st.subheader("⚙️ Local Pipeline Executor")
    st.write("Trigger the document ingestion pipeline logic directly from here (bypassing the Airflow scheduler for debug/admin runs):")
    
    if st.button("Run Ingestion Pipeline", type="primary"):
        with st.spinner("Executing pipeline in background..."):
            from src.pipelines.ingestion import ingest_documents_pipeline
            try:
                ingest_documents_pipeline()
                st.success("Pipeline run finished! Check your console/logs.")
            except Exception as e:
                st.error(f"Pipeline failed: {e}")
