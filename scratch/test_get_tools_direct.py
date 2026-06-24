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
    
    try:
        for tk in ["gmail", "slack", "reddit"]:
            try:
                tools = comp.tools.get(user_id=user_id, toolkits=[tk])
                print(f"\nToolkit '{tk}' returned {len(tools)} tools:")
                for t in tools[:5]:
                    print(f"  - {t.name}")
            except Exception as e:
                print(f"Error querying toolkit '{tk}': {e}")
    except Exception as exc:
        print("Global error:", exc)

if __name__ == "__main__":
    main()
