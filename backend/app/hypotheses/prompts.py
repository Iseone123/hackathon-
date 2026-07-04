"""Промпты для генерации гипотез."""

from app.hypotheses.prompt_sections import (
    CITATION_RULES,
    build_generation_system,
)

GENERATION_SYSTEM = build_generation_system()

__all__ = ["GENERATION_SYSTEM", "CITATION_RULES", "build_generation_system"]
