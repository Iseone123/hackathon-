"""Проверка соблюдения ограничений задачи."""

from __future__ import annotations

import re

from app.models import Hypothesis


def parse_ph_range(constraints: str) -> tuple[float, float] | None:
    match = re.search(
        r"pH\s*(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)",
        constraints,
        re.IGNORECASE,
    )
    if not match:
        return None
    low = float(match.group(1).replace(",", "."))
    high = float(match.group(2).replace(",", "."))
    return (min(low, high), max(low, high))


def _ranges_overlap(
    a_low: float, a_high: float, b_low: float, b_high: float
) -> bool:
    return max(a_low, b_low) <= min(a_high, b_high)


def extract_ph_ranges(text: str) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for match in re.finditer(
        r"pH\s*(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)",
        text,
        re.IGNORECASE,
    ):
        low = float(match.group(1).replace(",", "."))
        high = float(match.group(2).replace(",", "."))
        ranges.append((min(low, high), max(low, high)))
    return ranges


def extract_ph_values(text: str) -> list[float]:
    """Одиночные значения pH, не входящие в диапазоны вида pH 8-10."""
    range_spans = [
        m.span()
        for m in re.finditer(
            r"pH\s*\d+(?:[.,]\d+)?\s*[-–—]\s*\d+(?:[.,]\d+)?",
            text,
            re.IGNORECASE,
        )
    ]
    values: list[float] = []
    for match in re.finditer(r"pH\s*(\d+(?:[.,]\d+)?)", text, re.IGNORECASE):
        if any(start <= match.start() < end for start, end in range_spans):
            continue
        values.append(float(match.group(1).replace(",", ".")))
    return values


def check_ph_constraints(combined: str, low: float, high: float) -> list[str]:
    issues: list[str] = []
    for r_low, r_high in extract_ph_ranges(combined):
        if not _ranges_overlap(r_low, r_high, low, high):
            issues.append(
                f"Ограничения: диапазон pH {r_low:g}–{r_high:g} "
                f"не пересекается с допустимым {low:g}–{high:g}"
            )
    for value in extract_ph_values(combined):
        if value < low or value > high:
            issues.append(
                f"Ограничения: pH {value:g} вне допустимого диапазона {low:g}–{high:g}"
            )
    return issues


def check_constraints(h: Hypothesis, constraints: str) -> list[str]:
    issues: list[str] = []
    if not constraints:
        return issues

    combined = f"{h.text} {h.mechanism} {h.reasoning}"
    lowered = constraints.lower()

    ph_range = parse_ph_range(constraints)
    if ph_range:
        low, high = ph_range
        issues.extend(check_ph_constraints(combined, low, high))

    if "без капитальных" in lowered or "без капвложений" in lowered:
        if re.search(
            r"(?<!без\s)капитальн.{0,12}вложен|"
            r"(?<!без\s)новое оборудован|строительств|"
            r"магнитн.{0,12}флотац|новая установк",
            combined,
            re.IGNORECASE,
        ):
            issues.append("Ограничения: предложены капитальные вложения")

    if "trl 4" in lowered or "trl4" in lowered:
        if re.search(
            r"промышленн.{0,8}внедрен|пилотн.{0,12}цех|"
            r"на\s+заводе|заводск.{0,8}масштаб|цехов.{0,8}испытан",
            combined,
            re.IGNORECASE,
        ):
            issues.append("Ограничения: уровень TRL выше 4")

    return issues
