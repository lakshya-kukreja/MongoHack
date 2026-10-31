"""
Pytest configuration and shared fixtures for evaluation suite.
"""

import json
import pytest
from pathlib import Path
from eval.adapter import ask

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_CASES_FILE = REPO_ROOT / "eval" / "eval_cases.json"
GROUND_TRUTH_FILE = REPO_ROOT / "data" / "incident_001" / "ground_truth.json"


@pytest.fixture(scope="session")
def eval_cases():
    """Loads the 10 benchmark evaluation cases."""
    with open(EVAL_CASES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def ground_truth():
    """Loads ground truth incident analysis."""
    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def adapter():
    """Provides the unified adapter ask() function."""
    return ask


@pytest.fixture
def default_k():
    """Configurable top-k threshold for retrieval recall."""
    return 5
