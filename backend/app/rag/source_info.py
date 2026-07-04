"""Метаданные документов RAG для UI и трассировки источников."""

from __future__ import annotations

from typing import Any

from app.ingest.processed_store import processed_catalog
from app.models import RetrievalSource


def build_retrieval_sources(chunks: list[dict[str, Any]]) -> list[RetrievalSource]:
    catalog = processed_catalog()
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
