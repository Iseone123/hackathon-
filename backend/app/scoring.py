"""Прозрачное ранжирование гипотез: взвешенная сумма с раскладкой компонентов.

Скор = Σ w_i · criterion_i (нормировано в 0..1) − штраф за отсутствие grounding.
Новизна: LLM-оценка (первичный сигнал) + косинусная дистанция до корпуса
(вторичный, если есть эмбеддинги): слишком похоже на корпус — не ново.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_WEIGHTS = {"novelty": 0.2, "feasibility": 0.3, "impact": 0.35, "risk": 0.15}
UNGROUNDED_PENALTY = 0.25


def score_hypothesis(h: dict, weights: dict | None = None, corpus_similarity: float | None = None) -> dict:
    """Возвращает скор с полной раскладкой (интерпретируемость)."""
    w = _normalize_weights(weights or DEFAULT_WEIGHTS)
    s = h.get("scores") or {}
    components = {}
    total = 0.0
    for crit, weight in w.items():
        raw = s.get(crit)
        val = (float(raw) - 1) / 4 if raw is not None else 0.5  # 1..5 → 0..1
        # новизна: корректировка близостью к корпусу (similarity > 0.95 = пересказ)
        if crit == "novelty" and corpus_similarity is not None and corpus_similarity > 0.95:
            val = min(val, 0.25)
        contribution = weight * val
        components[crit] = {
            "raw": raw,
            "normalized": round(val, 3),
            "weight": weight,
            "contribution": round(contribution, 3),
        }
        total += contribution

    penalty = 0.0 if h.get("grounded") else UNGROUNDED_PENALTY
    consensus_bonus = 0.02 * (h.get("consensus_count", 1) - 1)  # надёжность self-consistency
    final = max(0.0, min(1.0, total - penalty + consensus_bonus))
    return {
        "final": round(final, 3),
        "components": components,
        "grounding_penalty": penalty,
        "consensus_bonus": round(consensus_bonus, 3),
        "corpus_similarity": corpus_similarity,
    }


def rank(hypotheses: list[dict], weights: dict | None = None, similarities: list[float | None] | None = None) -> list[dict]:
    sims = similarities or [None] * len(hypotheses)
    for h, sim in zip(hypotheses, sims):
        h["ranking"] = score_hypothesis(h, weights, sim)
    return sorted(hypotheses, key=lambda h: -h["ranking"]["final"])


def _normalize_weights(w: dict) -> dict:
    total = sum(max(0.0, float(v)) for v in w.values()) or 1.0
    return {k: max(0.0, float(v)) / total for k, v in w.items() if k in DEFAULT_WEIGHTS}


# ---------- обучение на фидбэке (exponentiated gradient, без переобучения LLM) ----------

def load_weights(store_dir: str) -> dict:
    p = Path(store_dir) / "weights.json"
    if p.exists():
        return json.loads(p.read_text())
    return dict(DEFAULT_WEIGHTS)


def update_weights_from_feedback(store_dir: str, hypothesis: dict, accepted: bool, lr: float = 0.15) -> dict:
    """Принята гипотеза → усиливаем веса критериев, по которым она сильна; отклонена — наоборот."""
    w = load_weights(store_dir)
    s = hypothesis.get("scores") or {}
    sign = 1.0 if accepted else -1.0
    for crit in w:
        raw = s.get(crit)
        if raw is None:
            continue
        strength = (float(raw) - 3) / 2  # −1..1 относительно середины шкалы
        w[crit] = w[crit] * (2.718 ** (lr * sign * strength))
    w = _normalize_weights(w)
    Path(store_dir).mkdir(parents=True, exist_ok=True)
    (Path(store_dir) / "weights.json").write_text(json.dumps(w, ensure_ascii=False, indent=2))
    return w
