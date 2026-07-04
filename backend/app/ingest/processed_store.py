"""Единый доступ к data/processed/*.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from app.config import settings


def _processed_dir() -> Path:
    return settings.processed_dir


def iter_processed_docs(
    *,
    source_dirs: list[str] | None = None,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Итератор по processed JSON; source_dirs — фильтр по подстроке metadata.source."""
    processed = _processed_dir()
    if not processed.exists():
        return

    markers = [d.lower() for d in source_dirs] if source_dirs else None
    count = 0
    for path in sorted(processed.glob("*.json")):
        if limit is not None and count >= limit:
            break
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if markers:
            source = (doc.get("metadata") or {}).get("source", "").lower()
            if not any(m in source for m in markers):
                continue
        count += 1
        yield doc


def load_docs_for_dirs(example_dirs: list[str]) -> list[dict[str, Any]]:
    if not example_dirs:
        return []
    return list(iter_processed_docs(source_dirs=example_dirs))


def processed_catalog() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for doc in iter_processed_docs():
        doc_id = doc.get("id", "")
        if not doc_id:
            continue
        meta = doc.get("metadata") or {}
        catalog[doc_id] = {
            "title": meta.get("title") or doc_id,
            "source_path": meta.get("source") or "",
        }
    return catalog
