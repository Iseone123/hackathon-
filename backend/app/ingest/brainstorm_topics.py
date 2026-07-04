"""Парсинг направлений мозгового штурма из docx/processed."""

from __future__ import annotations

import re


def parse_numbered_line(line: str) -> tuple[str, str] | None:
    """Извлекает номер и текст: '1. …', '2) …', '| 1. … |'."""
    stripped = line.strip()
    if not stripped:
        return None

    m = re.match(r"^(?:\d+\.\s*|\d+\)\s*)(.+)$", stripped)
    if m:
        num = re.match(r"^(\d+)", stripped)
        return (num.group(1), m.group(1).strip()) if num else None

    m = re.match(r"^##\s*(?:Гипотеза|Пункт)\s+(\d+):\s*(.+)$", stripped, re.I)
    if m:
        return m.group(1), m.group(2).strip()

    if "|" in stripped:
        for cell in (c.strip() for c in stripped.split("|") if c.strip()):
            m2 = re.match(r"^(\d+)\.\s*(.+)$", cell)
            if m2:
                return m2.group(1), m2.group(2).strip()
    return None


def extract_brainstorm_topics(text: str) -> list[str]:
    """Направления из docx: нумерованные строки и ## Гипотеза N: …"""
    topics: list[str] = []
    for line in text.splitlines():
        parsed = parse_numbered_line(line)
        if parsed:
            topics.append(parsed[1])
    return topics


def dedupe_topics(topics: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        key = topic.lower()
        if key not in seen:
            seen.add(key)
            unique.append(topic)
    return unique
