"""ML-модель предсказания KPI по историческим экспериментам (sklearn Ridge)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.domain.parameters import extract_text_parameters
from app.domain.profile import infer_kpi_label
from app.models import Hypothesis

_TARGET_HINTS = (
    "recovery", "yield", "strength", "efficiency", "quality", "result",
    "извлечени", "выход", "прочност", "эффективн", "качеств", "результат",
)
_FEATURE_HINTS = (
    "ph", "dosage", "temperature", "pressure", "concentration", "time",
    "dose", "temp", "concentr", "дозиров", "температур", "давлен", "концентрац",
)


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", key.lower()).strip("_")


def _is_target_key(key: str) -> bool:
    norm = _normalize_key(key)
    return any(h in norm for h in _TARGET_HINTS)


def _is_feature_key(key: str) -> bool:
    norm = _normalize_key(key)
    return any(h in norm for h in _FEATURE_HINTS)


def _record_from_metadata(meta: dict[str, Any], text: str) -> dict[str, float] | None:
    row: dict[str, float] = {}
    for bucket in ("process_parameters", "measurement_results", "experiment_conditions"):
        for key, val in (meta.get(bucket) or {}).items():
            parsed = _parse_float(val)
            if parsed is None:
                continue
            norm = _normalize_key(str(key))
            row[norm] = parsed
    row.update(extract_text_parameters(text))

    targets = [k for k in row if _is_target_key(k)]
    features = [k for k in row if _is_feature_key(k) and k not in targets]
    if not targets:
        # Любое измерение в measurement_results
        for key in (meta.get("measurement_results") or {}):
            norm = _normalize_key(str(key))
            if norm in row:
                targets.append(norm)
    if not targets or not features:
        return None

    target_key = targets[0]
    record = {f"target::{target_key}": row[target_key]}
    for feat in features[:5]:
        record[f"feature::{feat}"] = row[feat]
    return record


def _flatten_records(records: list[dict[str, float]]) -> tuple[list[str], list[str], list[dict[str, float]]] | None:
    """Выбирает наиболее частую целевую метрику и общий набор признаков."""
    target_counts: dict[str, int] = {}
    feature_counts: dict[str, int] = {}
    for rec in records:
        for k in rec:
            if k.startswith("target::"):
                target_counts[k] = target_counts.get(k, 0) + 1
            elif k.startswith("feature::"):
                feature_counts[k] = feature_counts.get(k, 0) + 1
    if not target_counts:
        return None
    target_key = max(target_counts, key=target_counts.get)
    feature_keys = [k for k, c in feature_counts.items() if c >= 2][:5]
    if not feature_keys:
        feature_keys = sorted(feature_counts, key=feature_counts.get, reverse=True)[:3]
    if not feature_keys:
        return None

    flat: list[dict[str, float]] = []
    for rec in records:
        if target_key not in rec:
            continue
        row = {"target": rec[target_key]}
        ok = True
        for fk in feature_keys:
            if fk not in rec:
                ok = False
                break
            row[fk.replace("feature::", "")] = rec[fk]
        if ok:
            flat.append(row)
    if len(flat) < 4:
        return None
    return target_key.replace("target::", ""), [k.replace("feature::", "") for k in feature_keys], flat


class ExperimentPredictor:
    """Ridge-регрессия: target ~ discovered process parameters."""

    def __init__(self) -> None:
        self._model: Any = None
        self._r2: float | None = None
        self._baseline: float | None = None
        self._sample_count = 0
        self._fitted = False
        self._target_name = ""
        self._feature_names: list[str] = []

    @property
    def model_name(self) -> str:
        if self._fitted and self._feature_names:
            feats = ", ".join(self._feature_names[:4])
            return f"sklearn.Ridge ({self._target_name} ~ {feats})"
        return ""

    @property
    def r2(self) -> float | None:
        return self._r2

    @property
    def baseline_recovery(self) -> float | None:
        return self._baseline

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

        flattened = _flatten_records(records)
        if not flattened:
            return False

        target_name, feature_names, flat = flattened
        self._target_name = target_name
        self._feature_names = feature_names

        xs: list[list[float]] = []
        ys: list[float] = []
        for row in flat:
            xs.append([row[f] for f in feature_names])
            ys.append(row["target"])

        x_arr = np.array(xs, dtype=float)
        y_arr = np.array(ys, dtype=float)
        self._baseline = float(np.median(y_arr))
        self._sample_count = len(flat)

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
        feats = extract_text_parameters(text)
        defaults = {"ph": 7.0, "dosage": 0.3, "temperature": 25.0, "pressure": 0.1}
        defaults.update({k.lower(): v for k, v in feats.items()})
        out: dict[str, float] = {}
        for name in self._feature_names:
            norm = _normalize_key(name)
            out[name] = defaults.get(norm, defaults.get(name, 1.0))
        return out

    def predict_for_hypothesis(
        self, h: Hypothesis, baseline_features: dict[str, float] | None = None
    ) -> tuple[float | None, float | None, list[str], str, float]:
        """Возвращает (predicted_value, delta, patterns, notes, score)."""
        if not self._fitted or self._model is None:
            return None, None, [], "ML-модель не обучена (мало исторических экспериментов)", 0.45

        import numpy as np

        model, scaler = self._model
        hyp_feats = self._hypothesis_features(h)
        base = baseline_features or {name: hyp_feats.get(name, 1.0) for name in self._feature_names}

        x_hyp = np.array([[hyp_feats.get(n, 1.0) for n in self._feature_names]])
        x_base = np.array([[base.get(n, 1.0) for n in self._feature_names]])
        pred_hyp = float(model.predict(scaler.transform(x_hyp))[0])
        pred_base = float(model.predict(scaler.transform(x_base))[0])
        baseline = self._baseline or pred_base
        delta = pred_hyp - baseline

        kpi_label = infer_kpi_label(h.text)
        patterns = [
            f"Прогноз {kpi_label}: {pred_hyp:.2f} (гипотеза)",
            f"Базовый режим: {pred_base:.2f}",
            f"Δ к медиане корпуса ({baseline:.2f}): {delta:+.2f}",
        ]
        score = max(0.05, min(0.95, 0.5 + delta / 20.0))
        if self._r2 is not None:
            score = max(0.05, min(0.95, score * (0.5 + 0.5 * max(0, self._r2))))

        notes = (
            f"Ridge R²={self._r2:.2f}, n={self._sample_count}, target={self._target_name}; "
            f"прогноз {pred_hyp:.2f} vs база {pred_base:.2f}"
        )
        return pred_hyp, delta, patterns, notes, score


_predictor: ExperimentPredictor | None = None


def get_predictor() -> ExperimentPredictor:
    global _predictor
    if _predictor is None:
        _predictor = ExperimentPredictor()
        _predictor.fit_from_corpus()
    return _predictor
