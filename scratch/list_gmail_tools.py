import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings
from src.agents.composio_agent import get_composio

def main():
    print("Composio API Key loaded:", bool(settings.composio_api_key))
    comp = get_composio()
    sess = comp.create(user_id="test_user_list", toolkits=["gmail"])
    tools = sess.tools()
    print("Number of tools in Gmail session:", len(tools))
    for i, t in enumerate(tools[:40]):
        name = getattr(t, "name", None) or str(t)
        print(f"{i+1}: {name}")

if __name__ == "__main__":
    main()
