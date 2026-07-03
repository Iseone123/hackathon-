"""Загрузка документов, чанкинг и индексация в ChromaDB."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from pypdf import PdfReader

from app.config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DATA_RAW_DIR,
    SUPPORTED_EXTENSIONS,
    ensure_dirs,
)
from app.llm_client import YandexLLMClient


@dataclass
class TextChunk:
    chunk_id: str
    text: str
    source_file: str
    chunk_index: int


def load_text_from_file(path: Path) -> str:
    """Извлекает plain text из txt/md/pdf."""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    raise ValueError(f"Неподдерживаемый формат: {path.suffix}")


def chunk_text(text: str, source_file: str) -> list[TextChunk]:
    """Простой чанкинг: сначала по абзацам, длинные — скользящим окном."""
    normalized = re.sub(r"\r\n?", "\n", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        return []

    paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
    raw_chunks: list[str] = []

    for paragraph in paragraphs:
        if len(paragraph) <= CHUNK_SIZE:
            raw_chunks.append(paragraph)
        else:
            start = 0
            while start < len(paragraph):
                end = start + CHUNK_SIZE
                raw_chunks.append(paragraph[start:end])
                if end >= len(paragraph):
                    break
                start = end - CHUNK_OVERLAP

    result: list[TextChunk] = []
    for index, chunk in enumerate(raw_chunks):
        chunk_id = _make_chunk_id(source_file, index, chunk)
        result.append(
            TextChunk(
                chunk_id=chunk_id,
                text=chunk,
                source_file=source_file,
                chunk_index=index,
            )
        )
    return result


def _make_chunk_id(source_file: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(f"{source_file}:{chunk_index}:{text[:64]}".encode()).hexdigest()
    return digest[:32]


def discover_source_files(raw_dir: Path | None = None) -> list[Path]:
    """Находит все поддерживаемые файлы в data/raw."""
    directory = raw_dir or DATA_RAW_DIR
    if not directory.exists():
        return []
    files: list[Path] = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return files


def get_chroma_collection():
    """Возвращает persistent-коллекцию ChromaDB."""
    ensure_dirs()
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(name=CHROMA_COLLECTION)


def ingest(raw_dir: Path | None = None, *, reset: bool = True) -> dict:
    """
    Индексирует документы из data/raw в ChromaDB.

    Returns:
        Статистика: files, chunks, collection_size
    """
    ensure_dirs()
    llm = YandexLLMClient()
    files = discover_source_files(raw_dir)

    if not files:
        raise FileNotFoundError(
            f"Нет документов в {raw_dir or DATA_RAW_DIR}. "
            "Положите .txt/.md/.pdf файлы и повторите."
        )

    all_chunks: list[TextChunk] = []
    for file_path in files:
        rel_name = str(file_path.relative_to(raw_dir or DATA_RAW_DIR))
        text = load_text_from_file(file_path)
        all_chunks.extend(chunk_text(text, rel_name))

    if not all_chunks:
        raise ValueError("Документы найдены, но текст не извлёкся (пустые файлы?)")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if reset:
        try:
            client.delete_collection(CHROMA_COLLECTION)
        except ValueError:
            pass
    collection = client.get_or_create_collection(name=CHROMA_COLLECTION)

    batch_size = 16
    for start in range(0, len(all_chunks), batch_size):
        batch = all_chunks[start : start + batch_size]
        embeddings = llm.embed_documents([c.text for c in batch])
        collection.add(
            ids=[c.chunk_id for c in batch],
            embeddings=embeddings,
            documents=[c.text for c in batch],
            metadatas=[
                {
                    "source_file": c.source_file,
                    "chunk_index": c.chunk_index,
                }
                for c in batch
            ],
        )

    return {
        "files": len(files),
        "chunks": len(all_chunks),
        "collection_size": collection.count(),
    }


def main() -> None:
    """CLI: python -m app.ingest"""
    stats = ingest()
    print(
        f"Индексация завершена: {stats['files']} файлов, "
        f"{stats['chunks']} чанков, в коллекции {stats['collection_size']} записей."
    )


if __name__ == "__main__":
    main()
