"""Конфигурация приложения: пути, параметры чанкинга, веса ранжирования."""

from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
CHROMA_DIR = ROOT_DIR / "data" / "chroma"
OUTPUT_DIR = ROOT_DIR / "output"

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
YANDEX_BASE_URL = "https://llm.api.cloud.yandex.net/v1"

YANDEX_CHAT_MODEL = os.getenv("YANDEX_CHAT_MODEL", "yandexgpt/latest")
YANDEX_EMBED_DOC_MODEL = os.getenv("YANDEX_EMBED_DOC_MODEL", "text-search-doc/latest")
YANDEX_EMBED_QUERY_MODEL = os.getenv("YANDEX_EMBED_QUERY_MODEL", "text-search-query/latest")

CHROMA_COLLECTION = "knowledge_chunks"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K_CHUNKS = 8

LLM_TEMPERATURE = 0.4
LLM_MAX_TOKENS = 4096
NUM_HYPOTHESES = 5

# Фиксированные веса для итогового ранжирования (сумма = 1.0)
RANKING_WEIGHTS = {
    "novelty": 0.35,
    "expected_value": 0.45,
    "risk": 0.20,  # риск инвертируется: меньше риск → выше балл
}

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


def model_uri(prefix: str, model_name: str) -> str:
    """Собирает URI модели Yandex AI Studio: gpt://folder/model или emb://folder/model."""
    return f"{prefix}://{YANDEX_FOLDER_ID}/{model_name}"


def ensure_dirs() -> None:
    """Создаёт рабочие директории, если их ещё нет."""
    for path in (DATA_RAW_DIR, CHROMA_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)
