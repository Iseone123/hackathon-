"""OCR для PNG/JPG и сканированных PDF (Tesseract)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.ingest.text_utils import clean_ocr_text

logger = logging.getLogger(__name__)

OCR_LANGS = "rus+eng"
MAX_OCR_PDF_PAGES = 50
IMAGE_DPI = 300


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def poppler_available() -> bool:
    return shutil.which("pdftoppm") is not None


def _preprocess_image(image):
    from PIL import ImageEnhance, ImageOps

    image = ImageOps.grayscale(image)
    image = ImageEnhance.Contrast(image).enhance(1.8)
    image = ImageEnhance.Sharpness(image).enhance(1.5)
    return image


def ocr_image(path: Path) -> str:
    if not tesseract_available():
        raise RuntimeError(
            "Tesseract не установлен. macOS: brew install tesseract tesseract-lang"
        )
    import pytesseract
    from PIL import Image

    image = Image.open(path)
    image = _preprocess_image(image)
    config = "--psm 6 -c preserve_interword_spaces=1"
    text = pytesseract.image_to_string(image, lang=OCR_LANGS, config=config)
    return clean_ocr_text(text)


def ocr_pdf(path: Path, max_pages: int = MAX_OCR_PDF_PAGES) -> str:
    if not tesseract_available():
        raise RuntimeError(
            "Tesseract не установлен. macOS: brew install tesseract tesseract-lang"
        )
    if not poppler_available():
        raise RuntimeError(
            "Poppler не установлен. macOS: brew install poppler"
        )

    from pdf2image import convert_from_path
    import pytesseract

    images = convert_from_path(
        str(path),
        first_page=1,
        last_page=max_pages,
        dpi=IMAGE_DPI,
    )
    parts: list[str] = []
    config = "--psm 6"
    for i, image in enumerate(images, 1):
        image = _preprocess_image(image)
        page_text = clean_ocr_text(
            pytesseract.image_to_string(image, lang=OCR_LANGS, config=config)
        )
        if page_text:
            parts.append(f"## Page {i}\n{page_text}")

    if not parts:
        logger.warning("OCR PDF %s: текст не распознан", path.name)
    return "\n\n".join(parts)


def pdf_needs_ocr(text: str, page_count: int) -> bool:
    stripped = text.strip()
    if len(stripped) < 100:
        return True
    if page_count > 0 and len(stripped) / page_count < 40:
        return True
    return False
