"""Параметры генерации гипотез."""

from __future__ import annotations

from app.config import settings


def clamp_hypothesis_count(count: int | None) -> int:
    raw = count if count is not None else settings.default_hypothesis_count
    return max(settings.min_hypothesis_count, min(raw, settings.max_hypothesis_count))
