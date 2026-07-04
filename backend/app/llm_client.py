"""Клиент YandexGPT: completion + embeddings с ретраями и логированием."""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = logging.getLogger(__name__)


class LLMRateLimitError(RuntimeError):
    """Исчерпан лимит запросов к YandexGPT."""


def _is_retryable_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


@dataclass
class LLMCallLog:
    operation: str
    model: str
    latency_ms: float
    input_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    success: bool = True
    error: str | None = None


@dataclass
class YandexLLMClient:
    """Обёртка над Foundation Models API Yandex Cloud."""

    api_key: str = field(default_factory=lambda: settings.yc_api_key)
    folder_id: str = field(default_factory=lambda: settings.yc_folder_id)
    timeout: float = field(default_factory=lambda: settings.llm_timeout_sec)
    call_history: list[LLMCallLog] = field(default_factory=list)
    _last_request_at: float = field(default=0.0, init=False, repr=False)
    _throttle_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key or not self.folder_id:
            raise ValueError(
                "Задайте YC_API_KEY и YC_FOLDER_ID в .env (см. .env.example)"
            )
        self._headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
            "x-data-logging-enabled": "false",
        }

    def _model_uri(self, kind: str, model: str) -> str:
        prefix = "gpt" if kind == "gpt" else "emb"
        return f"{prefix}://{self.folder_id}/{model}"

    def _log_call(self, log: LLMCallLog) -> None:
        self.call_history.append(log)
        level = logging.INFO if log.success else logging.ERROR
        logger.log(
            level,
            "LLM %s model=%s latency=%.0fms tokens=%d/%d success=%s",
            log.operation,
            log.model,
            log.latency_ms,
            log.input_tokens,
            log.completion_tokens,
            log.success,
        )

    def _throttle(self) -> None:
        """Минимальный интервал между запросами — снижает 429 от YandexGPT."""
        try:
            interval = float(settings.llm_request_delay_sec)
        except (TypeError, ValueError):
            interval = 0.0
        if interval <= 0:
            return
        with self._throttle_lock:
            elapsed = time.perf_counter() - self._last_request_at
            if elapsed < interval:
                time.sleep(interval - elapsed)
            self._last_request_at = time.perf_counter()

    @retry(
        retry=retry_if_exception(_is_retryable_llm_error),
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=3, min=8, max=120),
        reraise=True,
    )
    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._throttle()
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=self._headers, json=payload)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait_sec = 15.0
                if retry_after:
                    try:
                        wait_sec = max(wait_sec, float(retry_after))
                    except ValueError:
                        pass
                logger.warning(
                    "YandexGPT 429 — пауза %.0f с перед повтором%s",
                    wait_sec,
                    f" (Retry-After={retry_after})" if retry_after else "",
                )
                time.sleep(wait_sec)
                response.raise_for_status()
            if response.status_code >= 500:
                response.raise_for_status()
            response.raise_for_status()
            return response.json()

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """Chat completion через Foundation Models API."""
        model_name = model or settings.yandexgpt_model
        model_uri = self._model_uri("gpt", model_name)
        start = time.perf_counter()

        messages = [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_prompt},
        ]
        payload: dict[str, Any] = {
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": temperature if temperature is not None else settings.llm_temperature,
                "maxTokens": str(max_tokens or settings.llm_max_tokens),
            },
            "messages": messages,
        }
        if json_mode:
            payload["jsonObject"] = True

        try:
            data = self._post(settings.llm_completion_url, payload)
            result = data["result"]["alternatives"][0]["message"]["text"]
            usage = data.get("result", {}).get("usage", {})
            self._log_call(
                LLMCallLog(
                    operation="completion",
                    model=model_uri,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    input_tokens=int(usage.get("inputTextTokens", 0) or 0),
                    completion_tokens=int(usage.get("completionTokens", 0) or 0),
                    total_tokens=int(usage.get("totalTokens", 0) or 0),
                )
            )
            if not result:
                raise RuntimeError("LLM вернул пустой ответ")
            return result
        except httpx.HTTPStatusError as exc:
            self._log_call(
                LLMCallLog(
                    operation="completion",
                    model=model_uri,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    success=False,
                    error=str(exc),
                )
            )
            if exc.response.status_code == 429:
                raise LLMRateLimitError(
                    "Превышен лимит запросов YandexGPT (429). "
                    "Подождите 2–3 минуты, не нажимайте кнопку повторно, затем повторите генерацию. "
                    "Снимите «Авто-индексация», если данные уже в индексе."
                ) from exc
            raise
        except Exception as exc:
            self._log_call(
                LLMCallLog(
                    operation="completion",
                    model=model_uri,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    success=False,
                    error=str(exc),
                )
            )
            raise

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        samples: int = 1,
    ) -> list[dict[str, Any]]:
        """Несколько JSON-ответов для self-consistency."""
        results: list[dict[str, Any]] = []
        for i in range(samples):
            if i > 0 and settings.llm_request_delay_sec > 0:
                time.sleep(settings.llm_request_delay_sec)
            raw = self.complete(
                system_prompt,
                user_prompt,
                model=model,
                json_mode=True,
            )
            try:
                parsed = self._parse_json(raw)
                results.append(parsed)
            except (ValueError, json.JSONDecodeError) as exc:
                logger.warning("Пропуск битого JSON-сэмпла: %s", exc)
        if not results:
            raise ValueError("LLM не вернул валидный JSON")
        return results

    def complete_lite(self, system_prompt: str, user_prompt: str) -> str:
        """Быстрый/дешёвый вызов для NER и извлечения сущностей."""
        return self.complete(
            system_prompt,
            user_prompt,
            model=settings.yandexgpt_lite_model,
            max_tokens=2000,
            json_mode=True,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, settings.embed_doc_model)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], settings.embed_query_model)[0]

    def _embed_single(self, text: str, model: str) -> list[float]:
        model_uri = self._model_uri("emb", model)
        start = time.perf_counter()
        payload = {"modelUri": model_uri, "text": text}
        try:
            data = self._post(settings.llm_embedding_url, payload)
            if "result" in data:
                vector = data["result"]["embedding"]
            elif "embedding" in data:
                vector = data["embedding"]
            else:
                raise RuntimeError(f"Unexpected embedding response: {list(data.keys())}")
            self._log_call(
                LLMCallLog(
                    operation="embedding",
                    model=model_uri,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    input_tokens=len(text.split()),
                )
            )
            return vector
        except Exception as exc:
            self._log_call(
                LLMCallLog(
                    operation="embedding",
                    model=model_uri,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    success=False,
                    error=str(exc),
                )
            )
            raise

    def _embed(self, texts: list[str], model: str) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) == 1:
            return [self._embed_single(texts[0], model)]

        workers = max(1, int(settings.embed_parallel_workers))
        if workers <= 1:
            return [self._embed_single(text, model) for text in texts]

        results: list[list[float] | None] = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(self._embed_single, text, model): idx
                for idx, text in enumerate(texts)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                results[idx] = future.result()
        return results  # type: ignore[return-value]

    @staticmethod
    def _escape_control_chars_in_strings(text: str) -> str:
        """Экранирует сырые control-символы внутри JSON-строк."""
        result: list[str] = []
        in_string = False
        escape = False
        for ch in text:
            if escape:
                result.append(ch)
                escape = False
                continue
            if ch == "\\" and in_string:
                result.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string and ord(ch) < 32:
                if ch == "\n":
                    result.append("\\n")
                elif ch == "\r":
                    result.append("\\r")
                elif ch == "\t":
                    result.append("\\t")
                else:
                    result.append(" ")
                continue
            result.append(ch)
        return "".join(result)

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )
        text = YandexLLMClient._escape_control_chars_in_strings(text)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(text[start:end])
            else:
                raise
        if not isinstance(parsed, dict):
            raise ValueError(
                f"LLM вернул {type(parsed).__name__} вместо JSON-объекта"
            )
        return parsed
