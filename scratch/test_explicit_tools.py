import os
import sys
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agents.composio_agent import get_composio
from src.config import settings

def get_permanent_user_id() -> str:
    db_path = ROOT / "data" / "conversations.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM user_config WHERE key = 'composio_user_id'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "none"

def main():
    user_id = get_permanent_user_id()
    print("User ID:", user_id)
    comp = get_composio()
    
    print("\n--- Properties/Methods of Composio client (comp) ---")
    print(dir(comp))
    
    session = comp.create(
        user_id=user_id,
        toolkits=["gmail", "slack", "reddit"],
        manage_connections={"enable": True},
        workbench={"enable": False}
    )
    
    print("\n--- Properties/Methods of Session ---")
    print(dir(session))
    
    print("\n--- Trying session.tools() ---")
    try:
        tools = session.tools()
        print(f"Loaded {len(tools)} tools:")
        for t in tools:
            print(f"- {t.name}")
    except Exception as exc:
        print("Error session.tools():", exc)

if __name__ == "__main__":
    main()
