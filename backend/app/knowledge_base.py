"""База знаний: PDF учебники + заметки → чанки → гибридный поиск BM25 + эмбеддинги.

Эмбеддинги (Yandex text-search-doc) опциональны: без ключа работает чистый BM25,
с ключом — гибрид. Индекс кэшируется на диск.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import numpy as np
import fitz  # pymupdf
from rank_bm25 import BM25Okapi

from . import llm_client

logger = logging.getLogger("knowledge_base")

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
_WORD_RE = re.compile(r"[а-яёa-z0-9]+")


def _tokenize(text: str) -> list[str]:
    # обрезка до 7 символов — дешёвый стемминг для русской морфологии
    return [w[:7] for w in _WORD_RE.findall(text.lower())]


def _chunk_text(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= CHUNK_SIZE:
        return [text] if text else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            # рвём по границе предложения, если она есть в хвосте чанка
            cut = text.rfind(". ", start + CHUNK_SIZE // 2, end)
            if cut != -1:
                end = cut + 1
        chunks.append(text[start:end].strip())
        start = end - CHUNK_OVERLAP
    return [c for c in chunks if len(c) > 100]


class KnowledgeBase:
    def __init__(self, index_dir: str):
        self.index_dir = Path(index_dir)
        self.chunks: list[dict] = []
        self.bm25: BM25Okapi | None = None
        self.embeddings: np.ndarray | None = None

    # ---------- построение ----------

    def build(self, source_dirs: list[str]) -> dict:
        """Индексирует все PDF/MD/TXT из указанных директорий."""
        self.chunks = []
        skipped = []
        for d in source_dirs:
            for path in sorted(Path(d).rglob("*")):
                if path.suffix.lower() == ".pdf":
                    n = self._ingest_pdf(path)
                    if n == 0:
                        skipped.append(path.name)
                elif path.suffix.lower() in {".md", ".txt"}:
                    self._ingest_textfile(path)
        self._build_bm25()
        self._save()
        logger.info("Индекс: %s чанков; пропущено (нет текстового слоя): %s", len(self.chunks), skipped)
        return {"chunks": len(self.chunks), "skipped_no_text_layer": skipped}

    def _ingest_pdf(self, path: Path) -> int:
        try:
            doc = fitz.open(str(path))
        except Exception as e:
            logger.warning("Не открылся %s: %s", path.name, e)
            return 0
        added = 0
        for page_num in range(len(doc)):
            for chunk in _chunk_text(doc[page_num].get_text()):
                self.chunks.append(
                    {
                        "id": len(self.chunks),
                        "source": path.stem,
                        "page": page_num + 1,
                        "text": chunk,
                    }
                )
                added += 1
        return added

    def _ingest_textfile(self, path: Path) -> None:
        for i, chunk in enumerate(_chunk_text(path.read_text(encoding="utf-8"))):
            self.chunks.append(
                {"id": len(self.chunks), "source": path.stem, "page": i + 1, "text": chunk}
            )

    def build_embeddings(self) -> int:
        """Опционально: досчитать эмбеддинги Yandex (нужен YC_API_KEY)."""
        vecs = llm_client.embed_batch([c["text"] for c in self.chunks])
        self.embeddings = np.array(vecs, dtype=np.float32)
        np.save(self.index_dir / "embeddings.npy", self.embeddings)
        return len(vecs)

    def _build_bm25(self) -> None:
        if self.chunks:
            self.bm25 = BM25Okapi([_tokenize(c["text"]) for c in self.chunks])

    def _save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # ---------- загрузка ----------

    def load(self) -> bool:
        path = self.index_dir / "chunks.jsonl"
        if not path.exists():
            return False
        with open(path, encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f]
        self._build_bm25()
        emb_path = self.index_dir / "embeddings.npy"
        if emb_path.exists():
            self.embeddings = np.load(emb_path)
            if len(self.embeddings) != len(self.chunks):
                logger.warning("Эмбеддинги не совпадают с чанками, отключаю")
                self.embeddings = None
        return True

    # ---------- поиск ----------

    def search(self, query: str, k: int = 8) -> list[dict]:
        """Гибрид: BM25 (+ косинус по эмбеддингам, если есть). Скор прозрачный."""
        if not self.bm25:
            return []
        bm25_scores = np.array(self.bm25.get_scores(_tokenize(query)))
        bm25_norm = bm25_scores / bm25_scores.max() if bm25_scores.max() > 0 else bm25_scores

        cos_norm = None
        if self.embeddings is not None and llm_client.llm_available():
            try:
                q = np.array(llm_client.embed(query, query=True), dtype=np.float32)
                cos = self.embeddings @ q / (
                    np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q) + 1e-9
                )
                cos_norm = (cos - cos.min()) / (cos.max() - cos.min() + 1e-9)
            except Exception as e:
                logger.warning("Эмбеддинг запроса не удался, только BM25: %s", e)

        combined = bm25_norm if cos_norm is None else 0.5 * bm25_norm + 0.5 * cos_norm
        top = np.argsort(-combined)[:k]
        return [
            {
                **self.chunks[i],
                "score": round(float(combined[i]), 4),
                "score_bm25": round(float(bm25_norm[i]), 4),
                "score_cosine": round(float(cos_norm[i]), 4) if cos_norm is not None else None,
            }
            for i in top
            if combined[i] > 0
        ]

    def max_similarity(self, text: str) -> float | None:
        """Близость текста к корпусу — сигнал (анти)новизны. None, если нет эмбеддингов."""
        if self.embeddings is None or not llm_client.llm_available():
            return None
        try:
            v = np.array(llm_client.embed(text, query=True), dtype=np.float32)
            cos = self.embeddings @ v / (
                np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(v) + 1e-9
            )
            return round(float(cos.max()), 4)
        except Exception:
            return None
