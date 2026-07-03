"""Smoke-тесты пайплайна без вызова реального API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.generate import Hypothesis, generate_hypotheses, _extract_json_array
from app.ingest import chunk_text, discover_source_files, load_text_from_file
from app.ranking import compute_composite_score, rank_hypotheses
from app.report import render_markdown, save_report
from app.retrieval import RetrievedChunk, build_search_query


SAMPLE_LLM_RESPONSE = """[
  {
    "hypothesis": "LiF-наночастицы стабилизируют границу Li/SSE",
    "mechanism": "Образование стабильного SEI-слоя",
    "sources": ["nanocoatings_patent_landscape.txt"],
    "novelty_score": 7,
    "risk_score": 4,
    "expected_value_score": 8,
    "reasoning": "Подтверждено патентным анализом RU2789012"
  },
  {
    "hypothesis": "Градиентное покрытие LiNbO3/LiPON повышает цикличность",
    "mechanism": "Двухслойная защита катода",
    "sources": ["solid_state_batteries_review.md"],
    "novelty_score": 6,
    "risk_score": 5,
    "expected_value_score": 7,
    "reasoning": "Согласуется с обзором SSE материалов"
  }
]"""


class TestChunking:
    def test_chunk_by_paragraphs(self):
        text = "Первый абзац.\n\nВторой абзац с текстом."
        chunks = chunk_text(text, "demo.txt")
        assert len(chunks) >= 2
        assert all(c.source_file == "demo.txt" for c in chunks)

    def test_long_paragraph_split_with_overlap(self):
        text = "A" * 2000
        chunks = chunk_text(text, "long.txt")
        assert len(chunks) > 1


class TestDemoData:
    def test_demo_files_exist(self):
        files = discover_source_files()
        assert len(files) >= 2

    def test_load_markdown(self):
        files = discover_source_files()
        md_files = [f for f in files if f.suffix == ".md"]
        assert md_files
        content = load_text_from_file(md_files[0])
        assert len(content) > 100


class TestJsonParsing:
    def test_parse_raw_json(self):
        result = _extract_json_array(SAMPLE_LLM_RESPONSE)
        assert len(result) == 2
        assert result[0]["hypothesis"]

    def test_parse_json_in_markdown_fence(self):
        wrapped = f"```json\n{SAMPLE_LLM_RESPONSE}\n```"
        result = _extract_json_array(wrapped)
        assert len(result) == 2


class TestRanking:
    def test_composite_score_ordering(self):
        h1 = Hypothesis("A", "m", novelty_score=9, risk_score=2, expected_value_score=8)
        h2 = Hypothesis("B", "m", novelty_score=5, risk_score=8, expected_value_score=5)
        ranked = rank_hypotheses([h2, h1])
        assert ranked[0].hypothesis == "A"
        assert ranked[0].composite_score > ranked[1].composite_score

    def test_risk_inverted(self):
        low_risk = Hypothesis("low", "m", novelty_score=5, risk_score=2, expected_value_score=5)
        high_risk = Hypothesis("high", "m", novelty_score=5, risk_score=9, expected_value_score=5)
        assert compute_composite_score(low_risk) > compute_composite_score(high_risk)


class TestReport:
    def test_save_report_files(self, tmp_path):
        hypotheses = [
            Hypothesis(
                hypothesis="Test",
                mechanism="Mech",
                sources=["demo.txt"],
                novelty_score=7,
                risk_score=3,
                expected_value_score=8,
                reasoning="Because",
                composite_score=0.75,
            )
        ]
        chunks = [
            RetrievedChunk("id1", "text", "demo.txt", 0, 0.1),
        ]
        json_path, md_path = save_report(
            "Test problem", "budget 1M", hypotheses, chunks, output_dir=tmp_path
        )
        assert json_path.exists()
        assert md_path.exists()
        assert "Test problem" in md_path.read_text(encoding="utf-8")


class TestRetrievalQuery:
    def test_build_search_query(self):
        q = build_search_query("SSE stability", "no cobalt")
        assert "SSE stability" in q
        assert "no cobalt" in q


class TestPipelineMocked:
    @patch("app.main.YandexLLMClient")
    @patch("app.main.retrieve")
    @patch("app.main.generate_hypotheses")
    def test_run_pipeline_does_not_crash(self, mock_gen, mock_retrieve, mock_llm, tmp_path):
        mock_retrieve.return_value = [
            RetrievedChunk("id", "context text", "demo.md", 0, 0.05),
        ]
        mock_gen.return_value = [
            Hypothesis(
                hypothesis="H1",
                mechanism="M1",
                sources=["demo.md"],
                novelty_score=8,
                risk_score=3,
                expected_value_score=9,
                reasoning="R1",
            )
        ]

        from app.main import run_pipeline
        from app import report as report_module

        original_output = report_module.OUTPUT_DIR
        report_module.OUTPUT_DIR = tmp_path
        try:
            result = run_pipeline("Solid-state battery interface", "TRL 3-4")
        finally:
            report_module.OUTPUT_DIR = original_output

        assert len(result["hypotheses"]) == 1
        assert result["hypotheses"][0]["composite_score"] > 0

    @patch("app.generate.YandexLLMClient")
    def test_generate_hypotheses_with_mock_llm(self, mock_llm_cls):
        mock_client = MagicMock()
        mock_client.chat.return_value = SAMPLE_LLM_RESPONSE
        mock_llm_cls.return_value = mock_client

        chunks = [RetrievedChunk("id", "SSE context", "demo.md", 0, 0.1)]
        result = generate_hypotheses("SSE problem", "", chunks, llm=mock_client)
        assert len(result) == 2
        assert result[0].sources
