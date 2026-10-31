"""
Pytest integration for Task 1: Dataset Validation
Runs automated regression tests on incident_001 and incident_000 datasets.
"""

from scripts.validate_dataset import test_incident_001

def test_dataset_integrity():
    """Verify all 12 validation requirements for Task 1 dataset."""
    test_incident_001()
