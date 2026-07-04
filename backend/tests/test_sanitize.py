"""Тесты санитизации и ограничений."""

from __future__ import annotations

from app.hypotheses.sanitize import sanitize_raw_hypothesis
from app.judge.constraints import check_constraints, parse_ph_range
from app.models import Hypothesis, RiskScores, SourceRef


def _chunks():
    return [
        {
            "doc_id": "doc-flotation_0_abc",
            "text": "КМЦ 0,3 кг/т подавляет пустую породу при pH 8-9",
        }
    ]


class TestSanitize:
    def test_rejects_garbage_doc_id(self):
        raw = {
            "text": "Длинная тестовая гипотеза про флотацию меди в хвостах",
            "mechanism": "КМЦ улучшает селективность флотации сульфидов",
            "reasoning": "Источник подтверждает эффект",
            "verification_roadmap": ["Лабораторный тест", "Пилот"],
            "sources": [{"doc_id": "verification_roadmap': [", "snippet": "bad"}],
        }
        cleaned = sanitize_raw_hypothesis(raw, _chunks())
        assert cleaned is not None
        assert cleaned["sources"][0]["doc_id"] == "doc-flotation_0_abc"

    def test_rejects_incomplete(self):
        raw = {"text": "коротко", "mechanism": "x"}
        assert sanitize_raw_hypothesis(raw, _chunks()) is None

    def test_relax_saves_minimal_hypothesis(self):
        from app.hypotheses.sanitize import relax_raw_hypothesis

        raw = {
            "text": "КМЦ повысит извлечение меди при pH 9",
            "mechanism": "подавление пустой породы",
        }
        relaxed = relax_raw_hypothesis(raw, _chunks())
        assert relaxed is not None
        assert len(relaxed["verification_roadmap"]) >= 2
        assert relaxed["sources"]


class TestConstraints:
    def test_parse_ph(self):
        assert parse_ph_range("pH 8-10, TRL 4") == (8.0, 10.0)

    def test_ph_violation(self):
        h = Hypothesis(
            id="h1",
            text="Селективная флотация при pH 12 повысит извлечение",
            mechanism="Подавление пирита в щелочной среде",
            novelty_score=6,
            feasibility_score=7,
            expected_value_score=8,
            risk=RiskScores(technical=5, economic=4),
            sources=[SourceRef(doc_id="d1", snippet="флотация")],
            verification_roadmap=["шаг1", "шаг2"],
            reasoning="обоснование достаточной длины для проверки",
        )
        issues = check_constraints(h, "pH 8-10, без капитальных вложений")
        assert any("pH" in i for i in issues)

    def test_ph_range_overlap_allowed(self):
        from app.judge.constraints import check_ph_constraints

        assert not check_ph_constraints("флотация при pH 7,5-9 в слабощелочной среде", 8.0, 10.0)

    def test_ph_range_no_overlap(self):
        from app.judge.constraints import check_ph_constraints

        issues = check_ph_constraints("режим при pH 5-6", 8.0, 10.0)
        assert issues

    def test_no_false_capital_from_compliance_phrase(self):
        h = Hypothesis(
            id="h2",
            text="Добавление КМЦ 0,3 кг/т при pH 8-10, без капитальных вложений, лабораторно",
            mechanism="Подавление пустой породы",
            novelty_score=6,
            feasibility_score=7,
            expected_value_score=8,
            risk=RiskScores(technical=4, economic=3),
            sources=[SourceRef(doc_id="d1", snippet="КМЦ 0,3 кг/т")],
            verification_roadmap=["шаг1", "шаг2"],
            reasoning="обоснование достаточной длины для проверки источником",
        )
        issues = check_constraints(h, "pH 8-10, без капитальных вложений, TRL 4")
        assert not any("капитальн" in i for i in issues)

    def test_no_false_trl_from_source_quote(self):
        h = Hypothesis(
            id="h3",
            text="Добавление 4-6 кг/т сернокислого железа при pH 8-10 повысит извлечение на ≥3%",
            mechanism="Снижение щёлочности пульпы",
            novelty_score=6,
            feasibility_score=7,
            expected_value_score=8,
            risk=RiskScores(technical=4, economic=3),
            sources=[SourceRef(doc_id="d1", snippet="добавлением 4—6 кг/т сернокислого железа")],
            verification_roadmap=["шаг1", "шаг2"],
            reasoning="Источник указывает метод снижения pH добавлением сернокислого железа на металлургических заводах",
        )
        issues = check_constraints(h, "pH 8-10, TRL 4")
        assert not any("TRL" in i for i in issues)
