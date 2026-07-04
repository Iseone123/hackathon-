"""Вспомогательные функции ingest для API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.demo_scenarios import AUTO_INGEST_DIRS
from app.ingest.pipeline import IngestPipeline


def summarize_ingest_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    ingested = sum(1 for r in results if r.get("chunks_indexed", 0) > 0)
    skipped = sum(1 for r in results if r.get("skipped"))
    errors = sum(1 for r in results if r.get("error"))
    return {
        "processed": len(results),
        "ingested": ingested,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }


def run_auto_ingest(
    pipeline: IngestPipeline,
    directories: list[str] | None = None,
) -> dict[str, Any]:
    dirs = directories or list(AUTO_INGEST_DIRS)
    all_results: list[dict] = []
    for d in dirs:
        target = settings.data_dir_path / d
        if target.exists():
            all_results.extend(pipeline.ingest_directory(target, only_missing=True))
    return {
        "directories": dirs,
        "processed": len(all_results),
        "ingested": sum(1 for r in all_results if r.get("chunks_indexed", 0) > 0),
    }


def resolve_data_directory(directory: str) -> Path:
    target = settings.data_dir_path / directory
    if not target.exists():
        raise FileNotFoundError(f"Папка не найдена: {target}")
    return target
