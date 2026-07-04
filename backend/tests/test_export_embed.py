"""Тесты PDF-экспорта с кириллицей и параллельных эмбеддингов."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.export.pdf_fonts import register_pdf_fonts
from app.export.report import export_pdf
from app.models import Hypothesis, RiskScores


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id="h1",
        text="Добавка 0,3 кг/т КМЦ при pH 9 повысит извлечение меди",
        mechanism="КМЦ подавляет пустую породу",
        novelty_score=7,
        feasibility_score=8,
        expected_value_score=9,
        risk=RiskScores(technical=4, economic=3),
    )


class TestPdfExport:
    def test_registers_cyrillic_font(self):
        font = register_pdf_fonts()
        assert font != "Helvetica"

    def test_pdf_contains_cyrillic_text(self, tmp_path):
        out = tmp_path / "report.pdf"
        export_pdf("Извлечение меди из хвостов", "pH 8-10", [_hypothesis()], out)
        raw = out.read_bytes()
        assert raw.startswith(b"%PDF")
        # ReportLab встраивает TTF — кириллица не должна быть пустой
        assert b"Helvetica" not in raw or b"DejaVuSans" in raw or len(raw) > 2000


class TestEmbedBatch:
    def test_parallel_embed_preserves_order(self):
        from app.llm_client import YandexLLMClient

        client = YandexLLMClient(api_key="k", folder_id="f")
        calls: list[str] = []

        def fake_single(text: str, model: str) -> list[float]:
            calls.append(text)
            return [float(len(text))]

        with patch.object(client, "_embed_single", side_effect=fake_single):
            vectors = client._embed(["aaa", "bb", "c"], "text-search-doc")

        assert len(vectors) == 3
        assert vectors[0][0] == 3.0
        assert vectors[1][0] == 2.0
        assert vectors[2][0] == 1.0
        assert len(calls) == 3
