"""Приоритизация чанков из папок «Пример 1–4» при retrieval."""

from __future__ import annotations

import re
from typing import Any

from app.config import settings


def infer_example_dirs(problem: str, constraints: str = "") -> list[str]:
    """Сопоставляет формулировку задачи с папками эталонных материалов."""
    text = f"{problem} {constraints}".lower()
    dirs: list[str] = []

    if "кгмк" in text:
        dirs.append("Пример 1")
    if "ноф" in text:
        if "вкрапл" in text or "вкр" in text:
            dirs.append("Пример 2")
        else:
            dirs.append("Пример 3")
    if "тоф" in text:
        dirs.append("Пример 4")
    if "хвост" in text and not dirs:
        dirs.extend(["Пример 1", "Пример 2"])

    seen: set[str] = set()
    unique: list[str] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            unique.append(d)
    return unique


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
        return 0.5

    matches = sum(1 for w in kw_lower if w in text_lower)
    kw_score = matches / max(len(kw_lower), 1)

    bonus = 0.0
    for marker in ("извлекаемый металл", "гипотеза", "мозгового штурма", "кмц", "хвост"):
        if marker in text_lower:
            bonus += 0.08

    return min(1.0, kw_score * 0.7 + bonus)


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
        key=lambda h: h.get("example_score", 0.0),
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

    # Примеры — в начало контекста, учебники остаются для механизмов/реагентов
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
