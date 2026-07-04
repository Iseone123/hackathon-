"""Тесты единого конфига демо."""

from __future__ import annotations

from app.demo_scenarios import CLI_SCENARIOS, DEMO_SCENARIOS, demo_examples_payload


def test_demo_examples_payload_count():
    payload = demo_examples_payload()
    assert len(payload) == len(DEMO_SCENARIOS)
    assert all("data_path" in p for p in payload)


def test_cli_scenarios_map():
    assert set(CLI_SCENARIOS) == {"1", "2", "3"}
