"""Человекочитаемое объяснение решения судьи (одобрение / отклонение)."""

from __future__ import annotations

from app.config import settings
from app.models import Hypothesis, JudgeVerdict


def build_decision_rationale(
    verdict: JudgeVerdict,
    hypothesis: Hypothesis,
    *,
    llm_summary: str = "",
) -> list[str]:
    """
    Собирает список причин, почему гипотеза одобрена или отклонена.
    Используется в API и UI — отдельно от reasoning генератора.
    """
    if verdict.approved:
        return _approval_lines(verdict, hypothesis, llm_summary)
    return _rejection_lines(verdict, llm_summary)


def _approval_lines(
    verdict: JudgeVerdict,
    hypothesis: Hypothesis,
    llm_summary: str,
) -> list[str]:
    lines: list[str] = []

    if llm_summary.strip():
        lines.append(llm_summary.strip())

    if verdict.source_grounded:
        lines.append(
            "Цитата из источника подтверждена в RAG-контексте "
            f"(пересечение ≥ {settings.judge_snippet_overlap_min:.0%})"
        )
    if verdict.case_compliance:
        cc = verdict.case_compliance
        lines.append(
            f"Чеклист ТЗ: {cc.mandatory_passed}/{cc.mandatory_total} "
            f"обязательных пунктов ({cc.compliance_pct:.0f}%)"
        )
        for item in cc.items:
            if item.required and item.passed:
                lines.append(f"✓ {item.label}")

    lines.append(
        f"Оценки судьи: проверяемость {verdict.testability:.1f}, "
        f"доказательства {verdict.evidence_quality:.1f}, "
        f"релевантность {verdict.relevance:.1f} "
        f"(пороги ≥ {settings.judge_min_llm_testability})"
    )
    lines.append(
        f"Итоговый балл {verdict.overall_score:.1f}/10 "
        f"(порог одобрения {settings.judge_min_approve_score})"
    )

    if hypothesis.sources:
        src = hypothesis.sources[0]
        snippet_preview = src.snippet.strip()[:80]
        lines.append(f"Опора на источник `{src.doc_id}`: «{snippet_preview}…»")

    return _dedupe(lines)


def _rejection_lines(verdict: JudgeVerdict, llm_summary: str) -> list[str]:
    lines: list[str] = []

    if llm_summary.strip():
        lines.append(llm_summary.strip())

    blocking = [
        i
        for i in verdict.issues
        if i.startswith("Ограничения:")
        or i.startswith("Источники:")
        or "цитата" in i.lower()
        or "overlap" in i.lower()
        or "совпала" in i.lower()
    ]
    if blocking:
        lines.extend(blocking[:8])
    elif verdict.issues:
        lines.extend(verdict.issues[:8])

    if verdict.case_compliance and not verdict.case_compliance.all_mandatory_met:
        for item in verdict.case_compliance.items:
            if item.required and not item.passed:
                suffix = f" — {item.note}" if item.note else ""
                lines.append(f"✗ {item.label}{suffix}")

    if not lines:
        lines.append("Гипотеза не прошла один или несколько критериев судьи (см. замечания)")

    return _dedupe(lines)


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        key = line.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result
