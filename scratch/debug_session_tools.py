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
    if not db_path.exists():
        return "none"
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
    
    print("\n--- Test 1: session.tools() without specifying toolkits ---")
    try:
        session = comp.create(
            user_id=user_id,
            manage_connections={"enable": True},
            workbench={"enable": False}
        )
        tools = session.tools()
        print(f"Loaded {len(tools)} tools:")
        for i, t in enumerate(tools[:15]):
            print(f"{i+1}: {t.name}")
    except Exception as exc:
        print("Error Test 1:", exc)
        
    print("\n--- Test 2: comp.tools() (global client tools) ---")
    try:
        tools = comp.tools()
        print(f"Loaded {len(tools)} tools:")
        for i, t in enumerate(tools[:15]):
            print(f"{i+1}: {t.name}")
    except Exception as exc:
        print("Error Test 2:", exc)

if __name__ == "__main__":
    main()
