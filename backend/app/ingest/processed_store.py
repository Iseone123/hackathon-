"""Единый доступ к data/processed/*.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from app.config import settings
from app.ingest.parser import build_document, parse_file, supported_suffixes
from app.models import DocumentMetadata


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
    docs = list(iter_processed_docs(source_dirs=example_dirs))
    if docs:
        return docs
    return list(_iter_raw_example_docs(example_dirs))


def _iter_raw_example_docs(example_dirs: list[str]) -> Iterator[dict[str, Any]]:
    """Fallback для локальных демо-данных до preindex: DATA_DIR/Пример N/*."""
    suffixes = supported_suffixes()
    for example_dir in example_dirs:
        root = settings.data_dir_path / example_dir
        if not root.exists() or not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                content = parse_file(path)
            except Exception:
                continue
            source = f"{example_dir}/{path.relative_to(root)}"
            yield build_document(
                path,
                content,
                DocumentMetadata(source=source, title=path.name),
            )


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
