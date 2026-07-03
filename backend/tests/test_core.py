"""Юнит-тесты ключевых модулей: парсер, скоринг, JSON-экстракция, экспорт."""
import glob
import os

import pytest

from app import exporter, scoring
from app.llm_client import extract_json
from app.tailings_parser import parse_tailings_xlsx, diagnose

DATA_DIR = os.environ.get(
    "DATA_DIR", "/Users/sereginegor/Downloads/Задача 1. Фабрика гипотез/Задача 1"
)
XLSX_FILES = sorted(glob.glob(f"{DATA_DIR}/**/Хвосты*.xlsx", recursive=True))


# ---------- парсер ----------

@pytest.mark.skipif(not XLSX_FILES, reason="нет исходных Excel")
@pytest.mark.parametrize("path", XLSX_FILES)
def test_parse_real_files(path):
    r = parse_tailings_xlsx(path)
    assert r["sections"], "должна быть хотя бы одна секция хвостов"
    for sec in r["sections"]:
        assert sec["mass_smt"] > 0
        assert len(sec["classes"]) >= 5
        classes = [c["size_class"] for c in sec["classes"]]
        assert len(classes) == len(set(classes)), "классы не дублируются"
    assert r["diagnostics"], "диагностика не пуста"
    assert r["summary_text"]


@pytest.mark.skipif(not XLSX_FILES, reason="нет исходных Excel")
def test_diagnostics_sorted_by_extractable():
    r = parse_tailings_xlsx(XLSX_FILES[0])
    tons = [d["extractable_tons"] or 0 for d in r["diagnostics"]]
    assert tons == sorted(tons, reverse=True)


def test_diagnose_empty():
    assert diagnose({"sections": []}) == []


# ---------- скоринг ----------

def _hyp(scores, grounded=True, consensus=1):
    return {"hypothesis": "x", "scores": scores, "grounded": grounded,
            "consensus_count": consensus}


def test_score_breakdown_sums():
    h = _hyp({"novelty": 5, "feasibility": 5, "impact": 5, "risk": 5})
    r = scoring.score_hypothesis(h)
    assert r["final"] == 1.0
    total = sum(c["contribution"] for c in r["components"].values())
    assert abs(total - 1.0) < 1e-6


def test_ungrounded_penalty():
    good = scoring.score_hypothesis(_hyp({"novelty": 3, "feasibility": 3, "impact": 3, "risk": 3}))
    bad = scoring.score_hypothesis(
        _hyp({"novelty": 3, "feasibility": 3, "impact": 3, "risk": 3}, grounded=False))
    assert good["final"] - bad["final"] == pytest.approx(scoring.UNGROUNDED_PENALTY)


def test_corpus_similarity_caps_novelty():
    h = _hyp({"novelty": 5, "feasibility": 3, "impact": 3, "risk": 3})
    fresh = scoring.score_hypothesis(h, corpus_similarity=0.5)
    stale = scoring.score_hypothesis(h, corpus_similarity=0.99)
    assert stale["final"] < fresh["final"]


def test_rank_orders_desc():
    hyps = [
        _hyp({"novelty": 1, "feasibility": 1, "impact": 1, "risk": 1}),
        _hyp({"novelty": 5, "feasibility": 5, "impact": 5, "risk": 5}),
    ]
    ranked = scoring.rank(hyps)
    assert ranked[0]["ranking"]["final"] >= ranked[1]["ranking"]["final"]


def test_weights_update_from_feedback(tmp_path):
    h = _hyp({"novelty": 5, "feasibility": 1, "impact": 3, "risk": 3})
    w = scoring.update_weights_from_feedback(str(tmp_path), h, accepted=True)
    assert w["novelty"] > scoring.DEFAULT_WEIGHTS["novelty" ] / sum(scoring.DEFAULT_WEIGHTS.values())
    assert abs(sum(w.values()) - 1.0) < 1e-6


# ---------- extract_json ----------

@pytest.mark.parametrize("text,expected_type", [
    ('[{"a": 1}]', list),
    ('```json\n{"a": 1}\n```', dict),
    ('Вот ответ:\n[{"a": 1}, {"b": 2}]\nНадеюсь, помог!', list),
])
def test_extract_json(text, expected_type):
    assert isinstance(extract_json(text), expected_type)


def test_extract_json_garbage():
    with pytest.raises(ValueError):
        extract_json("никакого джейсона тут нет")


# ---------- экспорт ----------

FAKE_RUN = {
    "input_file": "Хвосты Тест.xlsx",
    "goal": "цель", "constraints": "ограничения",
    "summary_text": "### Хвосты породные: 100 т",
    "hypotheses": [{
        "hypothesis": "Заменить насадки гидроциклонов 12 на 8",
        "mechanism": "смещение границы разделения",
        "expected_effect": "возврат 500 т Ni",
        "target": {"element": "Ni", "size_class": "+71"},
        "risks": {"technical": "рост циркуляции", "economic": "износ"},
        "scores": {"novelty": 3, "feasibility": 5, "impact": 4, "risk": 4},
        "grounded": True,
        "sources": [{"ref": 1, "doc_id": "уч. флотации", "page": 10, "snippet": "текст"}],
        "verification_roadmap": ["опыт 1"],
        "ranking": {"final": 0.8, "components": {}},
    }],
}


def test_report_docx_bytes():
    data = exporter.report_docx(FAKE_RUN)
    assert data[:2] == b"PK"  # zip-контейнер docx
    assert len(data) > 5000


def test_tasks_csv_and_json():
    csv_text = exporter.tasks_csv(FAKE_RUN)
    assert "гидроциклон" in csv_text
    import json
    tasks = json.loads(exporter.tasks_json(FAKE_RUN))
    assert tasks[0]["priority"] == "High"
    assert tasks[0]["sources"][0]["page"] == 10
