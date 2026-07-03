"""FastAPI: приём данных, генерация гипотез, фидбэк, экспорт."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from . import exporter, llm_client, scoring
from .few_shot import load_expert_pairs
from .generator import generate_hypotheses
from .knowledge_base import KnowledgeBase
from .tailings_parser import parse_tailings_xlsx

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

DATA_DIR = os.environ.get("DATA_DIR", "./backend/data/source")
INDEX_DIR = os.environ.get("INDEX_DIR", "./backend/data/index")
STORE_DIR = os.environ.get("STORE_DIR", "./backend/data/store")
KNOWLEDGE_NOTES = "./backend/data/knowledge"

app = FastAPI(title="Фабрика гипотез", version="0.1.0")

KB = KnowledgeBase(INDEX_DIR)
EXAMPLES: list[dict] = []
RUNS: dict[str, dict] = {}  # id → результат генерации


def _persist_run(run_id: str) -> None:
    Path(STORE_DIR).mkdir(parents=True, exist_ok=True)
    (Path(STORE_DIR) / f"run_{run_id}.json").write_text(
        json.dumps(RUNS[run_id], ensure_ascii=False), encoding="utf-8"
    )


@app.on_event("startup")
def startup() -> None:
    global EXAMPLES
    if not KB.load():
        sources = [d for d in (DATA_DIR, KNOWLEDGE_NOTES) if Path(d).exists()]
        if sources:
            KB.build(sources)
    if Path(DATA_DIR).exists():
        EXAMPLES = load_expert_pairs(DATA_DIR)
    # восстановление прогонов с диска
    store = Path(STORE_DIR)
    if store.exists():
        for f in store.glob("run_*.json"):
            RUNS[f.stem.removeprefix("run_")] = json.loads(f.read_text(encoding="utf-8"))
    logger.info("Старт: %s чанков, %s экспертных пар, %s прогонов, LLM=%s",
                len(KB.chunks), len(EXAMPLES), len(RUNS), llm_client.llm_available())


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "kb_chunks": len(KB.chunks),
        "kb_embeddings": KB.embeddings is not None,
        "expert_pairs": [e["name"] for e in EXAMPLES],
        "llm_available": llm_client.llm_available(),
        "llm_usage": {"calls": llm_client.USAGE.calls,
                      "input_tokens": llm_client.USAGE.input_tokens,
                      "output_tokens": llm_client.USAGE.output_tokens},
    }


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)) -> dict:
    """Добавить документ в базу знаний (PDF/MD/TXT) с переиндексацией."""
    suffix = Path(file.filename or "doc").suffix.lower()
    if suffix not in {".pdf", ".md", ".txt"}:
        raise HTTPException(400, "Поддерживаются PDF, MD, TXT")
    dest = Path(DATA_DIR) / "uploaded"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / (file.filename or f"doc{suffix}")
    path.write_bytes(await file.read())
    stats = KB.build([d for d in (DATA_DIR, KNOWLEDGE_NOTES) if Path(d).exists()])
    return {"ingested": str(path.name), **stats}


@app.get("/examples")
def examples() -> list[dict]:
    """Экспертные пары для сравнения в UI (имя объекта + гипотезы специалистов)."""
    return [{"name": e["name"], "expert_hypotheses": e["expert_hypotheses"]} for e in EXAMPLES]


class GenerateResponse(BaseModel):
    run_id: str
    input_file: str
    summary_text: str
    diagnostics: list[dict]
    hypotheses: list[dict]
    n_samples_used: int


@app.post("/hypotheses/generate")
async def generate(
    file: UploadFile = File(...),
    goal: str = Form(""),
    constraints: str = Form(""),
    n_hypotheses: int = Form(8),
    weights: str = Form(""),  # JSON: {"novelty": .., "feasibility": .., "impact": .., "risk": ..}
) -> GenerateResponse:
    if not llm_client.llm_available():
        raise HTTPException(503, "LLM не настроен: заполните YC_API_KEY/YC_FOLDER_ID в .env")
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        parsed = parse_tailings_xlsx(tmp_path)
    except Exception as e:
        raise HTTPException(422, f"Не удалось разобрать Excel: {e}")
    finally:
        os.unlink(tmp_path)
    if not parsed["sections"]:
        raise HTTPException(422, "В файле не найдены секции хвостов (ожидается формат отчёта института)")

    # few-shot без утечки: исключаем пример того же объекта, что и вход
    input_name = Path(file.filename or "").stem.replace("Хвосты", "").strip(" _").lower()
    examples = [e for e in EXAMPLES if e["name"].lower() != input_name] or EXAMPLES

    result = generate_hypotheses(
        KB, parsed["summary_text"], parsed["diagnostics"], examples,
        goal=goal, constraints=constraints, n_hypotheses=n_hypotheses,
    )

    w = json.loads(weights) if weights else scoring.load_weights(STORE_DIR)
    sims = [KB.max_similarity(h["hypothesis"]) for h in result["hypotheses"]]
    ranked = scoring.rank(result["hypotheses"], w, sims)

    run_id = uuid.uuid4().hex[:8]
    RUNS[run_id] = {
        "run_id": run_id,
        "input_file": file.filename,
        "goal": goal,
        "constraints": constraints,
        "summary_text": parsed["summary_text"],
        "diagnostics": parsed["diagnostics"],
        "hypotheses": ranked,
        "weights": w,
        "n_samples_used": result["n_samples_used"],
    }
    _persist_run(run_id)
    return GenerateResponse(
        run_id=run_id, input_file=file.filename or "", summary_text=parsed["summary_text"],
        diagnostics=parsed["diagnostics"], hypotheses=ranked, n_samples_used=result["n_samples_used"],
    )


class RerankRequest(BaseModel):
    weights: dict


@app.post("/hypotheses/{run_id}/rerank")
def rerank(run_id: str, req: RerankRequest) -> dict:
    """Пересортировка с новыми весами — мгновенно, без LLM."""
    run = RUNS.get(run_id) or _not_found(run_id)
    run["hypotheses"] = scoring.rank(run["hypotheses"], req.weights)
    run["weights"] = req.weights
    _persist_run(run_id)
    return {"hypotheses": run["hypotheses"]}


@app.get("/hypotheses/{run_id}")
def get_run(run_id: str) -> dict:
    return RUNS.get(run_id) or _not_found(run_id)


class FeedbackRequest(BaseModel):
    hypothesis_index: int
    accepted: bool
    comment: str = ""


@app.post("/hypotheses/{run_id}/feedback")
def feedback(run_id: str, req: FeedbackRequest) -> dict:
    """Фидбэк эксперта: обновляет глобальные веса ранжирования (online learning)."""
    run = RUNS.get(run_id) or _not_found(run_id)
    if not 0 <= req.hypothesis_index < len(run["hypotheses"]):
        raise HTTPException(400, "Нет гипотезы с таким индексом")
    h = run["hypotheses"][req.hypothesis_index]
    h["feedback"] = {"accepted": req.accepted, "comment": req.comment}
    new_weights = scoring.update_weights_from_feedback(STORE_DIR, h, req.accepted)
    _persist_run(run_id)
    return {"updated_weights": new_weights}


@app.post("/export/report")
def export_report(run_id: str) -> Response:
    run = RUNS.get(run_id) or _not_found(run_id)
    return Response(
        exporter.report_docx(run),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="report_{run_id}.docx"'},
    )


@app.get("/export/tasks")
def export_tasks(run_id: str, fmt: str = "json") -> Response:
    run = RUNS.get(run_id) or _not_found(run_id)
    if fmt == "csv":
        return PlainTextResponse(exporter.tasks_csv(run), media_type="text/csv")
    return PlainTextResponse(exporter.tasks_json(run), media_type="application/json")


def _not_found(run_id: str):
    raise HTTPException(404, f"Прогон {run_id} не найден")
