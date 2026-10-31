"""
Root runner for validate_ingestion.py.
Calls scripts.validate_ingestion.run_ingestion_validation().
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_ingestion import run_ingestion_validation

if __name__ == "__main__":
    run_ingestion_validation()
