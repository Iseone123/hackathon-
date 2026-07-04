"""Тесты универсального доменного профиля."""

from __future__ import annotations

from app.domain.profile import (
    extract_topic_labels,
    infer_kpi_label,
    kpi_markers_from_problem,
    measurable_param_patterns,
)


def test_infer_kpi_strength():
    assert "прочность" in infer_kpi_label("Повысить прочность композита на 15%")


def test_infer_kpi_polymer():
    assert infer_kpi_label("Reduce manufacturing cost of polymer blend") in (
        "себестоимость",
        "manufacturing",
    ) or "cost" in infer_kpi_label("Reduce manufacturing cost of polymer blend").lower()


def test_domain_parameters_reexport():
    from app.domain import extract_text_parameters, has_measurable_parameters

    params = extract_text_parameters("pH 9 при температуре 720")
    assert params.get("pH") == 9.0
    assert has_measurable_parameters("давление 2.5 МПа при 720 °C")


def test_extract_topic_labels_generic():
    text = "полимерная матрица с углеродными волокнами при термообработке"
    labels = extract_topic_labels(text)
    assert any("полимерн" in l or "углерод" in l or "термообр" in l for l in labels)


def test_kpi_markers_from_problem():
    markers = kpi_markers_from_problem("Повысить жаропрочность сплава на 15%")
    assert any("жаропроч" in m for m in markers)
