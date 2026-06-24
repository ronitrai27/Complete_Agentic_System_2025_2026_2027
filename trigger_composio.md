# Event-Driven Automation: Composio Webhook & Polling Triggers

Instead of relying on periodic polling loops or manual scheduling (e.g., via Airflow or cron jobs), your workflow automation can be fully **event-driven**. When an event occurs in an external app—such as a new email in Gmail, a new issue in GitHub, a task in Todoist, or a message in Slack—Composio can immediately capture that event and run your workflow actions in real time.

This guide details how triggers work, how to discover and configure them for multiple services, and how to execute event-driven actions in Python.

---

## 1. How Triggers Work in Composio

Composio supports two trigger mechanisms under the hood, but abstracts them into a single subscription model:

| Trigger Type | How it Works | Example Toolkits |
|---|---|---|
| **Webhook** | The provider pushes events in real-time to a Composio-managed URL. Composio verifies signatures and forwards the payload to your application. | GitHub, Slack, Notion, Asana |
| **Polling** | Composio polls the provider at regular intervals (typically every 2 to 15 minutes depending on plan settings) and pushes new events to your code. | Gmail, Google Calendar |

When you enable or create a trigger instance:
1. Composio handles the webhook ingress configuration on the source app automatically (e.g., registering the webhook URL on GitHub or Slack).
2. You open an event stream via the SDK to listen to those incoming events and execute your custom workflow callbacks.

---

## 2. Managing Triggers in Python

### Discovering Available Trigger Types

You can query all available trigger types for a specific toolkit using the `client.triggers.list()` method:

```python
from dotenv import load_dotenv
from composio import Composio

load_dotenv()
client = Composio()

# List all triggers for Slack
slack_triggers = client.triggers.list(toolkit_slugs=["slack"])
for t in slack_triggers.items:
    print(f"Slug: {t.slug} | Name: {t.name}")
    print(f"Config Required: {list(t.config.get('properties', {}).keys())}\n")
```

### Retrieving Active Connected Accounts

Triggers are linked to specific connected accounts (credentials) for a user. You can query the connected accounts from Composio using:

```python
# List connected accounts for user 'user_v55i61letn6c'
res = client.connected_accounts.list(user_ids=["user_v55i61letn6c"])
for account in res.items:
    print(f"Account ID: {account.id} | Toolkit: {account.toolkit.slug} | Status: {account.status}")
```

### The 4-Step Trigger Lifecycle

To run an event-driven workflow, follow this 4-step sequence:

```python
from dotenv import load_dotenv
from composio import Composio

load_dotenv()
client = Composio()
user_id = "user_v55i61letn6c"

# STEP 1: Inspect trigger schema requirements
trigger_type = client.triggers.get_type("TODOIST_NEW_TASK_CREATED")
print("Configuration fields:", trigger_type.config)

# STEP 2: Create/Register the trigger instance
# If no connected_account_id is provided, Composio resolves the active one for the user
trigger = client.triggers.create(
    slug="TODOIST_NEW_TASK_CREATED",
    user_id=user_id,
    trigger_config={"interval": 2} # Optional config parameters
)
print(f"Trigger created successfully. ID: {trigger.trigger_id}")

# STEP 3: Setup subscription
subscription = client.triggers.subscribe()

# STEP 4: Define handler and start wait loop
@subscription.handle(trigger_id=trigger.trigger_id)
def on_todoist_task(data):
    payload = data.get("payload", {})
    content = payload.get("content")
    print(f"New Todoist Task: {content}")

# Blocks thread and routes events
subscription.wait_forever()
```

---

## 3. Practical Cross-App Automation Examples

Here are three complete, production-ready recipe templates to handle multi-app event-driven flows.

### Recipe 1: GitHub Issue opened $\rightarrow$ Slack Notification

**Goal**: When a new issue is opened in a repository, post a summary directly to a Slack channel.

```python
import os
from dotenv import load_dotenv
from composio import Composio

load_dotenv()
client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
user_id = "user_v55i61letn6c"

# 1. Create GitHub trigger instance (Webhook-based)
github_trigger = client.triggers.create(
    slug="GITHUB_ISSUE_CREATED_TRIGGER",
    user_id=user_id,
    trigger_config={
        "owner": "your-github-username",
        "repo": "your-repository-name",
        "state": "open"
    }
)

# 2. Subscribe and wait
subscription = client.triggers.subscribe()

@subscription.handle(trigger_id=github_trigger.trigger_id)
def handle_github_issue(data):
    payload = data.get("payload", {})
    title = payload.get("title")
    author = payload.get("user", {}).get("login", "unknown")
    html_url = payload.get("html_url")
    body = payload.get("body", "No description provided.")
    
    # Send message to Slack channel
    slack_message = (
        f"🚨 *New Issue Opened*\n"
        f"*Title*: {title}\n"
        f"*Author*: {author}\n"
        f"*Link*: {html_url}\n"
        f"> {body[:250]}..."
    )
    
    print(f"Routing GitHub issue event to Slack...")
    client.tools.execute(
        slug="SLACK_CHAT_POST_MESSAGE",
        arguments={
            "channel": "general",
            "markdown_text": slack_message
        },
        user_id=user_id,
        dangerously_skip_version_check=True
    )

subscription.wait_forever()
```

