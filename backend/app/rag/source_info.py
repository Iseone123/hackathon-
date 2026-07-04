"""Метаданные документов RAG для UI и трассировки источников."""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.models import RetrievalSource


def _load_processed_catalog() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    processed = settings.processed_dir
    if not processed.exists():
        return catalog
    for path in processed.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        doc_id = data.get("id", path.stem)
        meta = data.get("metadata", {})
        catalog[doc_id] = {
            "title": meta.get("title") or path.stem,
            "source_path": meta.get("source") or "",
        }
    return catalog


def build_retrieval_sources(chunks: list[dict[str, Any]]) -> list[RetrievalSource]:
    catalog = _load_processed_catalog()
    by_doc: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        doc_id = chunk["doc_id"]
        entry = by_doc.setdefault(
            doc_id,
            {"chunks": 0, "max_score": 0.0},
        )
        entry["chunks"] += 1
        entry["max_score"] = max(entry["max_score"], float(chunk.get("score", 0)))

    sources: list[RetrievalSource] = []
    for doc_id, stats in sorted(
        by_doc.items(),
        key=lambda x: x[1]["max_score"],
        reverse=True,
    ):
        meta = catalog.get(doc_id, {})
        sources.append(
            RetrievalSource(
                doc_id=doc_id,
                title=meta.get("title") or doc_id,
                source_path=meta.get("source_path") or None,
                chunks_in_context=stats["chunks"],
                max_score=round(stats["max_score"], 4),
            )
        )
    return sources
