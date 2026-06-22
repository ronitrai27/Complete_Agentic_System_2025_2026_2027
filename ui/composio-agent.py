"""
Composio Agent UI — connect integrations, chat with a LangGraph agent.

Run:
    poetry run streamlit run ui/composio-agent.py --server.port 8502
"""
import sys
import threading
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib
if "src.agents.composio_agent" in sys.modules:
    try:
        importlib.reload(sys.modules["src.agents.composio_agent"])
    except Exception:
        pass

import streamlit as st

from src.agents.composio_agent import (
    create_user_session,
    get_connect_url,
    get_toolkit_status,
    run_agent_turn,
    run_agent_turn_stream,
)
from src.config import settings

# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Composio Agent",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide automatic multi-page sidebar navigation so "relationships" page isn't shown
st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

import sqlite3
from datetime import datetime, timezone

def get_or_create_permanent_user_id() -> str:
    db_dir = ROOT / "data"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / "conversations.db"
    
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
        
        cursor.execute("SELECT value FROM user_config WHERE key = 'composio_user_id'")
        row = cursor.fetchone()
        if row:
            return row[0]
        else:
            import random
            import string
            chars = string.ascii_lowercase + string.digits
            new_id = "user_" + "".join(random.choices(chars, k=12))
            
            cursor.execute(
                "INSERT INTO user_config (key, value) VALUES ('composio_user_id', ?)",
                (new_id,)
            )
            conn.commit()
            return new_id
    finally:
        conn.close()


