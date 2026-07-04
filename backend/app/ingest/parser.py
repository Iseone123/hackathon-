"""Парсинг PDF/DOCX/TXT/XLSX/изображений в нормализованные документы."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.ingest.docx_parse import read_docx
from app.ingest.ocr import ocr_image, ocr_pdf, pdf_needs_ocr, tesseract_available
from app.ingest.tabular import parse_spreadsheet
from app.ingest.text_utils import chunk_text, normalize_parsed_text
from app.models import DocumentMetadata, Entity

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


def _read_txt(path: Path) -> str:
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_pdf_text(path: Path) -> tuple[str, int]:
    page_count = 0
    parts: list[str] = []

    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    parts.append(text)
        if parts:
            return "\n\n".join(parts), page_count
    except Exception:
        pass

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    parts = [page.extract_text() or "" for page in reader.pages if page.extract_text()]
    return "\n\n".join(parts), page_count


def _read_pdf(path: Path) -> str:
    text, page_count = _extract_pdf_text(path)
    used_ocr = False

    if pdf_needs_ocr(text, page_count):
        if tesseract_available():
            logger.info("PDF %s: мало текста (%d симв.), OCR", path.name, len(text.strip()))
            try:
                ocr_text = ocr_pdf(path)
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    used_ocr = True
            except Exception as exc:
                logger.warning("OCR PDF %s failed: %s", path.name, exc)
        else:
            logger.warning(
                "PDF %s похож на скан, но Tesseract не установлен", path.name
            )

    return normalize_parsed_text(text, from_ocr=used_ocr)


def _read_docx(path: Path) -> str:
    return read_docx(path)


def _read_xlsx(path: Path) -> str:
    return parse_spreadsheet(path)


def _read_image(path: Path) -> str:
    return normalize_parsed_text(ocr_image(path), from_ocr=True)


def parse_file(path: Path) -> str:
    suffix = path.suffix.lower()
    readers = {
        ".txt": _read_txt,
        ".md": _read_txt,
        ".pdf": _read_pdf,
        ".docx": _read_docx,
        ".xlsx": _read_xlsx,
        ".xls": _read_xlsx,
    }
    if suffix in IMAGE_SUFFIXES:
        return _read_image(path)

    reader = readers.get(suffix)
    if not reader:
        raise ValueError(f"Неподдерживаемый формат: {suffix}")
    raw = reader(path)
    if suffix in IMAGE_SUFFIXES:
        return raw
    return normalize_parsed_text(raw)


def supported_suffixes() -> set[str]:
    return {
        ".txt", ".md", ".pdf", ".docx", ".xlsx", ".xls",
        *IMAGE_SUFFIXES,
    }


def make_doc_id(path: Path, content: str) -> str:
    digest = hashlib.sha256(content[:2000].encode("utf-8", errors="replace")).hexdigest()
    return f"{path.stem}_{digest[:12]}"


# chunk_text импортируется из text_utils (умная нарезка по абзацам)


def build_document(
    path: Path,
    content: str,
    metadata: DocumentMetadata | None = None,
) -> dict[str, Any]:
    meta = metadata or DocumentMetadata(source=str(path))
    if not meta.title:
        meta.title = path.name
    doc_id = make_doc_id(path, content)
    return {
        "id": doc_id,
        "text": content,
        "metadata": meta.model_dump(),
        "entities": [],
        "path": str(path),
    }


def parse_entities_from_llm(data: dict[str, Any]) -> list[Entity]:
    entities: list[Entity] = []
    for item in data.get("entities", []):
        entities.append(
            Entity(
                name=item.get("name", ""),
                type=item.get("type", "Parameter"),
                properties=item.get("properties", {}),
            )
        )
    return [e for e in entities if e.name]
