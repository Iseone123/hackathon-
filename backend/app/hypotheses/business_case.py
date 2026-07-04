"""Бизнес-кейс и ROI гипотезы, привязка к целевому KPI."""

from __future__ import annotations

import re
from typing import Any

from app.domain.profile import infer_kpi_label
from app.models import BusinessCase, Hypothesis


def _extract_target_kpi(problem: str) -> str:
    return infer_kpi_label(problem)


def _extract_delta_pct(h: Hypothesis, predicted_delta: float | None) -> float | None:
    if predicted_delta is not None:
        return round(max(-5.0, min(15.0, predicted_delta)), 2)
    text = f"{h.text} {h.reasoning}"
    kpi_patterns = [
        r"(?:увелич\w*|повыс\w*|улучш\w*|сниз\w*|increase|improve|reduce)\w*[^.\n]{0,40}?на\s+(\d+(?:[.,]\d+)?)\s*%",
        r"прирост\w*\s*(\d+(?:[.,]\d+)?)\s*%",
        r"Δ\s*(\d+(?:[.,]\d+)?)\s*%",
        r"by\s+(\d+(?:[.,]\d+)?)\s*%",
    ]
    for pat in kpi_patterns:
        match = re.search(pat, text, re.I)
        if match:
            val = float(match.group(1).replace(",", "."))
            if val <= 15:
                return val
    # Не брать первый попавшийся % (плотность 30%, pH и т.д.)
    if h.expected_value_score >= 7:
        return round(2.0 + (h.expected_value_score - 7) * 1.5, 1)
    return None


def _extract_baseline(chunks: list[dict[str, Any]]) -> str | None:
    values: list[float] = []
    for chunk in chunks:
        for pat in [
            r"извлечени\w*\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*%",
            r"recovery\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
            r"strength\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
            r"yield\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
            r"efficien\w*\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*%?",
        ]:
            for m in re.finditer(pat, chunk.get("text", ""), re.I):
                values.append(float(m.group(1).replace(",", ".")))
    if values:
        avg = sum(values) / len(values)
        return f"{avg:.1f} (среднее по базе знаний, n={len(values)})"
    return None


def _estimate_economics(
    delta_pct: float | None,
    constraints: str,
    feasibility: float,
    target_kpi: str,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Упрощённая модель экономического эффекта (руб/год) — масштабируется по KPI."""
    if delta_pct is None or delta_pct <= 0:
        return None, None, None, None, None

    scale = 1.0
    if re.search(r"извлечени|recovery|yield|металл", target_kpi, re.I):
        scale = 1.0
    elif re.search(r"себестоим|cost", target_kpi, re.I):
        scale = 0.7
    else:
        scale = 0.5

    annual_benefit_base = 2_000_000.0 * scale * (delta_pct / 3.0)
    if re.search(r"без\s+капитал", constraints, re.I):
        capex = 150_000.0
    else:
        capex = 800_000.0

    revenue = annual_benefit_base * 0.75
    savings = annual_benefit_base * 0.25
    opex = capex * 0.2 + (10 - feasibility) * 30_000
    annual_benefit = revenue + savings
    payback = (capex / annual_benefit) * 12 if annual_benefit > 0 else None
    roi = (annual_benefit - opex) / capex if capex > 0 else None
    return revenue, savings, capex, payback, roi


def build_business_case(
    h: Hypothesis,
    problem: str,
    constraints: str,
    chunks: list[dict[str, Any]],
    predicted_delta_pct: float | None = None,
    model_confidence: str = "medium",
) -> BusinessCase:
    target_kpi = _extract_target_kpi(problem)
    baseline = _extract_baseline(chunks)
    delta = _extract_delta_pct(h, predicted_delta_pct)
    revenue, savings, capex, payback, roi = _estimate_economics(
        delta, constraints, h.feasibility_score, target_kpi
    )

    narrative_parts = [
        f"Целевой KPI: **{target_kpi}** по задаче «{problem[:80]}».",
    ]
    if baseline:
        narrative_parts.append(f"Базовый уровень по архиву: {baseline}.")
    if delta is not None:
        narrative_parts.append(f"Ожидаемый прирост: **+{delta:.1f} п.п.**")
    if revenue is not None:
        narrative_parts.append(
            f"Оценка экономического эффекта: **{revenue:,.0f} руб/год** (выручка/эффект); "
            f"экономия: **{savings:,.0f} руб/год**."
        )
    if payback is not None and roi is not None:
        narrative_parts.append(
            f"Окупаемость ~**{payback:.0f} мес.**, ROI **{roi:.1f}x** "
            f"(лабораторный TRL, без капвложений — по ограничениям)."
        )
    narrative_parts.append(
        f"Оценка ценности LLM: {h.expected_value_score}/10; "
        f"реализуемость: {h.feasibility_score}/10."
    )

    confidence = model_confidence
    if delta is None or revenue is None:
        confidence = "low"
    elif h.sources and len(h.sources) >= 2:
        confidence = "high" if model_confidence == "medium" else model_confidence

    return BusinessCase(
        target_kpi=target_kpi,
        baseline_value=baseline,
        expected_delta_pct=delta,
        annual_revenue_impact_rub=round(revenue) if revenue else None,
        annual_cost_savings_rub=round(savings) if savings else None,
        implementation_cost_rub=round(capex) if capex else None,
        payback_months=round(payback, 1) if payback else None,
        roi_ratio=round(roi, 2) if roi else None,
        confidence=confidence,
        narrative=" ".join(narrative_parts),
    )
