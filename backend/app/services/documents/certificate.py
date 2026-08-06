"""Shared certificate generator (PLAN §4.5/§8.2) — `certificates` table has a
`type` discriminator so this one module serves workshop-delivery certs
(Phase 3, payment-letter signing) and completion certs (Phase 4, intern +
instructor completion).
"""

import io
import os
import re

import arabic_reshaper
from bidi.algorithm import get_display
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

_STATIC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
_TEMPLATES_DIR = os.path.join(_STATIC_DIR, "templates")
_TEMPLATE_PATHS = {
    "dark": os.path.join(_TEMPLATES_DIR, "certificate_template.png"),
    "light": os.path.join(_TEMPLATES_DIR, "certificate_template_light.png"),
}
_FONTS_DIR = os.path.join(_STATIC_DIR, "fonts")
_TEXT_COLORS = {
    "dark": HexColor("#9778be"),
    "light": HexColor("#67388f"),
}

_fonts_registered = False

# Arabic + Arabic Supplement + Arabic Extended-A + Arabic Presentation Forms A/B.
_ARABIC_RE = re.compile(
    "[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]"
)


def _ensure_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont("TimesNewRoman", os.path.join(_FONTS_DIR, "times.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNewRoman-Bold", os.path.join(_FONTS_DIR, "timesbd.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNewRoman-Italic", os.path.join(_FONTS_DIR, "timesi.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNewRoman-BoldItalic", os.path.join(_FONTS_DIR, "timesbi.ttf")))
    # Times New Roman has no Arabic coverage, and reportlab's drawString/
    # Paragraph draw raw codepoints with no shaping or bidi reordering —
    # Arabic text rendered as disconnected, left-to-right, unjoined glyphs
    # without a font that has the glyphs plus the _shaped() reorder below.
    pdfmetrics.registerFont(TTFont("Amiri", os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Amiri-Bold", os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")))
    _fonts_registered = True


def _is_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text or ""))


def _shaped(text: str) -> str:
    """Glyph-join + right-to-left reorder so Arabic renders correctly.
    Reportlab has no built-in text shaping — without this, Arabic draws as
    disconnected letterforms in visual (not logical) order."""
    return get_display(arabic_reshaper.reshape(text))


def generate_completion_certificate_pdf(
    recipient_name: str,
    body_text_template: str,
    background_bytes: bytes | None = None,
    theme: str = "dark",
) -> bytes:
    """Completion certificate (certificates.type='internship_completion' |
    'instructor_completion'). Uses dynamic body text and optional background
    file bytes. `theme` picks the stock background ("dark" | "light") when
    `background_bytes` isn't supplied, plus a matching text color — light
    uses #67388f instead of the dark theme's #9778be, since the lighter
    purple reads poorly against a white background (operator ask,
    2026-08-07)."""
    _ensure_fonts()
    text_color = _TEXT_COLORS.get(theme, _TEXT_COLORS["dark"])
    width, height = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    if background_bytes:
        c.drawImage(io.BytesIO(background_bytes), 0, 0, width=width, height=height)
    else:
        template_path = _TEMPLATE_PATHS.get(theme, _TEMPLATE_PATHS["dark"])
        c.drawImage(template_path, 0, 0, width=width, height=height)

    name_arabic = _is_arabic(recipient_name)
    c.setFont("Amiri-Bold" if name_arabic else "TimesNewRoman-BoldItalic", 34)
    c.setFillColor(text_color)
    c.drawCentredString(width / 2.0, 298, _shaped(recipient_name) if name_arabic else recipient_name)

    # `<br/>`-joined segments render independently — reshape each one so a
    # tag never gets treated as literal Arabic-adjacent text (reshaping
    # only touches the actual glyphs on either side of it).
    segments = body_text_template.split("<br/>")
    body_arabic = any(_is_arabic(seg) for seg in segments)
    if body_arabic:
        segments = [_shaped(seg) if _is_arabic(seg) else seg for seg in segments]
    display_body = "<br/>".join(segments)

    style = ParagraphStyle(
        name="CertificateCompletionText",
        fontName="Amiri" if body_arabic else "TimesNewRoman-Italic",
        fontSize=18, leading=26, textColor=text_color, alignment=1,
    )
    p = Paragraph(display_body, style)
    p_width = 600
    p_height = p.wrap(p_width, 100)[1]
    p.drawOn(c, (width - p_width) / 2.0, 240 - p_height)

    c.save()
    return buf.getvalue()


def merge_certificate_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    """One PDF, one page per certificate, in the given order — same
    pypdf-merge approach as build_applicant_dossier_pdf (dossier.py).
    """
    writer = PdfWriter()
    for pdf_bytes in pdf_bytes_list:
        for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()
