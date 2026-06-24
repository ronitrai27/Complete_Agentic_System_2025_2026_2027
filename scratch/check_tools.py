import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT))

from src.agents.composio_agent import create_user_session

session = create_user_session("test_user_id")
tools = list(session.tools())
print("Tools in session:")
for t in tools:
    print("- ", t.name)
