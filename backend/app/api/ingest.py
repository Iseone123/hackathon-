"""API: ingest и статус индекса."""

from __future__ import annotations

import json
import logging
import shutil
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.deps import get_ingest
from app.ingest.helpers import resolve_data_directory, run_auto_ingest, summarize_ingest_results
from app.ingest.index_status import get_index_status
from app.models import DocumentMetadata, IngestResponse, IngestSqlRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
def ingest_document(
    file: UploadFile = File(...),
    metadata: str = Form("{}"),
) -> IngestResponse:
    try:
        meta_dict = json.loads(metadata)
        doc_meta = DocumentMetadata.model_validate(meta_dict)
    except (json.JSONDecodeError, ValueError):
        doc_meta = DocumentMetadata()

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.uploads_dir / (file.filename or "upload.bin")
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    if not doc_meta.source:
        try:
            doc_meta.source = str(dest.relative_to(settings.data_dir_path))
        except ValueError:
            doc_meta.source = str(dest)
    if not doc_meta.title:
        doc_meta.title = file.filename or dest.name

    try:
        result = get_ingest().ingest_file(dest, doc_meta)
    except Exception as exc:
        logger.exception("Ingest failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return IngestResponse(
        doc_id=result["doc_id"],
        chunks_indexed=result["chunks_indexed"],
        entities_extracted=result["entities_extracted"],
        message="Документ успешно проиндексирован",
    )


@router.get("/index/status")
def index_status(directory: str | None = None) -> dict[str, Any]:
    return get_index_status(directory)


@router.post("/ingest/sync")
def ingest_sync(directory: str | None = None) -> dict[str, Any]:
    pipeline = get_ingest()
    if directory:
        try:
            target = resolve_data_directory(directory)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        results = pipeline.ingest_directory(target, only_missing=True)
    else:
        results = pipeline.ingest_missing()
    return summarize_ingest_results(results)


@router.post("/ingest/batch")
def ingest_batch(
    directory: str = "Дополнительные материалы",
    only_missing: bool = False,
) -> dict[str, Any]:
    try:
        target = resolve_data_directory(directory)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    results = get_ingest().ingest_directory(target, only_missing=only_missing)
    return summarize_ingest_results(results)


@router.post("/ingest/sql", response_model=IngestResponse)
def ingest_sql(body: IngestSqlRequest) -> IngestResponse:
    try:
        result = get_ingest().ingest_sql(
            body.connection_uri,
            body.query,
            body.title,
            body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("SQL ingest failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return IngestResponse(
        doc_id=result["doc_id"],
        chunks_indexed=result["chunks_indexed"],
        entities_extracted=result["entities_extracted"],
        message="SQL-данные успешно проиндексированы",
    )


def maybe_auto_ingest(directories: list[str] | None) -> None:
    status_before = get_index_status()
    if status_before["missing_files"] > 0 or status_before["qdrant_points"] == 0:
        run_auto_ingest(get_ingest(), directories)
