#!/usr/bin/env python3
"""CLI for idempotent embedding backfill of existing incident events.

Usage:
    backend/.venv/bin/python scripts/backfill_embeddings.py --incident-id INC-2026-042 --dry-run
    backend/.venv/bin/python scripts/backfill_embeddings.py --incident-id INC-2026-042

The script updates only the ``embedding`` field via MongoDB ``$set``. It never
prints the MongoDB URI or API keys.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.services.embedding_backfill import (  # noqa: E402
    ATLAS_VECTOR_DIMENSIONS,
    BACKFILL_MODES,
    EmbeddingBackfillError,
    EmbeddingBackfillService,
)
from app.services.embeddings import (  # noqa: E402
    EmbeddingDimensionError,
    EmbeddingError,
    create_embedding_provider,
)
from app.services.storage import StorageService  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill missing/invalid embeddings for existing incident events.",
    )
    parser.add_argument(
        "--incident-id",
        default=None,
        help="Only backfill this incident ID (omit to scan the whole collection).",
    )
    parser.add_argument(
        "--mode",
        choices=BACKFILL_MODES,
        default="missing",
        help="missing=only absent/null/empty vectors; invalid=missing+wrong shape; all=re-embed everything.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Events per embedding provider request (default: 64).",
    )
    parser.add_argument(
        "--expected-dimension",
        type=int,
        default=ATLAS_VECTOR_DIMENSIONS,
        help=f"Required Atlas vector dimension (default: {ATLAS_VECTOR_DIMENSIONS}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Audit and select targets without calling the provider or writing data.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    print(f"target_database: {settings.MONGODB_DB_NAME}")
    print(f"embedding_provider: {settings.EMBEDDING_PROVIDER}")
    print(f"embedding_model: {settings.EMBEDDING_MODEL_NAME}")
    print(f"expected_dimension: {args.expected_dimension}")
    print(f"mode: {args.mode}")
    print(f"dry_run: {args.dry_run}")

    storage = StorageService()
    if storage.is_in_memory:
        print(
            "ERROR: MongoDB is not connected (MONGODB_URI missing or connection failed). "
            "Refusing to backfill the in-memory fallback store.",
            file=sys.stderr,
        )
        return 2

    try:
        provider = create_embedding_provider()
        service = EmbeddingBackfillService(
            storage=storage,
            provider=provider,
            expected_dimension=args.expected_dimension,
            batch_size=args.batch_size,
        )
        result = service.run(
            incident_id=args.incident_id,
            mode=args.mode,
            dry_run=args.dry_run,
        )
    except EmbeddingDimensionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "The configured provider/model does not match the Atlas vector index. "
            "Use a 1536-dimension model (for example Gemini gemini-embedding-2 with "
            "EMBEDDING_DIMENSIONS=1536, or OpenAI text-embedding-3-small) or change "
            "the index and expected dimension together.",
            file=sys.stderr,
        )
        return 1
    except (EmbeddingBackfillError, EmbeddingError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), indent=2))
    if args.dry_run:
        print("Dry run complete: no provider calls and no MongoDB writes were made.")
    elif result.eligible == 0:
        print("Nothing to backfill: all selected events already have usable embeddings.")
    else:
        print(
            f"Backfill complete: updated {result.updated}/{result.eligible} events "
            f"({result.failed} failed)."
        )
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
