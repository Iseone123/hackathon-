#!/usr/bin/env python3
"""Pre-index demo corpora: Пример 1–4 + Лабораторные опыты.xlsx."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.ingest.index_status import get_index_status  # noqa: E402
from app.ingest.pipeline import IngestPipeline  # noqa: E402
from app.models import DocumentMetadata  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEMO_DIRS = ("Пример 1", "Пример 2", "Пример 3", "Пример 4")
LAB_XLSX = "Лабораторные опыты.xlsx"


def preindex(*, force: bool = False) -> dict:
    pipeline = IngestPipeline()
    results: list[dict] = []

    for dirname in DEMO_DIRS:
        target = settings.data_dir_path / dirname
        if not target.is_dir():
            logger.warning("Skip missing dir: %s", target)
            continue
        logger.info("Indexing directory: %s", dirname)
        try:
            batch = pipeline.ingest_directory(target, only_missing=not force)
            results.extend(batch)
        except Exception as exc:
            logger.error("Failed to index %s: %s", dirname, exc)

    lab_path = settings.data_dir_path / LAB_XLSX
    if lab_path.is_file():
        if force or not _is_indexed(lab_path):
            logger.info("Indexing file: %s", LAB_XLSX)
            meta = DocumentMetadata(
                title=LAB_XLSX,
                source=str(lab_path.relative_to(settings.data_dir_path)),
            )
            try:
                results.append(pipeline.ingest_file(lab_path, meta))
            except Exception as exc:
                logger.error(
                    "Failed to index %s (check YC_API_KEY for embeddings): %s",
                    LAB_XLSX,
                    exc,
                )
        else:
            logger.info("Already indexed: %s", LAB_XLSX)
    else:
        logger.warning("Lab xlsx not found: %s", lab_path)

    status = get_index_status()
    return {
        "ingested_batches": len(results),
        "index_status": {
            "files_total": status["total_files"],
            "files_indexed": status["indexed_files"],
            "missing_files": status["missing_files"],
            "qdrant_points": status["qdrant_points"],
            "neo4j": status.get("neo4j"),
        },
    }


def _is_indexed(path: Path) -> bool:
    from app.ingest.index_status import is_file_indexed

    return is_file_indexed(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-index demo data for hackathon")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if already in processed/",
    )
    args = parser.parse_args()
    summary = preindex(force=args.force)
    neo4j = summary["index_status"].get("neo4j") or {}
    logger.info(
        "Done: indexed %s/%s files, qdrant=%s, neo4j nodes=%s",
        summary["index_status"]["files_indexed"],
        summary["index_status"]["files_total"],
        summary["index_status"]["qdrant_points"],
        neo4j.get("nodes", 0),
    )
    if summary["index_status"]["missing_files"]:
        logger.warning("Still missing %s files", summary["index_status"]["missing_files"])
    if not neo4j.get("available"):
        logger.warning("Neo4j unavailable — graph ingest may have been skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
