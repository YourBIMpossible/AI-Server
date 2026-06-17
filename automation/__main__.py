"""Enable `python -m automation <job>`. Ensures the repo root is importable, then dispatches."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for aiserver/rag

from automation.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
