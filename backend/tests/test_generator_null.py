"""Тесты устойчивости к null-полям от LLM."""

from __future__ import annotations

from app.hypotheses.hypothesis_factory import build_hypothesis_from_raw


class TestGeneratorNullSafety:
    def test_build_hypothesis_handles_null_risk(self):
        raw = {
            "text": "Добавка 0,3% КМЦ при pH 9 повысит извлечение меди из хвостов",
            "mechanism": "КМЦ подавляет пустую породу и улучшает селективность",
            "novelty_score": 7,
            "feasibility_score": 8,
            "expected_value_score": 9,
            "risk": None,
            "sources": [{"doc_id": "doc1", "snippet": "флотация меди"}],
            "verification_roadmap": ["шаг 1", "шаг 2"],
            "reasoning": "обоснование с достаточной длиной для проверки полей",
        }
        chunks = [{"doc_id": "doc1", "text": "флотация меди"}]
        h = build_hypothesis_from_raw(raw, "gen1", 0, chunks)
        assert h.risk.technical == 5.0
