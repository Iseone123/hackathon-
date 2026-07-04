"""API: экспорт отчётов и задач."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from app.config import settings
from app.export.report import export_report
from app.export.tasks import export_tasks_csv, export_tasks_json
from app.hypotheses.store import load_generation
from app.models import Hypothesis

router = APIRouter(tags=["export"])


@router.post("/export/report")
def export_report_endpoint(
    generation_id: str,
    format: str = "pdf",
    hypothesis_ids: str | None = None,
) -> FileResponse:
    data = load_generation(generation_id)
    if not data:
        raise HTTPException(status_code=404, detail="Генерация не найдена")

    hypotheses = [Hypothesis.model_validate(h) for h in data["hypotheses"]]
    if hypothesis_ids:
        ids = set(hypothesis_ids.split(","))
        hypotheses = [h for h in hypotheses if h.id in ids]

    output_dir = settings.data_dir_path / "exports"
    path, _ = export_report(
        data["problem"],
        data.get("constraints", ""),
        hypotheses,
        format,
        output_dir,
        generation_id,
    )
    media = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if format == "docx"
        else "application/pdf"
    )
    return FileResponse(path, media_type=media, filename=path.name)


@router.get("/export/tasks")
def export_tasks(
    generation_id: str,
    format: str = "json",
) -> Any:
    data = load_generation(generation_id)
    if not data:
        raise HTTPException(status_code=404, detail="Генерация не найдена")
    hypotheses = [Hypothesis.model_validate(h) for h in data["hypotheses"]]

    if format == "csv":
        return PlainTextResponse(
            export_tasks_csv(hypotheses, generation_id),
            media_type="text/csv",
        )
    return JSONResponse(export_tasks_json(hypotheses, generation_id))
