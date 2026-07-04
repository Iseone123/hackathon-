"""Регистрация TTF-шрифтов с кириллицей для ReportLab PDF."""

from __future__ import annotations

import logging
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
_FONT_DIR = Path(__file__).resolve().parent / "fonts"

_REGISTERED = False


def _font_candidates(filename: str) -> list[Path]:
    """Bundled fonts first, then типичные пути Linux/macOS."""
    names = [filename]
    if filename.startswith("DejaVuSans"):
        names.extend(
            [
                filename.replace("DejaVuSans", "Arial"),
                "LiberationSans-Regular.ttf" if "Bold" not in filename else "LiberationSans-Bold.ttf",
                "Arial Unicode.ttf",
            ]
        )
    paths: list[Path] = []
    for name in names:
        paths.append(_FONT_DIR / name)
    paths.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu") / filename,
            Path("/usr/share/fonts/TTF") / filename,
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/Library/Fonts/Arial Unicode.ttf"),
        ]
    )
    return paths


def _resolve_font(filename: str) -> Path | None:
    for path in _font_candidates(filename):
        if path.is_file():
            return path
    return None


def register_pdf_fonts() -> str:
    """Регистрирует regular + bold; возвращает имя regular для ParagraphStyle."""
    global _REGISTERED
    if _REGISTERED:
        return FONT_REGULAR

    regular_path = _resolve_font("DejaVuSans.ttf")
    bold_path = _resolve_font("DejaVuSans-Bold.ttf") or regular_path
    if not regular_path:
        logger.warning(
            "Cyrillic PDF font not found in %s or system paths — PDF may show empty boxes",
            _FONT_DIR,
        )
        return "Helvetica"

    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular_path)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))
    pdfmetrics.registerFontFamily(
        FONT_REGULAR,
        normal=FONT_REGULAR,
        bold=FONT_BOLD,
        italic=FONT_REGULAR,
        boldItalic=FONT_BOLD,
    )
    _REGISTERED = True
    logger.debug("PDF fonts registered: %s, %s", regular_path, bold_path)
    return FONT_REGULAR
