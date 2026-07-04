"""Извлечение числовых параметров из текста гипотез и экспериментов."""

from __future__ import annotations

import re

from app.domain.profile import measurable_param_patterns

_TEXT_PARAM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("pH", r"pH\s*[:=]?\s*(\d+(?:\.\d+)?)"),
    ("dosage", r"(\d+(?:\.\d+)?)\s*(?:кг|г|wt\.?%|vol\.?%)\s*/?\s*(?:т|wt)?"),
    ("temperature", r"(?:температур\w*|temperature)\s*[:=]?\s*(\d+(?:\.\d+)?)"),
    ("pressure", r"(?:давлен\w*|pressure)\s*[:=]?\s*(\d+(?:\.\d+)?)"),
    ("metric", r"(?:извлечени\w*|recovery|yield|strength|efficien\w*)\s*[:=]?\s*(\d+(?:\.\d+)?)"),
)


def extract_text_parameters(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for key, pat in _TEXT_PARAM_PATTERNS:
        match = re.search(pat, text, re.I)
        if match:
            found[key] = float(match.group(1).replace(",", "."))
    return found


def has_measurable_parameters(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in measurable_param_patterns())
