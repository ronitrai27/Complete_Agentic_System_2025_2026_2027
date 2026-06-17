from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

# Import the core logic from our src package. 
# This keeps the DAG thin and parses fast.
from src.pipelines.ingestion import ingest_documents_pipeline

default_args = {
    'owner': 'production_admin',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'document_ingestion_pipeline',
    default_args=default_args,
    description='Orchestrates document ingestion by calling Python logic defined in src/',
    schedule_interval='@daily',
    catchup=False,
) as dag:

    run_ingestion = PythonOperator(
        task_id='run_ingestion_pipeline',
        python_callable=ingest_documents_pipeline,
    )