def save_connected_toolkits_to_sqlite(user_id: str, toolkits: list[dict]):
    db_path = ROOT / "data" / "conversations.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS connected_toolkits (
                user_id   TEXT,
                toolkit   TEXT,
                connected INTEGER,
                updated_at TEXT,
                PRIMARY KEY (user_id, toolkit)
            )
        """)
        now = datetime.now(timezone.utc).isoformat()
        for tk in toolkits:
            slug = tk["slug"]
            connected = 1 if tk["connected"] else 0
            cursor.execute("""
                INSERT INTO connected_toolkits (user_id, toolkit, connected, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, toolkit) DO UPDATE SET
                    connected = excluded.connected,
                    updated_at = excluded.updated_at
            """, (user_id, slug, connected, now))
        conn.commit()
    except Exception as exc:
        print(f"[SQLite Toolkit Cache Error] {exc}", flush=True)
    finally:
        conn.close()


def init_state():
    defaults = {
        "user_id": get_or_create_permanent_user_id(),
        "conv_id": str(uuid.uuid4()),
        "messages": [],
        "agent_running": False,
        "connect_url": None,
        "connect_label": None,
        "status_refresh": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()

# ─── Keys check ───────────────────────────────────────────────────────────────

missing_keys = []
if not settings.composio_api_key:
    missing_keys.append("COMPOSIO_API_KEY")
if not (settings.openai_api_key or settings.openai_key):
    missing_keys.append("OPENAI_API_KEY")

if missing_keys:
    st.error(f"Missing env vars: {', '.join(missing_keys)}. Add them to `.env` and restart.")
    st.stop()

# ─── Composio session (per Streamlit user) ───────────────────────────────────

@st.cache_resource
def _cached_session(user_id: str):
    return create_user_session(user_id)


def get_session():
    return _cached_session(st.session_state.user_id)


# ─── Sidebar: integrations ───────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔌 Integrations")
    st.caption("Connect the apps you want the agent to read from.")

    if st.button("🔄 Refresh status", use_container_width=True):
        st.session_state.status_refresh += 1
        _cached_session.clear()
        st.rerun()

    st.divider()

    try:
        session = get_session()
    except Exception as exc:
        err = str(exc)
        if "Invalid API key" in err or "AuthenticationError" in type(exc).__name__:
            st.error(
                "**COMPOSIO_API_KEY is invalid.** Composio rejected it (401). "
                "Generate a fresh key at [Composio Settings](https://platform.composio.dev/settings), "
                "update `.env`, then restart Streamlit."
            )
        else:
            st.error(f"Could not connect to Composio: {exc}")
        st.stop()

    toolkits = get_toolkit_status(session)
    save_connected_toolkits_to_sqlite(st.session_state.user_id, toolkits)

    for tk in toolkits:
        icon = tk["icon"]
        name = tk["name"]
        slug = tk["slug"]
        connected = tk["connected"]
        badge = "🟢 Connected" if connected else "⚪ Not connected"

        with st.container(border=True):
            st.markdown(f"**{icon} {name}**")
            st.caption(badge)
            if not connected:
                if st.button(f"Connect {name}", key=f"connect_{slug}", use_container_width=True):
                    try:
                        url = get_connect_url(session, slug)
                        st.session_state.connect_url = url
                        st.session_state.connect_label = name
                        print(f"\n[Authorization Link] Click here to connect {name}: {url}\n", flush=True)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not start connect flow: {exc}")

    if st.session_state.connect_url:
        st.divider()
        st.markdown(f"### Authorize **{st.session_state.connect_label}**")
        st.link_button(
            "Open authorization page",
            st.session_state.connect_url,
            use_container_width=True,
        )
        st.caption("Complete OAuth in the browser, then click Refresh status.")
        if st.button("Clear link", use_container_width=True):
            st.session_state.connect_url = None
            st.session_state.connect_label = None
            st.rerun()

    st.divider()
    st.caption(f"User ID: `{st.session_state.user_id[:8]}…`")
    if st.button("New conversation", use_container_width=True):
        st.session_state.conv_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# ─── Main chat ────────────────────────────────────────────────────────────────

st.title("🔌 Composio Agent")
st.caption(
    "Connect apps in the sidebar, then ask things like "
    "*Summarize my emails from today* or *What Linear issues are open?*"
)
st.divider()

# High-visibility connection instruction card in the main chat container
if st.session_state.connect_url:
    st.info(f"### 🔐 Authorization Required: **{st.session_state.connect_label}**")
    st.markdown(
        f"Click the button below to link your **{st.session_state.connect_label}** account. "
        f"After authorizing in the new browser tab, click **Refresh status** in the sidebar."
    )
    st.link_button(
        f"🔑 Grant Access / Connect {st.session_state.connect_label}",
        st.session_state.connect_url,
        use_container_width=True,
    )
    st.divider()

for msg in st.session_state.messages:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.write(msg["content"])

user_input = st.chat_input(
    "Ask about your connected apps…",
    disabled=st.session_state.agent_running,
)

if user_input and user_input.strip():
    st.session_state.messages.append({"role": "user", "content": user_input.strip()})
    st.rerun()

needs_response = (
    st.session_state.messages
    and st.session_state.messages[-1]["role"] == "user"
    and not st.session_state.agent_running
)

if needs_response:
    query = st.session_state.messages[-1]["content"]
    conv_id = st.session_state.conv_id
    st.session_state.agent_running = True

    with st.status("Agent thinking…", expanded=True) as status:
        try:
            sess = get_session()
            
            # Print to console for full visibility
            print(f"\n--- [Agent Turn Start] Thread ID: {conv_id} ---", flush=True)
            
            final_ans = "No response from agent."
            # Iterate over the stream of trace events
            import re
            for event in run_agent_turn_stream(sess, st.session_state.messages, conv_id):
                ev_type = event["type"]
                if ev_type == "thought":
                    content = event["content"]
                    st.markdown(f"💭 **Thought:** {content}")
                    print(f"[Agent Thought] {content}", flush=True)
                elif ev_type == "tool_call":
                    name = event["name"]
                    args = event["args"]
                    st.markdown(f"🔧 **Tool Call:** `{name}` with arguments `{args}`")
                    print(f"[Tool Call] {name}({args})", flush=True)
                elif ev_type == "tool_output":
                    name = event["name"]
                    content = event["content"]
                    # Show a nice summary/preview of the output
                    preview = content[:200] + "..." if len(content) > 200 else content
                    st.markdown(f"📦 **Tool Output (`{name}`):**\n```\n{preview}\n```")
                    print(f"[Tool Output] {name} returned: {preview}", flush=True)
                    if "http" in content:
                        urls = re.findall(r'https?://[^\s\)\"\'\]\}]+', content)
                        for u in urls:
                            print(f"\n[Found Auth Link in Tool Output] {u}\n", flush=True)
                elif ev_type == "final_answer":
                    final_ans = event["content"]
                    print(f"[Final Answer] {final_ans}", flush=True)
                    if "http" in final_ans:
                        urls = re.findall(r'https?://[^\s\)\"\'\]\}]+', final_ans)
                        for u in urls:
                            print(f"\n[Found Auth Link in Final Answer] {u}\n", flush=True)
            
            print(f"--- [Agent Turn End] ---\n", flush=True)
            
            status.update(label="Done", state="complete", expanded=False)
            st.session_state.messages.append({
                "role": "assistant",
                "content": final_ans,
            })
        except Exception as exc:
            status.update(label="Failed", state="error")
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"Sorry, something went wrong:\n\n{exc}",
            })
            print(f"[Agent Error] {exc}", flush=True)
        finally:
            st.session_state.agent_running = False

    st.rerun()
