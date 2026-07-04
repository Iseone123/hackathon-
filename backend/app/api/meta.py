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
    neo4j = status.get("neo4j") or {}
    return {
        "architecture": "RAG + Knowledge Graph (Neo4j) + YandexGPT + Judge",
        "requirements": {
            "ingest_pdf_docx_xlsx_png": True,
            "metadata_support": True,
            "metadata_simplified_isa_tab_allotrope": True,
            "sql_database_import_sqlite_readonly": True,
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
            "export_jira_youtrack_api": False,
            "expert_feedback": True,
            "judge_validation": True,
            "judge_quality_index": True,
            "multilingual_input_ru_en_cn": True,
            "multilingual_output_ru": True,
            "multilingual_output_en_cn": False,
            "auth_rbac_encryption": False,
        },
        "limitations": [
            "Вывод гипотез: русский; источники EN/CN — читать, извлекать знания, переводить в RU (snippet — дословно)",
            "ISA-Tab / Allotrope: упрощённые поля метаданных, не полный импорт стандарта",
            "Jira/YouTrack: экспорт CSV/JSON для импорта, без REST API создания задач",
            "Security: локальный MVP без RBAC и шифрования at rest",
        ],
        "primary_metric": {
            "name": "JQI",
            "description": "Judge Quality Index 0–100 — максимизируем вердикты судьи",
            "target": settings.judge_quality_target,
            "formula": "50% approval_rate + 35% avg_judge_score + 15% source_grounding",
        },
        "index_status": {
            "files_total": status.get("total_files"),
            "files_indexed": status.get("indexed_files"),
            "missing_files": status.get("missing_files"),
            "qdrant_points": status.get("qdrant_points"),
            "neo4j_available": neo4j.get("available", False),
            "neo4j_nodes": neo4j.get("nodes", 0),
            "neo4j_relationships": neo4j.get("relationships", 0),
            "neo4j_publications": neo4j.get("publications", 0),
        },
        "pipeline": [
            "1. Ingest: parse → OCR → chunk → embed → Qdrant + Neo4j",
            "2. RAG: vector + keyword hybrid search + Neo4j subgraph",
            "3. Generate: YandexGPT structured JSON (self-consistency, language=ru)",
            "4. Rank: transparent weighted formula",
            "5. Judge: structure + source grounding + LLM review",
            "6. Export: PDF/DOCX/CSV/JSON + expert feedback",
        ],
    }


@router.get("/demo/examples")
def demo_examples() -> dict[str, Any]:
    return {"examples": demo_examples_payload()}
