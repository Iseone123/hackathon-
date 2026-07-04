"""API: генерация и управление гипотезами."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from app.api.ingest import maybe_auto_ingest
from app.deps import get_generator
from app.feedback.learner import record_hypothesis_feedback
from app.hypotheses.roadmap_builder import apply_roadmap_update
from app.hypotheses.store import load_hypothesis, update_hypothesis
from app.llm_client import LLMRateLimitError
from app.models import (
    FeedbackRequest,
    FeedbackResponse,
    GenerateRequest,
    GenerateResponse,
    Hypothesis,
    RoadmapUpdateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["hypotheses"])


@router.post("/hypotheses/generate", response_model=GenerateResponse)
def generate_hypotheses(request: GenerateRequest) -> GenerateResponse:
    try:
        if request.auto_ingest:
            maybe_auto_ingest(request.ingest_directories)

        result = get_generator().generate(
            problem=request.problem,
            constraints=request.constraints,
            language=request.language,
            top_k=request.top_k,
            weights=request.weights,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Превышен лимит запросов YandexGPT. "
                    "Подождите 1–2 минуты и повторите."
                ),
            ) from exc
        logger.exception("Generation failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return GenerateResponse(
        generation_id=result["generation_id"],
        problem=result["problem"],
        constraints=result["constraints"],
        hypotheses=result["hypotheses"],
        conflicts_detected=result["conflicts_detected"],
        retrieval_doc_ids=result["retrieval_doc_ids"],
        retrieval_sources=result.get("retrieval_sources") or [],
        knowledge_gaps=result.get("knowledge_gaps") or [],
        judge_summary=result.get("judge_summary"),
    )


@router.get("/hypotheses/{hypothesis_id}", response_model=Hypothesis)
def get_hypothesis(hypothesis_id: str) -> Hypothesis:
    hypothesis = load_hypothesis(hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail="Гипотеза не найдена")
    return hypothesis


@router.patch("/hypotheses/{hypothesis_id}/roadmap", response_model=Hypothesis)
def update_roadmap(hypothesis_id: str, body: RoadmapUpdateRequest) -> Hypothesis:
    hypothesis = load_hypothesis(hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail="Гипотеза не найдена")
    updated = apply_roadmap_update(hypothesis, body.steps)
    if not update_hypothesis(hypothesis_id, updated):
        raise HTTPException(status_code=500, detail="Не удалось сохранить roadmap")
    return updated


@router.post("/hypotheses/{hypothesis_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(
    hypothesis_id: str,
    feedback: FeedbackRequest,
) -> FeedbackResponse:
    hypothesis = load_hypothesis(hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail="Гипотеза не найдена")

    result = record_hypothesis_feedback(
        hypothesis_id,
        feedback.status,
        hypothesis.model_dump(mode="json"),
        feedback.comment,
        feedback.expert_scores,
    )
    return FeedbackResponse(
        hypothesis_id=hypothesis_id,
        status=feedback.status,
        updated_weights=result.get("weights"),
    )
