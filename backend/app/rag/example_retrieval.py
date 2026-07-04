"""RAG: приоритет чанков из папок «Пример N» + обязательные KPI/brainstorm."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.ingest.brainstorm_topics import dedupe_topics, extract_brainstorm_topics
from app.ingest.kpi import kpi_chunk_boost, kpi_summary_from_doc
from app.ingest.processed_store import load_docs_for_dirs


def example_source_boost(source: str, example_dirs: list[str]) -> float:
    """Дополнительный score для чанков из материалов предприятия."""
    if not example_dirs or not source:
        return 0.0

    src = source.lower()
    boost = 0.0
    base = settings.retrieval_example_boost

    for example_dir in example_dirs:
        marker = example_dir.lower()
        if marker not in src:
            continue
        boost += base
        if "гипотез" in src:
            boost += 0.12
        if src.endswith(".xlsx") or "хвост" in src:
            boost += 0.18
        break

    return boost


def score_example_chunk(text: str, keywords: list[str]) -> float:
    """Релевантность чанка примера к запросу по ключевым словам."""
    if not text:
        return 0.0
    text_lower = text.lower()
    kw_lower = [w.lower() for w in keywords if len(w) >= 4]
    if not kw_lower:
        base = 0.5
    else:
        matches = sum(1 for w in kw_lower if w in text_lower)
        kw_score = matches / max(len(kw_lower), 1)
        base = kw_score * 0.7

    bonus = kpi_chunk_boost(text)
    for marker in ("извлекаемый металл", "гипотеза", "мозгового штурма", "хвост"):
        if marker in text_lower:
            bonus += 0.08

    return min(1.0, base + bonus)


def merge_example_chunks(
    vector_hits: list[dict[str, Any]],
    example_hits: list[dict[str, Any]],
    *,
    max_inject: int,
) -> list[dict[str, Any]]:
    """Вставляет обязательные чанки из примеров, не дублируя doc_id+chunk_index."""
    if not example_hits or max_inject <= 0:
        return vector_hits

    seen: set[tuple[str, int]] = {
        (h.get("doc_id", ""), h.get("chunk_index", 0)) for h in vector_hits
    }
    injected: list[dict[str, Any]] = []

    mandatory = [h for h in example_hits if h.get("mandatory")]
    optional = [h for h in example_hits if not h.get("mandatory")]

    def _inject(hit: dict[str, Any]) -> None:
        key = (hit.get("doc_id", ""), hit.get("chunk_index", 0))
        if key in seen or not hit.get("doc_id"):
            return
        seen.add(key)
        injected.append(hit)

    for hit in sorted(
        mandatory,
        key=lambda h: (
            0 if h.get("mandatory") == "kpi" else 1 if h.get("mandatory") == "brainstorm" else 2,
            -kpi_chunk_boost(h.get("text", "")),
        ),
    ):
        _inject(hit)
        if len(injected) >= max_inject:
            break

    ranked = sorted(
        optional,
        key=lambda h: (
            kpi_chunk_boost(h.get("text", "")),
            h.get("example_score", 0.0),
        ),
        reverse=True,
    )
    for hit in ranked:
        if len(injected) >= max_inject:
            break
        _inject(hit)

    if not injected:
        return vector_hits

    return injected + vector_hits


def _is_brainstorm_doc(doc: dict[str, Any]) -> bool:
    meta = doc.get("metadata") or {}
    blob = f"{meta.get('source', '')} {meta.get('title', '')}".lower()
    return "гипотез" in blob or "brainstorm" in blob


def _is_tailings_xlsx(doc: dict[str, Any]) -> bool:
    source = (doc.get("metadata") or {}).get("source", "").lower()
    return source.endswith(".xlsx") and ("хвост" in source or "tailings" in source)


def _hit_from_doc(
    doc: dict[str, Any],
    *,
    text: str,
    mandatory: str,
    chunk_index: int = 0,
) -> dict[str, Any]:
    meta = doc.get("metadata") or {}
    return {
        "score": 1.0,
        "doc_id": doc.get("id", ""),
        "chunk_index": chunk_index,
        "text": text,
        "title": meta.get("title", ""),
        "source": meta.get("source", ""),
        "from_example": True,
        "mandatory": mandatory,
        "example_score": 1.0,
    }


def build_mandatory_chunks(
    example_dirs: list[str],
    qdrant: Any | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Brainstorm docx + KPI xlsx — всегда в контекст генерации."""
    docs = load_docs_for_dirs(example_dirs)
    topics: list[str] = []
    chunks: list[dict[str, Any]] = []
    seen_doc: set[str] = set()

    for doc in docs:
        doc_id = doc.get("id", "")
        if not doc_id or doc_id in seen_doc:
            continue

        if _is_brainstorm_doc(doc):
            seen_doc.add(doc_id)
            text = doc.get("text", "")
            topics.extend(extract_brainstorm_topics(text))
            chunk_text = text[:1400]
            if qdrant is not None:
                q_hits = qdrant.get_chunks_by_doc(doc_id, [0])
                if q_hits and q_hits[0].get("text"):
                    chunk_text = q_hits[0]["text"][:1400]
            chunks.append(_hit_from_doc(doc, text=chunk_text, mandatory="brainstorm"))

        elif _is_tailings_xlsx(doc):
            seen_doc.add(doc_id)
            kpi_text: str | None = None
            if qdrant is not None:
                q_hits = qdrant.get_chunks_by_doc(doc_id, [0])
                if q_hits and kpi_chunk_boost(q_hits[0].get("text", "")) > 0:
                    kpi_text = q_hits[0]["text"]
            if not kpi_text:
                kpi_text = kpi_summary_from_doc(doc)
            if kpi_text:
                chunks.append(_hit_from_doc(doc, text=kpi_text, mandatory="kpi"))

    ordered = sorted(
        chunks,
        key=lambda c: (c.get("mandatory") != "kpi", c.get("mandatory") != "brainstorm"),
    )
    return dedupe_topics(topics), ordered
