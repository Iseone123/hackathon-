"""Аналогии, контрфактуал и ML-предсказательная оценка гипотез."""

from __future__ import annotations

import re
from typing import Any

from app.domain.parameters import extract_text_parameters
from app.domain.profile import extract_topic_labels, infer_kpi_label
from app.hypotheses.predictive_model import get_predictor
from app.models import Hypothesis, KnowledgeGap, ResearchAnalysis


def _chunk_domains(text: str, doc_id: str) -> set[str]:
    return set(extract_topic_labels(f"{text} {doc_id}"))


def _hypothesis_domains(h: Hypothesis) -> set[str]:
    return set(extract_topic_labels(f"{h.text} {h.mechanism}"))


def _parameter_signature(text: str) -> dict[str, float]:
    return extract_text_parameters(text)


def _find_cross_domain_analogy(
    h: Hypothesis, chunks: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    hyp_domains = _hypothesis_domains(h)
    hyp_sig = _parameter_signature(f"{h.text} {h.mechanism}")

    best: tuple[float, dict[str, Any], set[str]] | None = None
    for chunk in chunks:
        chunk_domains = _chunk_domains(chunk.get("text", ""), chunk.get("doc_id", ""))
        if not chunk_domains:
            continue
        overlap = hyp_domains & chunk_domains
        cross = chunk_domains - hyp_domains
        sig = _parameter_signature(chunk.get("text", ""))
        score = len(overlap) * 2 + len(cross) * 3
        for key in hyp_sig:
            if key in sig and abs(hyp_sig[key] - sig[key]) < max(1.0, hyp_sig[key] * 0.25):
                score += 4
        if best is None or score > best[0]:
            best = (score, chunk, cross)

    if best and best[0] >= 3:
        chunk = best[1]
        cross_labels = sorted(best[2])[:3]
        domain_note = (
            f"перенос из домена «{cross_labels[0]}»"
            if cross_labels
            else "смежный процесс в корпусе"
        )
        sig = _parameter_signature(chunk.get("text", ""))
        param_note = ""
        if sig:
            param_note = ", ".join(f"{k}≈{v}" for k, v in sig.items())
        analogy = (
            f"Cross-domain аналогия ({domain_note}): в {chunk['doc_id'][:36]}… "
            f"описан похожий механизм"
            + (f" ({param_note})" if param_note else "")
            + f" — «{chunk['text'][:140]}…»"
        )
        return analogy, cross_labels or list(hyp_domains)[:2]

    for chunk in chunks[:8]:
        text = chunk.get("text", "")
        for token in re.findall(r"[а-яёa-z]{7,}", f"{h.text} {h.mechanism}".lower()):
            if token in text.lower() and token not in ("извлечение", "повышение", "флотация"):
                return (
                    f"Аналогия по параметру «{token}» в {chunk['doc_id'][:36]}…: "
                    f"«{text[:140]}…»",
                    list(hyp_domains)[:2],
                )

    return (
        f"Аналогия: механизм сопоставим с подходами из корпуса по теме «{infer_kpi_label(h.text)}» "
        "и смежным процессам в базе знаний.",
        list(hyp_domains)[:2] or extract_topic_labels(h.text)[:2] or ["процесс"],
    )


def _build_counterfactual(
    h: Hypothesis,
    problem: str,
    chunks: list[dict[str, Any]],
    baseline_value: float | None,
    predicted_value: float | None,
) -> tuple[str, str]:
    kpi = infer_kpi_label(problem)
    hyp_sig = _parameter_signature(f"{h.text} {h.mechanism}")
    param = "ключевой параметр режима"
    if "pH" in hyp_sig:
        param = f"pH={hyp_sig['pH']}"
    elif "dosage" in hyp_sig:
        param = f"дозировка {hyp_sig['dosage']}"
    elif "temperature" in hyp_sig:
        param = f"температура {hyp_sig['temperature']}"

    baseline_note = ""
    if baseline_value is not None:
        baseline_note = f"медиана {kpi} по архиву {baseline_value:.2f}"
    elif chunks:
        sigs = [_parameter_signature(c.get("text", "")) for c in chunks[:10]]
        metrics = [s["metric"] for s in sigs if "metric" in s]
        if metrics:
            avg = sum(metrics) / len(metrics)
            baseline_note = f"среднее {kpi} в источниках {avg:.2f}"
            baseline_value = avg

    if baseline_value is not None and predicted_value is not None:
        cf = (
            f"Контрфактуал: при сохранении базового режима ({baseline_note}) "
            f"прогноз {kpi} остаётся ~{baseline_value:.2f}; "
            f"при внедрении гипотезы ({param}) ML-модель даёт {predicted_value:.2f} "
            f"(Δ {predicted_value - baseline_value:+.2f}). "
            f"Без изменений KPI по «{problem[:55]}…» не достигается."
        )
        return cf, baseline_note or f"{baseline_value:.2f}"

    cf = (
        f"Контрфактуал: если НЕ менять {param}, сохраняется текущий уровень {kpi} "
        f"по задаче «{problem[:60]}…»"
        + (f" ({baseline_note})" if baseline_note else "")
        + " без целевого прироста."
    )
    return cf, baseline_note or "базовый режим не зафиксирован в архиве"


def build_research_analysis(
    h: Hypothesis,
    problem: str,
    chunks: list[dict[str, Any]],
    gaps: list[KnowledgeGap] | None = None,
) -> ResearchAnalysis:
    predictor = get_predictor()
    pred_recovery, delta, patterns, pred_notes, score = predictor.predict_for_hypothesis(h)

    if pred_recovery is None:
        score = 0.45
        patterns = []
        pred_notes = "Fallback: недостаточно размеченных экспериментов для Ridge"
        for chunk in chunks:
            meta_text = chunk.get("text", "").lower()
            for key, pat in [
                ("pH", r"pH\s*(\d+(?:\.\d+)?)"),
                ("дозировка", r"(\d+(?:\.\d+)?)\s*(?:кг|г)\s*/?\s*т"),
                ("извлечение", r"извлечени\w*\s*(\d+(?:\.\d+)?)\s*%"),
            ]:
                h_match = re.search(pat, f"{h.text} {h.mechanism}", re.I)
                c_match = re.search(pat, meta_text, re.I)
                if h_match and c_match:
                    patterns.append(
                        f"{key}: гипотеза {h_match.group(1)} ~ источник {c_match.group(1)}"
                    )
                    score += 0.1
        score = min(0.85, score)

    if gaps:
        high = sum(1 for g in gaps if g.severity == "high")
        score = max(0.15, score - 0.06 * high)
        pred_notes += f"; пробелов в знаниях: {len(gaps)}"

    analogy, domains = _find_cross_domain_analogy(h, chunks)
    counterfactual, baseline = _build_counterfactual(
        h, problem, chunks, predictor.baseline_recovery, pred_recovery
    )

    return ResearchAnalysis(
        analogy=analogy,
        analogy_domains=domains,
        counterfactual=counterfactual,
        counterfactual_baseline=baseline,
        predictive_score=round(score, 3),
        predictive_notes=pred_notes,
        pattern_matches=patterns,
        model_name=predictor.model_name,
        model_r2=predictor.r2,
        predicted_kpi_delta_pct=round(delta, 2) if delta is not None else None,
    )
