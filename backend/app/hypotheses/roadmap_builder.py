"""Структурированная дорожная карта верификации с ресурсами и сроками."""

from __future__ import annotations

import re
from typing import Any

from app.models import Hypothesis, RoadmapStep


def _clean_roadmap_step_text(step_text: str) -> str:
    text = re.sub(r"^step\s*\d+\s*:\s*", "", step_text.strip(), flags=re.I)
    text = re.sub(r"^шаг\s*\d+\s*:\s*", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _extract_resources(text: str) -> list[str]:
    resources: list[str] = []
    patterns = [
        r"(\d+(?:[.,]\d+)?\s*(?:кг|г)\s*/?\s*т\s+\w+)",
        r"(лаборатор\w+\s+\w+)",
        r"(флотомашин\w+|ячейк\w+)",
        r"(проб[аы]\s+\d+)",
        r"(реагент\w+)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            val = m.group(1).strip()
            if val and val not in resources:
                resources.append(val)
    return resources[:5]


def _parse_duration(text: str, default: int = 7) -> int:
    m = re.search(r"(\d+)\s*(?:дн|день|дней|week|нед)", text, re.I)
    if m:
        days = int(m.group(1))
        if "нед" in text.lower() or "week" in text.lower():
            days *= 7
        return max(1, min(days, 90))
    return default


def text_step_to_structured(step_text: str, order: int, hypothesis_text: str) -> RoadmapStep:
    step_text = _clean_roadmap_step_text(step_text)
    lowered = step_text.lower()
    resources = _extract_resources(step_text)
    if not resources:
        resources = ["пробы 1 кг", "существующее лабораторное оборудование"]

    success = ""
    failure = ""
    success_match = re.search(r"успех\s*[-–:]\s*([^\.]+)", step_text, re.I)
    if success_match:
        success = success_match.group(1).strip()
    if not success:
        success = "Улучшение целевого KPI ≥3% относительно контроля"
    failure_match = re.search(r"провал\s*[-–:]\s*([^\.]+)", step_text, re.I)
    if failure_match:
        failure = failure_match.group(1).strip()
    elif re.search(r"провал|без изменений|без эффекта", lowered):
        failure = "Отсутствие статистически значимого эффекта vs контроль"
    else:
        failure = "Отсутствие статистически значимого эффекта vs контроль"

    title = step_text[:80] if len(step_text) > 20 else f"Шаг {order}: проверка гипотезы"
    return RoadmapStep(
        step_order=order,
        title=title,
        description=step_text,
        duration_days=_parse_duration(step_text, 7 if order == 1 else 14),
        resources=resources,
        success_criteria=success[:200],
        failure_criteria=failure[:200],
        depends_on=[order - 1] if order > 1 else [],
    )


def build_structured_roadmap(h: Hypothesis) -> list[RoadmapStep]:
    """Строит structured_roadmap из текстовой или с нуля."""
    if h.structured_roadmap:
        return h.structured_roadmap

    steps: list[RoadmapStep] = []
    texts = h.verification_roadmap or []
    if not texts:
        texts = [
            f"Лабораторная проверка: {h.text[:100]}",
            "Сравнение с контрольным режимом на существующем оборудовании",
        ]

    for i, raw in enumerate(texts, 1):
        steps.append(text_step_to_structured(str(raw), i, h.text))

    return steps


def roadmap_to_text(steps: list[RoadmapStep]) -> list[str]:
    lines: list[str] = []
    for s in sorted(steps, key=lambda x: x.step_order):
        title = _clean_roadmap_step_text(s.title)
        desc = _clean_roadmap_step_text(s.description or s.title)
        lines.append(
            f"Шаг {s.step_order}: {title} ({s.duration_days} дн.). "
            f"{desc}. Ресурсы: {', '.join(s.resources)}. "
            f"Успех: {s.success_criteria}. Провал: {s.failure_criteria}"
        )
    return lines


def apply_roadmap_update(h: Hypothesis, steps: list[RoadmapStep]) -> Hypothesis:
    h.structured_roadmap = sorted(steps, key=lambda x: x.step_order)
    h.verification_roadmap = roadmap_to_text(h.structured_roadmap)
    return h


def roadmap_timeline(steps: list[RoadmapStep]) -> list[dict[str, Any]]:
    """Данные для Gantt-визуализации."""
    timeline: list[dict[str, Any]] = []
    cursor = 0
    for s in sorted(steps, key=lambda x: x.step_order):
        timeline.append(
            {
                "step": s.step_order,
                "title": s.title[:40],
                "start_day": cursor,
                "duration_days": s.duration_days,
                "end_day": cursor + s.duration_days,
                "resources": ", ".join(s.resources[:3]),
            }
        )
        cursor += s.duration_days
    return timeline


RESOURCE_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "lab_baseline",
        "label": "Лабораторный контроль",
        "title": "Контрольный опыт на пробах 1 кг",
        "duration_days": 7,
        "resources": ["пробы 1 кг", "лабораторная флотомашина", "реагенты базового режима"],
        "cost_rub": 120_000,
    },
    {
        "id": "reagent_sweep",
        "label": "Подбор дозировки реагента",
        "title": "Серия опытов с варьированием дозировки",
        "duration_days": 14,
        "resources": ["пробы 3×1 кг", "реагент", "анализ проб"],
        "cost_rub": 280_000,
    },
    {
        "id": "ph_matrix",
        "label": "Матрица pH",
        "title": "Оптимизация pH в заданном диапазоне",
        "duration_days": 10,
        "resources": ["пробы 2 кг", "pH-метр", "реагенты регулировки pH"],
        "cost_rub": 190_000,
    },
    {
        "id": "pilot_cell",
        "label": "Пилот на ячейке",
        "title": "Пилотные испытания на промышленной ячейке",
        "duration_days": 21,
        "resources": ["проба 50 кг", "пилотная ячейка", "оператор смены"],
        "cost_rub": 650_000,
    },
    {
        "id": "analytics",
        "label": "Аналитика проб",
        "title": "Химический и granulometric анализ",
        "duration_days": 5,
        "resources": ["10 проб", "ICP/AAS", "гранулометрия"],
        "cost_rub": 85_000,
    },
]


