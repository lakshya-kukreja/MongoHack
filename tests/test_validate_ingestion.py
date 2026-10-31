"""
Pytest integration for Ingestion Validation.
Runs all 8 checks for Person 1's Ingestion Pipeline.
"""

from scripts.validate_ingestion import run_ingestion_validation

def test_ingestion_pipeline_validation():
    """Executes the 8-point Ingestion Validation suite."""
    run_ingestion_validation()
