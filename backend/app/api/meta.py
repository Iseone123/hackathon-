"""API: метаданные, compliance, демо."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.demo_scenarios import demo_examples_payload
from app.ingest.index_status import get_index_status

router = APIRouter(tags=["meta"])


@router.get("/compliance")
def compliance_check() -> dict[str, Any]:
    status = get_index_status()
    return {
        "architecture": "RAG + Knowledge Graph (Neo4j) + YandexGPT + Judge",
        "requirements": {
            "ingest_pdf_docx_xlsx_png": True,
            "metadata_support": True,
            "metadata_isa_tab_allotrope": True,
            "sql_database_import": True,
            "knowledge_gap_analysis": True,
            "analogy_counterfactual_predictive": True,
            "ml_predictive_model": True,
            "business_case_roi": True,
            "structured_roadmap_constructor": True,
            "feedback_learning_patterns": True,
            "entity_extraction": True,
            "hypothesis_generation": True,
            "ranking_transparent": True,
            "source_citations": True,
            "influence_graph": True,
            "verification_roadmap": True,
            "export_pdf_docx_csv_json": True,
            "expert_feedback": True,
            "judge_validation": True,
            "judge_quality_index": True,
            "multilingual_ru_en": True,
        },
        "primary_metric": {
            "name": "JQI",
            "description": "Judge Quality Index 0–100 — максимизируем вердикты судьи",
            "target": settings.judge_quality_target,
            "formula": "50% approval_rate + 35% avg_judge_score + 15% source_grounding",
        },
        "index_status": {
            "files_total": status.get("total_files"),
            "files_indexed": status.get("indexed_files"),
            "qdrant_points": status.get("qdrant_points"),
        },
        "pipeline": [
            "1. Ingest: parse → OCR → chunk → embed → Qdrant + Neo4j",
            "2. RAG: vector + keyword hybrid search",
            "3. Generate: YandexGPT structured JSON (self-consistency)",
            "4. Rank: transparent weighted formula",
            "5. Judge: structure + source grounding + LLM review",
            "6. Export: PDF/DOCX/CSV/JSON + expert feedback",
        ],
    }


@router.get("/demo/examples")
def demo_examples() -> dict[str, Any]:
    return {"examples": demo_examples_payload()}
