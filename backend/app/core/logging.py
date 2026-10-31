"""Application logging configuration."""

import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logger with clean stdout formatting."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger("incident_investigator")


logger = setup_logging()
