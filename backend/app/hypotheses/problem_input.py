"""Разбор поля проблемы: выделение ограничений, если пользователь вписал всё в одно поле."""

from __future__ import annotations

import re

_SPLIT_PATTERNS = [
    re.compile(r"\n\s*ограничени[яй]\s*:\s*", re.IGNORECASE),
    re.compile(r"\n\s*constraints\s*:\s*", re.IGNORECASE),
    re.compile(r"\.\s*ограничени[яй]\s*:\s*", re.IGNORECASE),
    re.compile(r"\.\s*constraints\s*:\s*", re.IGNORECASE),
]


def normalize_problem_constraints(problem: str, constraints: str = "") -> tuple[str, str]:
    """Возвращает (problem, constraints), вытаскивая ограничения из текста проблемы."""
    problem = (problem or "").strip()
    constraints = (constraints or "").strip()
    if constraints:
        return problem, constraints

    for pattern in _SPLIT_PATTERNS:
        match = pattern.search(problem)
        if match:
            extracted = problem[match.end() :].strip()
            clean_problem = problem[: match.start()].strip().rstrip(".")
            if clean_problem and extracted:
                return clean_problem, extracted

    return problem, constraints
