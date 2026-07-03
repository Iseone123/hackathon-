"""Клиент Yandex AI Studio через OpenAI-совместимый API."""

from __future__ import annotations

from openai import OpenAI

from app.config import (
    YANDEX_API_KEY,
    YANDEX_BASE_URL,
    YANDEX_CHAT_MODEL,
    YANDEX_EMBED_DOC_MODEL,
    YANDEX_EMBED_QUERY_MODEL,
    YANDEX_FOLDER_ID,
    model_uri,
)


class YandexLLMClient:
    """Обёртка над chat completions и embeddings Yandex AI Studio."""

    def __init__(self) -> None:
        if not YANDEX_API_KEY or not YANDEX_FOLDER_ID:
            raise ValueError(
                "Задайте YANDEX_API_KEY и YANDEX_FOLDER_ID в .env "
                "(см. .env.example)"
            )
        self._client = OpenAI(
            api_key=YANDEX_API_KEY,
            base_url=YANDEX_BASE_URL,
            default_headers={
                "x-folder-id": YANDEX_FOLDER_ID,
                "x-data-logging-enabled": "false",
            },
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Эмбеддинги для документов (индексация)."""
        return self._embed(texts, model=YANDEX_EMBED_DOC_MODEL)

    def embed_query(self, text: str) -> list[float]:
        """Эмбеддинг для поискового запроса."""
        return self._embed([text], model=YANDEX_EMBED_QUERY_MODEL)[0]

    def _embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=model_uri("emb", model),
            input=texts,
        )
        return [item.embedding for item in response.data]

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Генерация текста через chat completions."""
        from app.config import LLM_MAX_TOKENS, LLM_TEMPERATURE

        response = self._client.chat.completions.create(
            model=model_uri("gpt", YANDEX_CHAT_MODEL),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM вернул пустой ответ")
        return content
