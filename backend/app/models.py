"""Pydantic-модели API и домена."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FeedbackStatus(str, Enum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class IsaTabRecord(BaseModel):
    """ISA-Tab: Investigation → Study → Assay (упрощённая схема)."""

    investigation_id: str | None = None
    study_id: str | None = None
    assay_id: str | None = None
    factor_names: list[str] = Field(default_factory=list)
    factor_values: dict[str, Any] = Field(default_factory=dict)
    measurement_type: str | None = None
    measurement_value: str | None = None
    unit: str | None = None
    raw_sample_characteristics: dict[str, Any] = Field(default_factory=dict)


class DocumentMetadata(BaseModel):
    source: str | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    date: str | None = None
    language: str = "ru"
    experiment_conditions: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    # ISA-Tab / Allotrope-подобная структура для экспериментов
    material_type: str | None = None
    sample_id: str | None = None
    instrument: str | None = None
    material_composition: dict[str, Any] = Field(default_factory=dict)
    process_parameters: dict[str, Any] = Field(default_factory=dict)
    measurement_results: dict[str, Any] = Field(default_factory=dict)
    protocol_steps: list[str] = Field(default_factory=list)
    isa_tab: IsaTabRecord | None = None
    allotrope_process_uri: str | None = None


class RoadmapStep(BaseModel):
    step_order: int = 1
    title: str
    description: str = ""
    duration_days: int = 7
    resources: list[str] = Field(default_factory=list)
    success_criteria: str = ""
    failure_criteria: str = ""
    depends_on: list[int] = Field(default_factory=list)


class KnowledgeGap(BaseModel):
    topic: str
    severity: str = "medium"  # low | medium | high
    evidence: str = ""
    suggested_action: str = ""


class BusinessCase(BaseModel):
    """Бизнес-обоснование гипотезы: KPI, ROI, окупаемость."""

    target_kpi: str = ""
    baseline_value: str | None = None
    expected_delta_pct: float | None = None
    annual_revenue_impact_rub: float | None = None
    annual_cost_savings_rub: float | None = None
    implementation_cost_rub: float | None = None
    payback_months: float | None = None
    roi_ratio: float | None = None
    confidence: str = "medium"  # low | medium | high
    narrative: str = ""


class ResearchAnalysis(BaseModel):
    analogy: str = ""
    analogy_domains: list[str] = Field(default_factory=list)
    counterfactual: str = ""
    counterfactual_baseline: str = ""
    predictive_score: float = Field(ge=0, le=1, default=0.5)
    predictive_notes: str = ""
    pattern_matches: list[str] = Field(default_factory=list)
    model_name: str = ""
    model_r2: float | None = None
    predicted_kpi_delta_pct: float | None = None


class Entity(BaseModel):
    name: str
    type: str  # Material, Process, Property, Parameter
    properties: dict[str, Any] = Field(default_factory=dict)


class SourceRef(BaseModel):
    doc_id: str
    snippet: str
    url: str | None = None


class RiskScores(BaseModel):
    technical: float = Field(ge=0, le=10)
    economic: float = Field(ge=0, le=10)


class ScoreBreakdown(BaseModel):
    novelty: float = 0.0
    feasibility: float = 0.0
    expected_value: float = 0.0
    risk_inverted: float = 0.0
    novelty_vector: float | None = None
    novelty_llm: float | None = None
    weights: dict[str, float] = Field(default_factory=dict)
    composite: float = 0.0


class CaseCheckItem(BaseModel):
    key: str
    label: str
    required: bool = True
    passed: bool = False
    note: str = ""


class CaseCompliance(BaseModel):
    items: list[CaseCheckItem] = Field(default_factory=list)
    mandatory_passed: int = 0
    mandatory_total: int = 0
    optional_passed: int = 0
    optional_total: int = 0
    all_mandatory_met: bool = False
    compliance_pct: float = Field(
        0.0, description="Доля выполненных обязательных пунктов ТЗ, %"
    )


class JudgeVerdict(BaseModel):
    approved: bool = False
    overall_score: float = Field(ge=0, le=10, default=0)
    testability: float = Field(ge=0, le=10, default=0)
    evidence_quality: float = Field(ge=0, le=10, default=0)
    relevance: float = Field(ge=0, le=10, default=0)
    structure_valid: bool = True
    source_grounded: bool = False
    case_compliance: CaseCompliance | None = None
    objective_score: float = Field(
        ge=0,
        le=1,
        default=0,
        description="Целевой балл гипотезы по вердикту судьи (максимизируем)",
    )
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    judge_notes: str = ""
    decision_rationale: list[str] = Field(
        default_factory=list,
        description="Почему судья одобрил или отклонил гипотезу (для UI)",
    )


class JudgeSummary(BaseModel):
    total: int = 0
    approved: int = 0
    rejected: int = 0
    avg_score: float = 0.0
    jqi: float = Field(
        0.0,
        description="Judge Quality Index 0–100 — главная метрика прогона",
    )
    approval_rate: float = 0.0
    avg_objective: float = 0.0
    grounding_rate: float = 0.0
    objective_target: float = 75.0
    avg_case_compliance_pct: float = 0.0
    compliance_notes: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    id: str
    text: str
    mechanism: str
    novelty_score: float = Field(ge=0, le=10)
    feasibility_score: float = Field(ge=0, le=10)
    expected_value_score: float = Field(ge=0, le=10)
    risk: RiskScores
    sources: list[SourceRef] = Field(default_factory=list)
    verification_roadmap: list[str] | None = None
    structured_roadmap: list[RoadmapStep] | None = None
    research_analysis: ResearchAnalysis | None = None
    business_case: BusinessCase | None = None
    reasoning: str = ""
    conflicts: list[str] = Field(default_factory=list)
    influence_graph: dict[str, Any] = Field(default_factory=dict)
    score_breakdown: ScoreBreakdown | None = None
    judge_verdict: JudgeVerdict | None = None
    generation_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class IngestRequest(BaseModel):
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class IngestResponse(BaseModel):
    doc_id: str
    chunks_indexed: int
    entities_extracted: int
    message: str


class IngestSqlRequest(BaseModel):
    """Импорт строк из SQL-источника в базу знаний."""

    connection_uri: str = Field(
        description="URI: sqlite:///data/experiments.db или путь к .db/.sqlite",
    )
    query: str = Field(description="SELECT-запрос (только чтение)")
    title: str = "SQL import"
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class GenerateRequest(BaseModel):
    problem: str
    constraints: str = ""
    language: str = Field(
        default="ru",
        description="Зарезервировано; вывод гипотез всегда на русском",
    )
    hypothesis_count: int | None = Field(
        default=None,
        description="Число гипотез для генерации (1–12); по умолчанию из DEFAULT_HYPOTHESIS_COUNT",
    )
    top_k: int = 12
    weights: dict[str, float] | None = None
    auto_ingest: bool = False
    ingest_directories: list[str] | None = None


class RetrievalSource(BaseModel):
    """Документ, попавший в RAG-контекст генерации."""

    doc_id: str
    title: str | None = None
    source_path: str | None = None
    chunks_in_context: int = 0
    max_score: float = 0.0


class GenerateResponse(BaseModel):
    generation_id: str
    problem: str
    constraints: str
    hypotheses: list[Hypothesis]
    conflicts_detected: list[str] = Field(default_factory=list)
    retrieval_doc_ids: list[str] = Field(default_factory=list)
    retrieval_sources: list[RetrievalSource] = Field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list)
    agentic_trace: dict[str, Any] | None = None
    judge_summary: JudgeSummary | None = None


class RoadmapUpdateRequest(BaseModel):
    steps: list[RoadmapStep]


class FeedbackRequest(BaseModel):
    status: FeedbackStatus
    comment: str = ""
    expert_scores: dict[str, float] | None = None


class FeedbackResponse(BaseModel):
    hypothesis_id: str
    status: FeedbackStatus
    updated_weights: dict[str, float] | None = None


class ExportReportRequest(BaseModel):
    generation_id: str
    format: str = "pdf"  # pdf | docx
    hypothesis_ids: list[str] | None = None


class RankingWeightsUpdate(BaseModel):
    novelty: float | None = None
    feasibility: float | None = None
    expected_value: float | None = None
    risk: float | None = None


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str]
    models: dict[str, str] = Field(default_factory=dict)
