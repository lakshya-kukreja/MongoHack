"""
Root runner for validate_ingestion.py.
Executes eval/validate_ingestion.py main().
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from eval.validate_ingestion import main

if __name__ == "__main__":
    main()
