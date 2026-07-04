"""Обучение на фидбэке: веса, профили оценок, exemplars и анти-паттерны."""

from __future__ import annotations

import re
from typing import Any

from app.feedback.bandit import (
    load_adjusted_weights,
    update_weights_from_feedback,
    update_weights_from_profiles,
)
from app.feedback.scores import RANKING_CRITERIA, criterion_scores_from_hypothesis, profile_averages
from app.feedback.store import append_log_entry, empty_patterns, load_patterns, save_patterns
from app.models import FeedbackStatus

MAX_EXEMPLARS = 5
MAX_ANTI_PATTERNS = 5


def _extract_keywords(text: str) -> list[str]:
    return re.findall(r"[а-яёa-z]{5,}", text.lower())[:25]


def _update_score_profile(patterns: dict[str, Any], bucket: str, scores: dict[str, float]) -> None:
    profiles = patterns.setdefault("score_profiles", empty_patterns()["score_profiles"])
    slot = profiles.setdefault(bucket, empty_patterns()["score_profiles"]["confirmed"])
    for key, val in scores.items():
        if key not in slot:
            continue
        slot[key]["sum"] += val
        slot[key]["count"] += 1


def _upsert_list_item(
    items: list[dict[str, Any]],
    *,
    match_key: str,
    new_item: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    for item in items:
        if item.get(match_key, "")[:80] == new_item[match_key][:80]:
            item["count"] = item.get("count", 1) + 1
            item.update({k: v for k, v in new_item.items() if k != match_key and v})
            return items[:limit]
    items.insert(0, new_item)
    return items[:limit]


def record_hypothesis_feedback(
    hypothesis_id: str,
    status: FeedbackStatus,
    hypothesis: dict[str, Any] | None = None,
    comment: str = "",
    expert_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = update_weights_from_feedback(status, expert_scores, hypothesis)
    patterns = load_patterns()

    append_log_entry(
        {
            "hypothesis_id": hypothesis_id,
            "status": status.value,
            "comment": comment,
            "text": (hypothesis or {}).get("text", "")[:200],
            "expert_scores": expert_scores,
        }
    )

    if hypothesis:
        text = f"{hypothesis.get('text', '')} {hypothesis.get('mechanism', '')}"
        kw_bucket = (
            patterns["confirmed_keywords"]
            if status == FeedbackStatus.CONFIRMED
            else patterns["rejected_keywords"]
        )
        for kw in _extract_keywords(text):
            kw_bucket[kw] = kw_bucket.get(kw, 0) + 1

        scores = criterion_scores_from_hypothesis(hypothesis)
        if scores:
            bucket = "confirmed" if status == FeedbackStatus.CONFIRMED else "rejected"
            _update_score_profile(patterns, bucket, scores)

        if status == FeedbackStatus.CONFIRMED:
            patterns["confirmed_count"] += 1
            patterns["exemplars"] = _upsert_list_item(
                patterns.setdefault("exemplars", []),
                match_key="text",
                new_item={
                    "text": (hypothesis.get("text") or "")[:220],
                    "mechanism": (hypothesis.get("mechanism") or "")[:120],
                    "count": 1,
                },
                limit=MAX_EXEMPLARS,
            )
        elif status == FeedbackStatus.REJECTED:
            patterns["rejected_count"] += 1
            patterns["anti_patterns"] = _upsert_list_item(
                patterns.setdefault("anti_patterns", []),
                match_key="text",
                new_item={
                    "text": (hypothesis.get("text") or "")[:180],
                    "comment": comment[:200],
                    "count": 1,
                },
                limit=MAX_ANTI_PATTERNS,
            )

    confirmed_avg = profile_averages(patterns.get("score_profiles", {}).get("confirmed", {}))
    rejected_avg = profile_averages(patterns.get("score_profiles", {}).get("rejected", {}))
    if confirmed_avg and rejected_avg:
        weights = update_weights_from_profiles(confirmed_avg, rejected_avg)

    patterns["hints"] = _build_hints(patterns)
    save_patterns(patterns)
    return {"weights": weights, "patterns": patterns}


def _build_hints(patterns: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    for bucket, label in (("confirmed_keywords", "подтверждает"), ("rejected_keywords", "отклоняет")):
        keywords = patterns.get(bucket, {})
        if keywords:
            top = sorted(keywords.items(), key=lambda x: -x[1])[:5]
            prefix = "Эксперт чаще подтверждает гипотезы с темами" if label == "подтверждает" else "Избегайте акцентов на"
            hints.append(f"{prefix}: " + ", ".join(k for k, _ in top))

    profiles = patterns.get("score_profiles", {})
    c_avg = profile_averages(profiles.get("confirmed", {}))
    r_avg = profile_averages(profiles.get("rejected", {}))
    preferred = [
        f"{key} (подтверждённые ~{c_avg[key]:.1f}/10)"
        for key in RANKING_CRITERIA
        if key in c_avg and key in r_avg and c_avg[key] - r_avg[key] >= 1.0
    ]
    if preferred:
        hints.append("Приоритет критериев по фидбэку: " + ", ".join(preferred))

    for ex in (patterns.get("exemplars") or [])[:2]:
        hints.append(f"Пример одобренной формулировки: «{ex.get('text', '')[:120]}…»")
    for anti in (patterns.get("anti_patterns") or [])[:2]:
        note = anti.get("comment") or anti.get("text", "")
        hints.append(f"Анти-паттерн (отклонено): «{note[:100]}»")
    return hints


def get_generation_hints() -> str:
    patterns = load_patterns()
    if patterns.get("confirmed_count", 0) + patterns.get("rejected_count", 0) == 0:
        return ""
    hints = patterns.get("hints") or _build_hints(patterns)
    return (
        "Expert feedback hints (learned from prior reviews):\n" + "\n".join(f"- {h}" for h in hints)
        if hints
        else ""
    )


def get_learned_weights() -> dict[str, float]:
    return load_adjusted_weights()
