"""Полный пайплайн ingest: парсинг → NER → Qdrant + Neo4j."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.db.neo4j_store import Neo4jStore
from app.db.qdrant_store import QdrantStore
from app.ingest.metadata_extract import enrich_metadata_from_content
from app.ingest.entities import extract_entities
from app.ingest.index_status import get_index_status, is_file_indexed, list_data_files
from app.ingest.parser import build_document, parse_file, supported_suffixes
from app.ingest.text_utils import chunk_text
from app.llm_client import YandexLLMClient
from app.models import DocumentMetadata

logger = logging.getLogger(__name__)


class IngestPipeline:
    def __init__(
        self,
        llm: YandexLLMClient | None = None,
        qdrant: QdrantStore | None = None,
        neo4j: Neo4jStore | None = None,
    ) -> None:
        self.llm = llm or YandexLLMClient()
        self.qdrant = qdrant or QdrantStore()
        self.neo4j = neo4j or Neo4jStore()

    def ingest_file(
        self,
        path: Path,
        metadata: DocumentMetadata | None = None,
    ) -> dict[str, Any]:
        content = parse_file(path)
        doc = build_document(path, content, metadata)
        doc_id = doc["id"]
        meta = enrich_metadata_from_content(
            path, content, DocumentMetadata(**doc["metadata"]) if doc.get("metadata") else metadata
        )
        meta_payload = meta.model_dump()

        chunks = chunk_text(
            content,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        embeddings = self.llm.embed_documents(chunks) if chunks else []
        indexed = self.qdrant.upsert_chunks(doc_id, chunks, embeddings, meta_payload)

        entities, relations = extract_entities(content, self.llm)
        doc["metadata"] = meta_payload
        doc["entities"] = [e.model_dump() for e in entities]

        try:
            self.neo4j.upsert_publication(doc_id, meta_payload)
            self.neo4j.upsert_entities(doc_id, entities, relations)
        except Exception as exc:
            logger.warning("Neo4j ingest skipped: %s", exc)

        processed_path = settings.processed_dir / f"{doc_id}.json"
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        processed_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "doc_id": doc_id,
            "chunks_indexed": indexed,
            "entities_extracted": len(entities),
            "relations_extracted": len(relations),
        }

    def ingest_text_corpus(
        self,
        content: str,
        doc_id: str,
        metadata: DocumentMetadata,
    ) -> dict[str, Any]:
        """Индексирует готовый текст (SQL, API и др.)."""
        meta = metadata
        meta_payload = meta.model_dump()

        chunks = chunk_text(
            content,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        embeddings = self.llm.embed_documents(chunks) if chunks else []
        indexed = self.qdrant.upsert_chunks(doc_id, chunks, embeddings, meta_payload)

        entities, relations = extract_entities(content, self.llm)
        doc = {
            "id": doc_id,
            "text": content,
            "metadata": meta_payload,
            "entities": [e.model_dump() for e in entities],
            "path": meta.source or doc_id,
        }

        try:
            self.neo4j.upsert_publication(doc_id, meta_payload)
            self.neo4j.upsert_entities(doc_id, entities, relations)
        except Exception as exc:
            logger.warning("Neo4j ingest skipped: %s", exc)

        processed_path = settings.processed_dir / f"{doc_id}.json"
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        processed_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "doc_id": doc_id,
            "chunks_indexed": indexed,
            "entities_extracted": len(entities),
            "relations_extracted": len(relations),
        }

    def ingest_sql(
        self,
        connection_uri: str,
        query: str,
        title: str,
        metadata: DocumentMetadata | None = None,
    ) -> dict[str, Any]:
        from app.ingest.sql_import import (
            build_sql_metadata,
            fetch_sql_rows,
            make_sql_doc_id,
            rows_to_text,
        )

        rows = fetch_sql_rows(connection_uri, query)
        content = rows_to_text(rows, title)
        meta = build_sql_metadata(title, rows, metadata)
        doc_id = make_sql_doc_id(title, content)
        return self.ingest_text_corpus(content, doc_id, meta)

    def ingest_directory(
        self,
        directory: Path,
        *,
        only_missing: bool = False,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        extensions = supported_suffixes()
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            if only_missing and is_file_indexed(path):
                results.append({
                    "path": str(path),
                    "skipped": True,
                    "reason": "already_indexed",
                })
                continue
            try:
                meta = DocumentMetadata(
                    source=str(path.relative_to(settings.data_dir_path)),
                    title=path.name,
                )
                results.append(self.ingest_file(path, meta))
            except Exception as exc:
                logger.error("Failed to ingest %s: %s", path, exc)
                results.append({"path": str(path), "error": str(exc)})
        return results

    def ingest_missing(self, directory: Path | None = None) -> list[dict[str, Any]]:
        """Индексирует только ещё не обработанные файлы."""
        root = directory or settings.data_dir_path
        if directory:
            return self.ingest_directory(root, only_missing=True)
        results: list[dict[str, Any]] = []
        for path in list_data_files(root):
            if is_file_indexed(path):
                continue
            try:
                meta = DocumentMetadata(
                    source=str(path.relative_to(settings.data_dir_path)),
                    title=path.name,
                )
                results.append(self.ingest_file(path, meta))
            except Exception as exc:
                logger.error("Failed to ingest %s: %s", path, exc)
                results.append({"path": str(path), "error": str(exc)})
        return results
