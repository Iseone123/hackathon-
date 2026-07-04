"""Чеклист соответствия гипотезы требованиям кейса."""

from __future__ import annotations

import re
from typing import Callable

from app.models import CaseCheckItem, CaseCompliance, Hypothesis

# Обязательные пункты ТЗ (без них — reject)
MANDATORY_CHECKS: list[tuple[str, str]] = [
    ("testable_formulation", "Проверяемая формулировка (конкретная, с параметрами)"),
    ("reasoning", "Обоснование"),
    ("sources", "Ссылки на источники"),
    ("mechanism", "Ожидаемый механизм влияния"),
    ("novelty", "Оценка новизны vs известные решения"),
    ("risks", "Риски: технические и экономические"),
    ("kpi_value", "Ожидаемая ценность / влияние на целевой KPI"),
]

# Опциональные пункты дорожной карты (замечание, не блокируют)
OPTIONAL_CHECKS: list[tuple[str, str]] = [
    ("roadmap_steps", "Дорожная карта: последовательность экспериментов (≥2 шага)"),
    ("roadmap_resources", "Дорожная карта: необходимые ресурсы"),
    ("roadmap_criteria", "Дорожная карта: критерии успеха/провала"),
    ("business_case", "Бизнес-кейс: KPI, ROI, окупаемость"),
]


