"""Тесты разбора проблемы и ограничений."""

from __future__ import annotations

from app.hypotheses.problem_input import normalize_problem_constraints


class TestProblemInput:
    def test_keeps_separate_constraints(self):
        p, c = normalize_problem_constraints("Задача KPI", "pH 8-10")
        assert p == "Задача KPI"
        assert c == "pH 8-10"

    def test_extracts_constraints_from_problem(self):
        p, c = normalize_problem_constraints(
            "Повышение извлечения меди. Ограничения: pH 8-10, TRL 4",
            "",
        )
        assert "извлечения меди" in p
        assert "pH 8-10" in c

    def test_multiline_constraints(self):
        p, c = normalize_problem_constraints(
            "Задача\nОграничения: без капвложений",
            "",
        )
        assert p == "Задача"
        assert "капвложений" in c
