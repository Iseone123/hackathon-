"""Модуль «Судья» — валидация качества гипотез после генерации."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.config import settings
from app.judge.checklist import (
    compliance_issues,
    compliance_warnings,
    evaluate_case_compliance,
)
from app.judge.constraints import check_constraints
from app.judge.metrics import generation_judge_quality_index, hypothesis_objective_score
from app.judge.rationale import build_decision_rationale
from app.llm_client import YandexLLMClient
from app.models import Hypothesis, JudgeSummary, JudgeVerdict

from app.rag.text_overlap import align_snippet_to_corpus, citation_overlap

from app.rag.text_overlap import build_doc_corpus

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = """Ты — строгий независимый эксперт-ревьюер (судья) промышленного НИИ.
Будь консервативен: одобряй только гипотезы, которые явно соответствуют ВСЕМ требованиям.

Отклоняй (approved=false), если есть ЛЮБОЕ из:
- размытая или непроверяемая формулировка (нет измеримых параметров)
- слабое обоснование без привязки к источникам
- механизм не объяснён
- нет связи с целевым KPI/задачей
- источники не подтверждают утверждение
- в roadmap нет ресурсов или критериев успеха/провала
- риски выглядят дефолтными или нереалистичными
- нарушены ограничения задачи

Контекст retrieval может быть на русском, английском, китайском и др. — оценивай по смыслу.

Шкала 0–10: 8+ только при сильных доказательствах; 5–6 = посредственно; ниже 5 = слабо.
НЕ одобряй посредственные гипотезы из вежливости.

Все строки в issues и recommendations — ТОЛЬКО на русском языке.

