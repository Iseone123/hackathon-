"""Хранение и загрузка гипотез."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models import Hypothesis


def load_generation(generation_id: str) -> dict | None:
    path = settings.hypotheses_dir / f"{generation_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_hypothesis(hypothesis_id: str) -> Hypothesis | None:
    for path in settings.hypotheses_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for raw in data.get("hypotheses", []):
            if raw.get("id") == hypothesis_id:
                return Hypothesis.model_validate(raw)
    return None


def update_hypothesis(hypothesis_id: str, updated: Hypothesis) -> bool:
    for path in settings.hypotheses_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        hyps = data.get("hypotheses", [])
        for i, raw in enumerate(hyps):
            if raw.get("id") == hypothesis_id:
                hyps[i] = updated.model_dump(mode="json")
                changed = True
                break
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            return True
    return False


def list_generations() -> list[str]:
    if not settings.hypotheses_dir.exists():
        return []
    return [p.stem for p in settings.hypotheses_dir.glob("*.json")]
