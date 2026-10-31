"""
Automated Pytest Runner for Evaluation Suite.
Can be executed directly via: python eval/run_tests.py
"""

import sys
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

def main():
    test_dir = str(REPO_ROOT / "eval" / "tests")
    args = [test_dir, "-v", "--tb=short"]
    exit_code = pytest.main(args)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
