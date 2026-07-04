"""Нормализация и очистка текста после парсинга/OCR."""

from __future__ import annotations

import re


def clean_ocr_text(text: str) -> str:
    """Убирает типичный мусор OCR со схем и сканов."""
    if not text:
        return ""

    text = text.replace("\x0c", "\n")
    text = re.sub(r"[¦|]{2,}", " ", text)
    text = re.sub(r"[^\S\n]+", " ", text)

    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if len(line) < 2:
            continue
        alnum = sum(ch.isalnum() for ch in line)
        ratio = alnum / max(len(line), 1)
        # Строка из спецсимволов — шум
        if ratio < 0.25 and len(line) > 10:
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def normalize_parsed_text(text: str, *, from_ocr: bool = False) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if from_ocr:
        text = clean_ocr_text(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def text_quality_score(text: str) -> float:
    """0..1 — насколько текст пригоден для RAG."""
    if not text or len(text) < 20:
        return 0.0
    alnum = sum(ch.isalnum() or ch.isspace() for ch in text)
    ratio = alnum / len(text)
    words = re.findall(r"[а-яА-Яa-zA-Z]{3,}", text)
    word_density = len(words) / max(len(text) / 50, 1)
    return min(1.0, 0.5 * ratio + 0.5 * min(word_density, 1.0))


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[str]:
    """Режет по абзацам/предложениям, не ломая смысл."""
    text = normalize_parsed_text(text)
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    units = re.split(r"\n\s*\n+", text)
    if len(units) == 1:
        units = re.split(r"(?<=[.!?…])\s+(?=[А-ЯA-Z0-9])", text)

    chunks: list[str] = []
    current = ""

    for unit in units:
        unit = unit.strip()
        if not unit:
            continue
        if len(unit) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            start = 0
            while start < len(unit):
                end = min(start + chunk_size, len(unit))
                piece = unit[start:end].strip()
                if piece:
                    chunks.append(piece)
                if end >= len(unit):
                    break
                start = end - overlap
            continue

        candidate = f"{current}\n\n{unit}".strip() if current else unit
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = unit

    if current:
        chunks.append(current.strip())

    if not chunks:
        return [text[:chunk_size]]

    # Overlap между соседними чанками
    if overlap <= 0 or len(chunks) < 2:
        return chunks

    overlapped: list[str] = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
        merged = f"{prev_tail}\n{chunks[i]}".strip()
        overlapped.append(merged[: chunk_size + overlap])
    return overlapped