### Recipe 2: Todoist Task created $\rightarrow$ Gmail Draft notification

**Goal**: When a new task is added to Todoist, automatically compose a draft notification email in Gmail.

```python
import os
from dotenv import load_dotenv
from composio import Composio

load_dotenv()
client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
user_id = "user_v55i61letn6c"

# 1. Create Todoist trigger instance
todoist_trigger = client.triggers.create(
    slug="TODOIST_NEW_TASK_CREATED",
    user_id=user_id,
    trigger_config={"interval": 2}
)

# 2. Subscribe and wait
subscription = client.triggers.subscribe()

@subscription.handle(trigger_id=todoist_trigger.trigger_id)
def handle_todoist_task(data):
    payload = data.get("payload", {})
    content = payload.get("content", "Untitled Task")
    priority = payload.get("priority", "Normal")
    due = payload.get("due", {}).get("date", "No due date")
    
    draft_body = (
        f"Hello,\n\n"
        f"A new task has been registered on your Todoist account:\n\n"
        f"- Task: {content}\n"
        f"- Priority: {priority}\n"
        f"- Due: {due}\n\n"
        f"Best,\n"
        f"Automation Engine"
    )
    
    print(f"Todoist task detected. Creating Gmail draft...")
    client.tools.execute(
        slug="GMAIL_CREATE_DRAFT",
        arguments={
            "userId": "me",
            "draft": {
                "message": {
                    "raw": "", # Gmail SDK handles building raw or automatically populates body
                    "subject": f"Reminder: New Todoist Task - {content[:30]}",
                    "snippet": f"Task Created: {content}"
                }
            }
        },
        user_id=user_id,
        dangerously_skip_version_check=True
    )

subscription.wait_forever()
```

### Recipe 3: Gmail email received $\rightarrow$ Slack notification

**Goal**: When an email matching a query (e.g. from a specific sender or containing keywords) is received in Gmail, push a summary to Slack.

```python
import os
from dotenv import load_dotenv
from composio import Composio

load_dotenv()
client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
user_id = "user_v55i61letn6c"

# 1. Create Gmail trigger instance (Polling-based)
gmail_trigger = client.triggers.create(
    slug="GMAIL_NEW_GMAIL_MESSAGE",
    user_id=user_id,
    trigger_config={
        "inbox_id": "me",
        "labels": ["unread"],
        "interval": 2 # check every 2 minutes
    }
)

# 2. Subscribe and wait
subscription = client.triggers.subscribe()

@subscription.handle(trigger_id=gmail_trigger.trigger_id)
def handle_new_email(data):
    payload = data.get("payload", {})
    sender = payload.get("from")
    subject = payload.get("subject", "No Subject")
    preview = payload.get("preview", "")
    
    slack_message = (
        f"✉️ *New Unread Email Received*\n"
        f"*From*: {sender}\n"
        f"*Subject*: {subject}\n"
        f"*Preview*: _{preview}_"
    )
    
    print(f"Incoming email from {sender}. Sending notification to Slack...")
    client.tools.execute(
        slug="SLACK_CHAT_POST_MESSAGE",
        arguments={
            "channel": "general",
            "markdown_text": slack_message
        },
        user_id=user_id,
        dangerously_skip_version_check=True
    )

subscription.wait_forever()
```

---

## 4. Running Triggers in Production

For long-running background tasks, running a blocking `subscription.wait_forever()` directly in your main thread is not recommended. Instead, consider the following architecture options:

### Option A: Standalone Background Worker
Run the script as a system service or container process managed by a process controller like **Supervisor**, or as a daemon inside a Docker container.

### Option B: FastAPI Endpoint (Webhooks Receiver)
Instead of streaming triggers via `subscribe()`, configure an Ingress webhook receiver URL in Composio. This makes your application completely stateless and highly scalable.

```python
import os
from fastapi import FastAPI, Request, Header, HTTPException
from composio import Composio

app = FastAPI()
client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
WEBHOOK_SECRET = os.getenv("COMPOSIO_WEBHOOK_SECRET")

@app.post("/api/webhooks/composio")
async def receive_webhook(
    request: Request,
    webhook_id: str = Header(None, alias="webhook-id"),
    webhook_signature: str = Header(None, alias="webhook-signature"),
    webhook_timestamp: str = Header(None, alias="webhook-timestamp")
):
    body = await request.body()
    body_str = body.decode("utf-8")
    
    try:
        # Verify that the webhook originated from Composio and is authentic
        event = client.triggers.verify_webhook(
            id=webhook_id,
            payload=body_str,
            signature=webhook_signature,
            timestamp=webhook_timestamp,
            secret=WEBHOOK_SECRET
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Unauthorized signature")
        
    print(f"Received verified event: {event.trigger_slug}")
    
    # Route execution logic
    if event.trigger_slug == "GITHUB_ISSUE_CREATED_TRIGGER":
        title = event.payload.get("title")
        # trigger Slack action ...
        
    return {"status": "accepted"}
```
