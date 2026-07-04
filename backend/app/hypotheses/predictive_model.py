"""ML-модель предсказания KPI по историческим экспериментам (sklearn Ridge)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import Hypothesis

_FEATURE_KEYS = ("pH", "reagent_dosage", "temperature_C")
_TARGET_KEYS = ("recovery_pct", "Cu_recovery", "yield")


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _extract_from_text(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    patterns = [
        ("pH", r"pH\s*[:=]?\s*(\d+(?:\.\d+)?)"),
        ("reagent_dosage", r"(\d+(?:\.\d+)?)\s*(?:кг|г)\s*/?\s*т"),
        ("temperature_C", r"температур\w*\s*[:=]?\s*(\d+(?:\.\d+)?)"),
        ("recovery_pct", r"извлечени\w*\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%"),
    ]
    for key, pat in patterns:
        match = re.search(pat, text, re.I)
        if match:
            found[key] = float(match.group(1))
    return found


def _record_from_metadata(meta: dict[str, Any], text: str) -> dict[str, float] | None:
    row: dict[str, float] = {}
    for bucket in ("process_parameters", "measurement_results", "experiment_conditions"):
        for key, val in (meta.get(bucket) or {}).items():
            parsed = _parse_float(val)
            if parsed is not None:
                norm = key
                if key in ("Cu_recovery", "yield"):
                    norm = "recovery_pct"
                row.setdefault(norm, parsed)
                if key in _FEATURE_KEYS:
                    row[key] = parsed
    row.update(_extract_from_text(text))
    if "recovery_pct" not in row:
        return None
    if not any(k in row for k in _FEATURE_KEYS):
        return None
    return row


class ExperimentPredictor:
    """Ridge-регрессия: recovery ~ pH + dosage + temperature."""

    def __init__(self) -> None:
        self._model: Any = None
        self._r2: float | None = None
        self._baseline_recovery: float | None = None
        self._sample_count = 0
        self._fitted = False

    @property
    def model_name(self) -> str:
        if self._fitted:
            return "sklearn.Ridge (recovery ~ pH, dosage, temperature)"
        return ""

    @property
    def r2(self) -> float | None:
        return self._r2

    @property
    def baseline_recovery(self) -> float | None:
        return self._baseline_recovery

    def fit_from_corpus(self, processed_dir: Path | None = None) -> bool:
        try:
            import numpy as np
            from sklearn.linear_model import Ridge
            from sklearn.metrics import r2_score
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            return False

        root = processed_dir or settings.processed_dir
        records: list[dict[str, float]] = []
        if root.exists():
            for path in root.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                meta = data.get("metadata") or {}
                text = data.get("text", "")
                row = _record_from_metadata(meta, text)
                if row:
                    records.append(row)

        if len(records) < 4:
            return False

        xs: list[list[float]] = []
        ys: list[float] = []
        for row in records:
            xs.append([
                row.get("pH", 9.0),
                row.get("reagent_dosage", 0.3),
                row.get("temperature_C", 25.0),
            ])
            ys.append(row["recovery_pct"])

        x_arr = np.array(xs, dtype=float)
        y_arr = np.array(ys, dtype=float)
        self._baseline_recovery = float(np.median(y_arr))
        self._sample_count = len(records)

        scaler = StandardScaler()
        x_scaled = scaler.fit_transform(x_arr)
        model = Ridge(alpha=1.0)
        model.fit(x_scaled, y_arr)
        preds = model.predict(x_scaled)
        self._r2 = float(r2_score(y_arr, preds))
        self._model = (model, scaler)
        self._fitted = True
        return True

    def _hypothesis_features(self, h: Hypothesis) -> dict[str, float]:
        text = f"{h.text} {h.mechanism}"
        feats = _extract_from_text(text)
        return {
            "pH": feats.get("pH", 9.0),
            "reagent_dosage": feats.get("reagent_dosage", 0.3),
            "temperature_C": feats.get("temperature_C", 25.0),
        }

    def predict_for_hypothesis(
        self, h: Hypothesis, baseline_features: dict[str, float] | None = None
    ) -> tuple[float | None, float | None, list[str], str, float]:
        """Возвращает (predicted_recovery, delta_pct, patterns, notes, score)."""
        if not self._fitted or self._model is None:
            return None, None, [], "ML-модель не обучена (мало исторических экспериментов)", 0.45

        import numpy as np

        model, scaler = self._model
        hyp_feats = self._hypothesis_features(h)
        base = baseline_features or {"pH": 8.5, "reagent_dosage": 0.5, "temperature_C": 25.0}

        x_hyp = np.array([[hyp_feats["pH"], hyp_feats["reagent_dosage"], hyp_feats["temperature_C"]]])
        x_base = np.array([[base["pH"], base["reagent_dosage"], base["temperature_C"]]])
        pred_hyp = float(model.predict(scaler.transform(x_hyp))[0])
        pred_base = float(model.predict(scaler.transform(x_base))[0])
        baseline = self._baseline_recovery or pred_base
        delta = pred_hyp - baseline

        patterns = [
            f"pH {hyp_feats['pH']} → прогноз извлечения {pred_hyp:.1f}%",
            f"базовый режим pH {base['pH']} → {pred_base:.1f}%",
            f"Δ к медиане корпуса ({baseline:.1f}%): {delta:+.1f} п.п.",
        ]
        score = max(0.05, min(0.95, 0.5 + delta / 20.0))
        if self._r2 is not None:
            score = max(0.05, min(0.95, score * (0.5 + 0.5 * max(0, self._r2))))

        notes = (
            f"Ridge R²={self._r2:.2f}, n={self._sample_count}; "
            f"прогноз {pred_hyp:.1f}% vs база {pred_base:.1f}%"
        )
        return pred_hyp, delta, patterns, notes, score


_predictor: ExperimentPredictor | None = None


def get_predictor() -> ExperimentPredictor:
    global _predictor
    if _predictor is None:
        _predictor = ExperimentPredictor()
        _predictor.fit_from_corpus()
    return _predictor