def estimate_step_cost(step: RoadmapStep) -> int:
    """Грубая оценка стоимости шага по длительности и числу ресурсов."""
    base = 15_000 * max(1, step.duration_days // 7)
    resource_bonus = 8_000 * len(step.resources)
    return base + resource_bonus


def summarize_roadmap(steps: list[RoadmapStep]) -> dict[str, Any]:
    """Сводка для конструктора: сроки, ресурсы, оценка бюджета."""
    ordered = sorted(steps, key=lambda x: x.step_order)
    timeline = roadmap_timeline(ordered)
    total_days = timeline[-1]["end_day"] if timeline else 0
    all_resources: list[str] = []
    for s in ordered:
        for r in s.resources:
            if r not in all_resources:
                all_resources.append(r)
    total_cost = sum(estimate_step_cost(s) for s in ordered)
    parallel_groups = len([s for s in ordered if not s.depends_on])
    return {
        "total_days": total_days,
        "step_count": len(ordered),
        "resources_unique": all_resources,
        "estimated_cost_rub": total_cost,
        "timeline": timeline,
        "parallel_entry_points": parallel_groups,
    }


def step_from_template(template_id: str, order: int) -> RoadmapStep | None:
    tpl = next((t for t in RESOURCE_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        return None
    return RoadmapStep(
        step_order=order,
        title=str(tpl["title"]),
        description=str(tpl["title"]),
        duration_days=int(tpl["duration_days"]),
        resources=list(tpl["resources"]),
        success_criteria="Улучшение целевого KPI ≥3% относительно контроля",
        failure_criteria="Отсутствие статистически значимого эффекта vs контроль",
        depends_on=[order - 1] if order > 1 else [],
    )


def reorder_steps(steps: list[RoadmapStep], new_order: list[int]) -> list[RoadmapStep]:
    """Перестановка шагов по списку step_order."""
    by_order = {s.step_order: s for s in steps}
    reordered: list[RoadmapStep] = []
    for i, old_order in enumerate(new_order, 1):
        step = by_order.get(old_order)
        if not step:
            continue
        reordered.append(
            step.model_copy(update={"step_order": i, "depends_on": [i - 1] if i > 1 else []})
        )
    return reordered