def _has_specific_params(text: str) -> bool:
    patterns = [
        r"\d+[\.,]?\d*\s*%",
        r"\d+[\.,]?\d*\s*(кг|г|т|мг|л|мл|ppm|°C)\b",
        r"\d+[\.,]?\d*\s*кг\s*/\s*т",
        r"pH\s*\d",
        r"\d+[\.,]?\d*\s*[-–—]\s*\d+",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _kpi_keywords(problem: str) -> list[str]:
    words = re.findall(r"[а-яёa-z]{5,}", problem.lower())
    return words[:8]


def _check_testable_formulation(h: Hypothesis) -> tuple[bool, str]:
    text = f"{h.text} {h.mechanism}".strip()
    if len(h.text.strip()) < 40:
        return False, "Формулировка слишком короткая"
    has_action = bool(
        re.search(
            r"(повысит|повышени|снизит|снижени|улучшит|улучшени|"
            r"обеспечит|позволит|увеличит|оптимизир|"
            r"увеличит|достигнет|обеспечит)",
            text,
            re.IGNORECASE,
        )
    )
    if not has_action:
        return False, "Нет проверяемого утверждения (ожидаемый эффект)"
    if not _has_specific_params(text):
        return False, "Нет конкретных параметров (%, кг/т, pH, режим и т.п.)"
    if re.search(r"\bможет\b", text, re.I) and not re.search(
        r"\d+[\.,]?\d*\s*%", text
    ):
        return False, "Размытая формулировка «может» без количественного эффекта"
    return True, ""


def _check_reasoning(h: Hypothesis) -> tuple[bool, str]:
    if not h.reasoning or len(h.reasoning.strip()) < 40:
        return False, "Обоснование отсутствует или короче 40 символов"
    lowered = h.reasoning.lower()
    if re.search(r"мозгов\w*\s*штурм", lowered):
        return False, "Обоснование без привязки к источникам (мозговой штурм)"
    return True, ""


def _check_sources(h: Hypothesis) -> tuple[bool, str]:
    if not h.sources:
        return False, "Нет ссылок на источники"
    for src in h.sources:
        if src.doc_id and src.doc_id != "unknown" and len(src.snippet.strip()) >= 15:
            return True, ""
    return False, "Источники без doc_id или цитаты"


def _check_mechanism(h: Hypothesis) -> tuple[bool, str]:
    if h.mechanism and len(h.mechanism.strip()) >= 15:
        return True, ""
    return False, "Механизм влияния не описан"


def _check_novelty(h: Hypothesis) -> tuple[bool, str]:
    if not (1 <= h.novelty_score <= 10):
        return False, "Некорректная оценка новизны"
    combined = f"{h.reasoning} {h.text} {h.mechanism}".lower()
    has_comparison = bool(
        re.search(
            r"(новизн|известн|в отличие|аналог|существующ|типов|стандартн|"
            r"согласно|источник|типичн|распростран|в сравнении|отличается)",
            combined,
        )
    )
    if not has_comparison and h.novelty_score < 7:
        return False, "Нет сравнения с известными решениями"
    return True, ""


def _check_risks(h: Hypothesis) -> tuple[bool, str]:
    tech, econ = h.risk.technical, h.risk.economic
    if not (0 <= tech <= 10 and 0 <= econ <= 10):
        return False, "Некорректные оценки риска"
    if tech == 5.0 and econ == 5.0:
        return False, "Риски выглядят как дефолтные (5/5), нужна оценка"
    return True, ""


def _check_kpi_value(h: Hypothesis, problem: str) -> tuple[bool, str]:
    if not (1 <= h.expected_value_score <= 10):
        return False, "Некорректная оценка ценности"
    combined = f"{h.text} {h.reasoning} {h.mechanism}".lower()
    problem_words = _kpi_keywords(problem)
    linked_to_problem = any(w in combined for w in problem_words if len(w) > 5)
    value_markers = bool(
        re.search(
            r"(извлечени|себестоим|прочност|жаропроч|kpi|эффективн|"
            r"повышени|снижени|оптимизац|результат|целев)",
            combined,
            re.IGNORECASE,
        )
    )
    if not linked_to_problem:
        return False, "Нет связи с формулировкой задачи"
    if not value_markers:
        return False, "Нет явной связи с целевым KPI"
    return True, ""


def _roadmap_text(h: Hypothesis) -> str:
    if not h.verification_roadmap:
        return ""
    return " ".join(h.verification_roadmap).lower()


def _check_roadmap_steps(h: Hypothesis) -> tuple[bool, str]:
    if h.verification_roadmap and len(h.verification_roadmap) >= 2:
        return True, ""
    return False, "Меньше 2 шагов экспериментов"


def _check_roadmap_resources(h: Hypothesis) -> tuple[bool, str]:
    text = _roadmap_text(h)
    if not text:
        return False, "Дорожная карта отсутствует"
    if re.search(
        r"(ресурс|оборудован|реагент|лаборатор|персонал|бюджет|установк|"
        r"проб|образец|кг|л\b|мл\b|время|час)",
        text,
        re.IGNORECASE,
    ):
        return True, ""
    return False, "Не указаны ресурсы (оборудование, реагенты, образцы)"


def _check_roadmap_criteria(h: Hypothesis) -> tuple[bool, str]:
    text = _roadmap_text(h)
    if not text:
        return False, "Дорожная карта отсутствует"
    if re.search(
        r"(критери|успех|провал|порог|ожидаем|если\s|при\s+достижен|"
        r"сравнить|контроль|базов|\d+\s*%|процент)",
        text,
        re.IGNORECASE,
    ):
        return True, ""
    return False, "Нет критериев успеха/провала"


def _check_business_case(h: Hypothesis) -> tuple[bool, str]:
    bc = h.business_case
    if not bc:
        return False, "Бизнес-кейс не сформирован"
    if not bc.target_kpi:
        return False, "Не указан целевой KPI"
    if bc.expected_delta_pct is None and bc.annual_revenue_impact_rub is None:
        return False, "Нет количественной оценки эффекта"
    if not bc.narrative or len(bc.narrative) < 40:
        return False, "Нет текстового бизнес-обоснования"
    return True, ""


_CHECKERS: dict[str, Callable[[Hypothesis, str], tuple[bool, str]]] = {
    "testable_formulation": lambda h, p: _check_testable_formulation(h),
    "reasoning": lambda h, p: _check_reasoning(h),
    "sources": lambda h, p: _check_sources(h),
    "mechanism": lambda h, p: _check_mechanism(h),
    "novelty": lambda h, p: _check_novelty(h),
    "risks": lambda h, p: _check_risks(h),
    "kpi_value": lambda h, p: _check_kpi_value(h, p),
    "roadmap_steps": lambda h, p: _check_roadmap_steps(h),
    "roadmap_resources": lambda h, p: _check_roadmap_resources(h),
    "roadmap_criteria": lambda h, p: _check_roadmap_criteria(h),
    "business_case": lambda h, p: _check_business_case(h),
}


def evaluate_case_compliance(h: Hypothesis, problem: str) -> CaseCompliance:
    items: list[CaseCheckItem] = []

    for key, label in MANDATORY_CHECKS:
        passed, note = _CHECKERS[key](h, problem)
        items.append(CaseCheckItem(key=key, label=label, required=True, passed=passed, note=note))

    for key, label in OPTIONAL_CHECKS:
        passed, note = _CHECKERS[key](h, problem)
        items.append(
            CaseCheckItem(key=key, label=label, required=False, passed=passed, note=note)
        )

    mandatory = [i for i in items if i.required]
    optional = [i for i in items if not i.required]
    m_passed = sum(1 for i in mandatory if i.passed)
    o_passed = sum(1 for i in optional if i.passed)
    m_total = len(mandatory)

    return CaseCompliance(
        items=items,
        mandatory_passed=m_passed,
        mandatory_total=m_total,
        optional_passed=o_passed,
        optional_total=len(optional),
        all_mandatory_met=m_passed == m_total,
        compliance_pct=round(100 * m_passed / max(m_total, 1), 1),
    )


def compliance_issues(compliance: CaseCompliance) -> list[str]:
    issues: list[str] = []
    for item in compliance.items:
        if item.required and not item.passed:
            issues.append(f"ТЗ: {item.label} — {item.note or 'не выполнено'}")
    return issues


def compliance_warnings(compliance: CaseCompliance) -> list[str]:
    warnings: list[str] = []
    for item in compliance.items:
        if not item.required and not item.passed:
            warnings.append(f"Рекомендация: {item.label} — {item.note or 'не указано'}")
    return warnings
