"""Статус индексации: какие файлы уже в Qdrant."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.ingest.parser import supported_suffixes


def _indexed_sources() -> dict[str, dict]:
    """source path -> {doc_id, chunks} из data/processed/."""
    indexed: dict[str, dict] = {}
    processed = settings.processed_dir
    if not processed.exists():
        return indexed
    for path in processed.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        source = data.get("metadata", {}).get("source", "")
        if source:
            indexed[source] = {
                "doc_id": data.get("id", path.stem),
                "title": data.get("metadata", {}).get("title", ""),
            }
    return indexed


def list_data_files(directory: Path | None = None) -> list[Path]:
    root = directory or settings.data_dir_path
    suffixes = supported_suffixes()
    skip_dirs = {"processed", "hypotheses", "exports", "qdrant", "minio"}
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix.lower() in suffixes:
            files.append(path)
    return files


def get_index_status(directory: str | None = None) -> dict:
    root = settings.data_dir_path / directory if directory else settings.data_dir_path
    indexed = _indexed_sources()
    files = list_data_files(root)

    indexed_files: list[dict] = []
    missing_files: list[dict] = []

    for path in files:
        rel = str(path.relative_to(settings.data_dir_path))
        entry = {"path": rel, "name": path.name, "size_kb": round(path.stat().st_size / 1024, 1)}
        if rel in indexed:
            entry["doc_id"] = indexed[rel]["doc_id"]
            indexed_files.append(entry)
        else:
            missing_files.append(entry)

    qdrant_points = 0
    try:
        from app.db.qdrant_store import QdrantStore

        qdrant_points = QdrantStore().count_points()
    except Exception:
        pass

    return {
        "total_files": len(files),
        "indexed_files": len(indexed_files),
        "missing_files": len(missing_files),
        "qdrant_points": qdrant_points,
        "indexed": indexed_files,
        "missing": missing_files,
    }


def is_file_indexed(path: Path) -> bool:
    rel = str(path.relative_to(settings.data_dir_path))
    return rel in _indexed_sources()
