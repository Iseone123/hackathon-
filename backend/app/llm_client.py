"""Клиент Yandex AI Studio: completion + embeddings.

Единственная точка входа для всех LLM-вызовов — модель можно заменить,
не трогая бизнес-логику. Ключи только из окружения (.env), см. .env.example.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("llm_client")

COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
EMBEDDING_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"

RETRIES = 3
TIMEOUT = 120


class LLMError(RuntimeError):
    pass


@dataclass
class UsageLog:
    """Накопительный лог токенов и латентности за процесс — для аудита."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_latency_s: float = 0.0
    history: list[dict] = field(default_factory=list)

    def record(self, kind: str, usage: dict, latency: float) -> None:
        self.calls += 1
        inp = int(usage.get("inputTextTokens", 0))
        out = int(usage.get("completionTokens", 0))
        self.input_tokens += inp
        self.output_tokens += out
        self.total_latency_s += latency
        self.history.append(
            {"kind": kind, "input_tokens": inp, "output_tokens": out, "latency_s": round(latency, 2)}
        )


USAGE = UsageLog()


def _credentials() -> tuple[str, str]:
    api_key = os.environ.get("YC_API_KEY", "")
    folder = os.environ.get("YC_FOLDER_ID", "")
    if not api_key or not folder:
        raise LLMError(
            "Не заданы YC_API_KEY / YC_FOLDER_ID. Скопируйте .env.example в .env и заполните."
        )
    return api_key, folder


def llm_available() -> bool:
    return bool(os.environ.get("YC_API_KEY")) and bool(os.environ.get("YC_FOLDER_ID"))


def _post(url: str, payload: dict, api_key: str) -> dict:
    last_err: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Api-Key {api_key}"},
                timeout=TIMEOUT,
            )
            if resp.status_code == 429:
                wait = 2**attempt
                logger.warning("429 rate limit, жду %s c (попытка %s)", wait, attempt)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            last_err = e
            logger.warning("LLM запрос упал (попытка %s/%s): %s", attempt, RETRIES, e)
            time.sleep(2**attempt)
    raise LLMError(f"LLM недоступен после {RETRIES} попыток: {last_err}")


def complete(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4000,
    lite: bool = False,
) -> str:
    """messages: [{"role": "system"|"user"|"assistant", "text": "..."}]"""
    api_key, folder = _credentials()
    model = os.environ.get("YC_GPT_MODEL_LITE" if lite else "YC_GPT_MODEL", "yandexgpt/latest")
    payload = {
        "modelUri": f"gpt://{folder}/{model}",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": str(max_tokens),
        },
        "messages": messages,
    }
    t0 = time.monotonic()
    data = _post(COMPLETION_URL, payload, api_key)
    latency = time.monotonic() - t0
    result = data.get("result", {})
    USAGE.record("completion", result.get("usage", {}), latency)
    alternatives = result.get("alternatives", [])
    if not alternatives:
        raise LLMError(f"Пустой ответ модели: {data}")
    return alternatives[0]["message"]["text"]


def complete_json(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4000,
    lite: bool = False,
) -> dict | list:
    """Completion с парсингом JSON из ответа; одна повторная попытка при мусоре."""
    for attempt in range(2):
        text = complete(messages, temperature=temperature, max_tokens=max_tokens, lite=lite)
        try:
            return extract_json(text)
        except ValueError:
            logger.warning("Невалидный JSON от модели (попытка %s), ответ: %.300s", attempt + 1, text)
            messages = messages + [
                {"role": "assistant", "text": text},
                {"role": "user", "text": "Ответ не является валидным JSON. Верни ТОЛЬКО валидный JSON без пояснений и markdown."},
            ]
    raise LLMError("Модель дважды вернула невалидный JSON")


def extract_json(text: str) -> dict | list:
    """Достаёт JSON из ответа модели: срезает ```-заборы и текст вокруг."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # первая { или [ до последней } или ]
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("JSON не найден в ответе модели")


def embed(text: str, query: bool = False) -> list[float]:
    """Эмбеддинг документа (text-search-doc) или запроса (text-search-query)."""
    api_key, folder = _credentials()
    model = "text-search-query" if query else "text-search-doc"
    payload = {"modelUri": f"emb://{folder}/{model}/latest", "text": text[:8000]}
    t0 = time.monotonic()
    data = _post(EMBEDDING_URL, payload, api_key)
    USAGE.record("embedding", {}, time.monotonic() - t0)
    emb = data.get("embedding")
    if not emb:
        raise LLMError(f"Пустой эмбеддинг: {data}")
    return emb


def embed_batch(texts: list[str], query: bool = False, rps: float = 5.0) -> list[list[float]]:
    """Последовательный батч с троттлингом под rate limit AI Studio."""
    out = []
    delay = 1.0 / rps
    for i, t in enumerate(texts):
        out.append(embed(t, query=query))
        if i % 50 == 49:
            logger.info("Эмбеддинги: %s/%s", i + 1, len(texts))
        time.sleep(delay)
    return out
