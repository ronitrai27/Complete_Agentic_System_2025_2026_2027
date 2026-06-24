# Production Workflow Automation: Airflow Schedulers & Deterministic Architectures

This guide describes how to run saved workflows on a robust scheduler like **Apache Airflow**, how to establish a bulletproof execution framework, and premium features you can add to elevate this system.

---

## 1. Scheduling Workflows with Apache Airflow

Because workflow execution is a **pure Python function** requiring no AI, it translates directly into a standard Airflow DAG. 

Each step of a workflow can be mapped to an task, allowing Airflow to handle retries, dependencies, logging, and status tracking natively:

```python
from datetime import datetime, timedelta
import json
from airflow import DAG
from airflow.operators.python import PythonOperator
from composio import Composio

# Initialize Composio Client
comp = Composio(api_key="your_composio_api_key")

def execute_step(t_name, step_idx, workflow_path, user_id, **context):
    # 1. Load arguments from saved JSON
    with open(workflow_path, 'r') as f:
        workflow = json.load(f)
    step = workflow["steps"][step_idx]
    
    # 2. Gather parameters
    tool_args = {}
    for field in step.get("fields", []):
        val = field.get("value", "")
        # Resolve dynamic variables from previous tasks (XComs)
        if isinstance(val, str) and val.startswith("{{") and val.endswith("}}"):
            source_task = val.strip("{} ").split(".")[0]
            val = context['ti'].xcom_pull(task_ids=source_task)
            
        if val not in ("", [], {}):
            tool_args[field["name"]] = val
            
    # 3. Execute
    print(f"Invoking {t_name} with args: {tool_args}")
    result = comp.tools.execute(
        slug=t_name,
        arguments=tool_args,
        user_id=user_id,
        dangerously_skip_version_check=True
    )
    
    if not result.successful:
        raise ValueError(f"Step {step_idx} ({t_name}) failed: {result.error}")
        
    # Return payload for subsequent steps to read via XComs
    return result.data

default_args = {
    'owner': 'workflow_engine',
    'start_date': datetime(2026, 1, 1),
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'composio_weekly_reddit_summarizer',
    default_args=default_args,
    schedule_interval='@weekly', # Run once a week
    catchup=False
) as dag:

    # Step 1: Fetch Hot Posts from Reddit
    step1 = PythonOperator(
        task_id='reddit_get_posts',
        python_callable=execute_step,
        op_args=['REDDIT_GET_HOT_POSTS', 0, '/path/to/workflow.json', 'user_v55i61letn6c'],
        provide_context=True,
    )

    # Step 2: Post Summary to Slack
    step2 = PythonOperator(
        task_id='slack_post_message',
        python_callable=execute_step,
        op_args=['SLACK_CHAT_POST_MESSAGE', 1, '/path/to/workflow.json', 'user_v55i61letn6c'],
        provide_context=True,
    )

    step1 >> step2  # Run step 1 first, then pass output to step 2
```

---

## 2. Designing a Deterministic Architecture

To ensure 100% execution reliability, your backend architecture should use these three phases:

### Phase A: Design Phase (AI Assist)
- The user chats with the AI agent.
- The AI discovers tool slugs and fetches schemas.
- The AI outputs a structured JSON representing the workflow.
- **Rules**: LLM/AI is *only* active during this interactive design step. No AI is used in the execution engine.

### Phase B: Variable Mapping (Cross-Step Injection)
To make workflows actually useful, users must be able to pipe the outputs of Step 1 into Step 2.
- Support string templates like `{{step_1.title}}` or `{{step_1.url}}`.
- The execution engine resolves these placeholders right before executing the tool by reading the output payload dictionary of Step 1.

### Phase C: Execution Phase (Pure Engine)
- The execution is a simple sequential loop run by a worker (Celery, Airflow, or Cron).
- If any step fails, execution halts, logging the error payload.
- All empty strings/optional fields are automatically stripped before reaching the Composio API.

---

## 3. Premium Features to Build Next

To make this application look and feel extremely premium and competitive, add these features:

1. **Visual Canvas Interface**:
   - Provide a drag-and-drop node graph (like Node-RED or LangFlow) on the right panel, allowing users to visually link blocks, map variables, and see execution paths.
   
2. **Variable Injection Autocomplete**:
   - In the Streamlit parameter form, when editing a field, show a dropdown list of available outputs from previous steps (e.g. `Step 1 (Reddit) - Hot Post Title`) so the user doesn't have to type placeholders manually.

3. **Self-Healing Auth Prompts**:
   - If a toolkit execution fails with a `401 Unauthorized` (Oauth expired), trigger a toast and email notifying the user: *"Your Slack connection has expired. Click here to re-authorize."*

4. **Event-Driven Webhook Triggers**:
   - Instead of just scheduling (polling), let workflows trigger on webhook events (e.g. *"When a new issue is opened in GitHub, automatically post summary to Slack"*). You can accomplish this via Composio Triggers.
   
5. **Dry Run Mode**:
   - Let users click a "Validate & Dry Run" button that queries the parameter formats and tests active session connection status for all steps *without* actually making the API calls (perfect for test runs).