Ответь ТОЛЬКО JSON:
{
  "approved": true/false,
  "overall_score": 0-10,
  "testability": 0-10,
  "evidence_quality": 0-10,
  "relevance": 0-10,
  "novelty_assessment": 0-10,
  "kpi_link": 0-10,
  "issues": ["замечание на русском"],
  "recommendations": ["рекомендация на русском"],
  "decision_summary": "1-2 предложения: почему одобрил или отклонил"
}
"""


def _snippet_word_overlap(snippet: str, corpus: str) -> float:
    return citation_overlap(snippet, corpus)


class HypothesisJudge:
    """Правила + LLM-судья для проверки гипотез."""

    def __init__(self, llm: YandexLLMClient | None = None) -> None:
        self.llm = llm or YandexLLMClient()

    @property
    def min_approve_score(self) -> float:
        return settings.judge_min_approve_score

    def evaluate_all(
        self,
        hypotheses: list[Hypothesis],
        problem: str,
        constraints: str,
        retrieval_chunks: list[dict[str, Any]],
    ) -> tuple[list[Hypothesis], JudgeSummary]:
        """Оценивает все гипотезы; JQI считается по полному пулу без отбора."""
        chunk_text = "\n".join(c["text"][:600] for c in retrieval_chunks)
        known_doc_ids = {c["doc_id"] for c in retrieval_chunks}
        doc_corpus = build_doc_corpus(retrieval_chunks)

        for i, h in enumerate(hypotheses):
            if i > 0 and settings.llm_request_delay_sec > 0:
                time.sleep(settings.llm_request_delay_sec)
            h.judge_verdict = self._evaluate_one(
                h, problem, constraints, chunk_text, known_doc_ids, doc_corpus
            )

        summary = self._build_summary(hypotheses, problem, constraints, retrieval_chunks)
        return hypotheses, summary

    def select_for_output(
        self,
        hypotheses: list[Hypothesis],
        *,
        min_output: int | None = None,
    ) -> list[Hypothesis]:
        """Все гипотезы: сначала одобренные, затем отклонённые (без скрытия)."""
        del min_output
        ranked = sorted(
            hypotheses,
            key=lambda h: h.judge_verdict.objective_score if h.judge_verdict else 0,
            reverse=True,
        )
        approved = [h for h in ranked if h.judge_verdict and h.judge_verdict.approved]
        rejected = [h for h in ranked if h not in approved]
        return approved + rejected

    # Обратная совместимость для старых вызовов
    def select_for_jqi(
        self,
        hypotheses: list[Hypothesis],
        *,
        min_output: int | None = None,
        drop_below: float | None = None,
    ) -> list[Hypothesis]:
        del drop_below
        return self.select_for_output(hypotheses, min_output=min_output)

    def _evaluate_one(
        self,
        h: Hypothesis,
        problem: str,
        constraints: str,
        chunk_text: str,
        known_doc_ids: set[str],
        doc_corpus: dict[str, str],
    ) -> JudgeVerdict:
        compliance = evaluate_case_compliance(h, problem)
        issues = compliance_issues(compliance)
        issues.extend(check_constraints(h, constraints))
        source_grounded, evidence_issues = self._check_sources(
            h, known_doc_ids, chunk_text, doc_corpus
        )
        issues.extend(evidence_issues)

        llm_verdict = self._llm_review(h, problem, constraints, chunk_text, compliance)
        if not isinstance(llm_verdict, dict):
            llm_verdict = {}

        testability = float(llm_verdict.get("testability", 0))
        evidence = float(llm_verdict.get("evidence_quality", 0))
        relevance = float(llm_verdict.get("relevance", 0))
        novelty_llm = float(llm_verdict.get("novelty_assessment", 0))
        kpi_link = float(llm_verdict.get("kpi_link", 0))

        overall = (
            0.2 * testability
            + 0.2 * evidence
            + 0.2 * relevance
            + 0.15 * novelty_llm
            + 0.15 * kpi_link
            + 0.1 * (10 if source_grounded else 0)
        )
        if issues:
            overall = max(0, overall - len(issues) * settings.judge_issue_penalty)

        llm_approved = bool(llm_verdict.get("approved", False))
        llm_scores_ok = (
            testability >= settings.judge_min_llm_testability
            and evidence >= settings.judge_min_llm_evidence
            and kpi_link >= settings.judge_min_llm_kpi_link
            and relevance >= settings.judge_min_llm_relevance
        )

        approved = bool(
            compliance.all_mandatory_met
            and source_grounded
            and llm_approved
            and llm_scores_ok
            and overall >= self.min_approve_score
            and not any(i.startswith("Ограничения:") for i in issues)
        )

        recommendations = list(llm_verdict.get("recommendations", []))
        recommendations.extend(compliance_warnings(compliance))
        llm_issues = list(llm_verdict.get("issues", []))
        if llm_approved and not llm_scores_ok:
            llm_issues.append(
                "LLM одобрил, но баллы testability/evidence/kpi/relevance ниже порога"
            )

        verdict = JudgeVerdict(
            approved=approved,
            overall_score=round(overall, 2),
            testability=testability,
            evidence_quality=evidence,
            relevance=relevance,
            structure_valid=compliance.all_mandatory_met,
            source_grounded=source_grounded,
            case_compliance=compliance,
            issues=issues + llm_issues,
            recommendations=recommendations,
            judge_notes=str(llm_verdict.get("decision_summary", "")),
        )
        verdict.decision_rationale = build_decision_rationale(
            verdict,
            h,
            llm_summary=str(llm_verdict.get("decision_summary", "")),
        )
        verdict.objective_score = hypothesis_objective_score(verdict)
        return verdict

    def _check_sources(
        self,
        h: Hypothesis,
        known_doc_ids: set[str],
        chunk_text: str,
        doc_corpus: dict[str, str],
    ) -> tuple[bool, list[str]]:
        issues: list[str] = []
        if not h.sources:
            return False, ["Источники: список пуст"]

        min_overlap = settings.judge_snippet_overlap_min
        grounded_count = 0

        for src in h.sources:
            if src.doc_id not in known_doc_ids:
                issues.append(
                    f"Источники: doc_id '{src.doc_id}' не найден в RAG-контексте"
                )
                continue
            if not src.snippet or len(src.snippet.strip()) < 20:
                issues.append(f"Источники: слишком короткая цитата для {src.doc_id}")
                continue

            doc_text = doc_corpus.get(src.doc_id, chunk_text)
            overlap = _snippet_word_overlap(src.snippet, doc_text)
            if overlap >= min_overlap:
                grounded_count += 1
            else:
                issues.append(
                    f"Источники: цитата для {src.doc_id} совпала только на "
                    f"{overlap:.0%} (нужно ≥{min_overlap:.0%})"
                )

        grounded = grounded_count > 0
        if not grounded:
            issues.append("Источники: ни одна цитата не подтверждена retrieval-контекстом")
        return grounded, issues

    def _llm_review(
        self,
        h: Hypothesis,
        problem: str,
        constraints: str,
        chunk_text: str,
        compliance: Any,
    ) -> dict[str, Any]:
        checklist_lines = [
            f"- [{('OK' if i.passed else 'FAIL')}] {i.label}" for i in compliance.items
        ]
        user = (
            f"Целевая задача: {problem}\n"
            f"Ограничения: {constraints or 'нет'}\n\n"
            f"Гипотеза: {h.text}\n"
            f"Механизм: {h.mechanism}\n"
            f"Обоснование: {h.reasoning}\n"
            f"Новизна: {h.novelty_score}/10\n"
            f"Ценность: {h.expected_value_score}/10\n"
            f"Риски: технический={h.risk.technical}, экономический={h.risk.economic}\n"
            f"Источники: {[s.doc_id for s in h.sources]}\n"
            f"Дорожная карта: {h.verification_roadmap}\n\n"
            f"Чеклист ТЗ:\n" + "\n".join(checklist_lines) + "\n\n"
            f"Фрагмент retrieval-контекста (может быть на разных языках):\n{chunk_text[:2000]}\n\n"
            "Ответь на русском языке в полях issues и recommendations."
        )
        try:
            raw = self.llm.complete_lite(JUDGE_SYSTEM, user)
            return self.llm._parse_json(raw)
        except Exception as exc:
            logger.warning("Judge LLM failed: %s", exc)
            return {
                "approved": False,
                "testability": 0,
                "evidence_quality": 0,
                "relevance": 0,
                "novelty_assessment": 0,
                "kpi_link": 0,
                "issues": [f"LLM-судья недоступен: {exc}"],
                "recommendations": ["Экспертная ручная проверка обязательна"],
            }

    def _build_summary(
        self,
        hypotheses: list[Hypothesis],
        problem: str,
        constraints: str,
        chunks: list[dict[str, Any]],
    ) -> JudgeSummary:
        verdicts = [h.judge_verdict for h in hypotheses if h.judge_verdict]
        approved = sum(1 for v in verdicts if v.approved)
        avg = sum(v.overall_score for v in verdicts) / max(len(verdicts), 1)
        jqi_metrics = generation_judge_quality_index(verdicts)
        compliance_pcts = [
            v.case_compliance.compliance_pct
            for v in verdicts
            if v.case_compliance is not None
        ]
        avg_compliance = (
            sum(compliance_pcts) / len(compliance_pcts) if compliance_pcts else 0.0
        )
        output_approved = approved

        notes = [
            f"★ JQI (по всем оценённым гипотезам): {jqi_metrics['jqi']:.1f} / {settings.judge_quality_target:.0f}",
            f"★ Одобрено судьёй: {approved} из {len(verdicts)} ({100 * jqi_metrics['approval_rate']:.0f}%)",
            f"★ Соответствие ТЗ кейса: {avg_compliance:.0f}% обязательных пунктов",
            "✓ Строгие критерии: чеклист + ограничения + overlap цитат ≥30% + пороги LLM",
            "✓ В ответе все гипотезы: одобренные и отклонённые (прозрачность судьи)",
            "✓ RAG-поиск по базе знаний (Qdrant + YandexGPT embeddings)",
            "✓ Независимая валидация модулем «Судья»",
        ]
        if not chunks:
            notes.append("⚠ База знаний пуста — запустите индексацию данных")
        if approved < len(verdicts):
            notes.append(
                f"⚠ {len(verdicts) - approved} гипотез отклонены — требуют доработки экспертом"
            )
        if output_approved < settings.judge_min_output:
            notes.append(
                f"⚠ Одобренных меньше целевого минимума ({settings.judge_min_output})"
            )

        return JudgeSummary(
            total=len(verdicts),
            approved=approved,
            rejected=len(verdicts) - approved,
            avg_score=round(avg, 2),
            jqi=jqi_metrics["jqi"],
            approval_rate=jqi_metrics["approval_rate"],
            avg_objective=jqi_metrics["avg_objective"],
            grounding_rate=jqi_metrics["grounding_rate"],
            objective_target=settings.judge_quality_target,
            avg_case_compliance_pct=round(avg_compliance, 1),
            compliance_notes=notes,
        )
