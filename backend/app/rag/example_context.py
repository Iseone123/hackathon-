"""Приоритизация чанков из папок «Пример N» при retrieval."""

from __future__ import annotations

import re
from typing import Any

from app.config import settings
from app.rag.example_registry import infer_example_dirs as _infer_example_dirs

_KPI_CHUNK_MARKERS = (
    "# kpi-сводка",
    "тег: enterprise_kpi",
    "итого извлекаемый металл в хвостах",
    "отвальные хвосты:",
)


def infer_example_dirs(problem: str, constraints: str = "") -> list[str]:
    return _infer_example_dirs(problem, constraints)


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


def kpi_chunk_boost(text: str) -> float:
    """Бонус для короткого KPI-чанка (enterprise_kpi)."""
    lowered = text.lower().strip()
    if any(marker in lowered for marker in _KPI_CHUNK_MARKERS):
        return 0.25
    return 0.0


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

    ranked = sorted(
        example_hits,
        key=lambda h: (
            kpi_chunk_boost(h.get("text", "")),
            h.get("example_score", 0.0),
        ),
        reverse=True,
    )
    for hit in ranked:
        key = (hit.get("doc_id", ""), hit.get("chunk_index", 0))
        if key in seen:
            continue
        seen.add(key)
        injected.append(hit)
        if len(injected) >= max_inject:
            break

    if not injected:
        return vector_hits

    # KPI и примеры — в начало контекста
    return injected + vector_hits


def extract_brainstorm_topics(text: str) -> list[str]:
    """Ключевые слова из docx гипотез для topic recall."""
    topics: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(?:гипотеза\s+\d+:\s*)?(\d+)\.\s*(.+)$", line, re.I)
        if m:
            topics.append(m.group(2).strip())
    return topics
