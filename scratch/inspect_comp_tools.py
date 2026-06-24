import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agents.composio_agent import get_composio

def main():
    comp = get_composio()
    print("Type of comp.tools:", type(comp.tools))
    print("Methods/Properties of comp.tools:")
    print(dir(comp.tools))
    
    # Try calling common retrieval methods if they exist
    for method_name in ["get", "list", "get_tools", "all"]:
        if hasattr(comp.tools, method_name):
            try:
                method = getattr(comp.tools, method_name)
                print(f"\nCalling comp.tools.{method_name}()")
                res = method()
                print(f"Result type: {type(res)}, length/value: {len(res) if hasattr(res, '__len__') else res}")
            except Exception as e:
                print(f"Error calling {method_name}: {e}")

if __name__ == "__main__":
    main()
