"""Shared certificate generator (PLAN §4.5/§8.2) — `certificates` table has a
`type` discriminator so this one module serves workshop-delivery certs
(Phase 3, payment-letter signing) and completion certs (Phase 4, intern +
instructor completion).
"""

import io
import os

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

_STATIC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
_TEMPLATE_PATH = os.path.join(_STATIC_DIR, "templates", "certificate_template.png")
_FONTS_DIR = os.path.join(_STATIC_DIR, "fonts")
_TEXT_COLOR = HexColor("#9778be")

_fonts_registered = False


def _ensure_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont("TimesNewRoman", os.path.join(_FONTS_DIR, "times.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNewRoman-Bold", os.path.join(_FONTS_DIR, "timesbd.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNewRoman-Italic", os.path.join(_FONTS_DIR, "timesi.ttf")))
    pdfmetrics.registerFont(TTFont("TimesNewRoman-BoldItalic", os.path.join(_FONTS_DIR, "timesbi.ttf")))
    _fonts_registered = True


def generate_completion_certificate_pdf(
    recipient_name: str,
    body_text_template: str,
    background_bytes: bytes | None = None
) -> bytes:
    """Completion certificate (certificates.type='internship_completion' |
    'instructor_completion'). Uses dynamic body text and optional background file bytes.
    """
    _ensure_fonts()
    width, height = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    if background_bytes:
        c.drawImage(io.BytesIO(background_bytes), 0, 0, width=width, height=height)
    else:
        c.drawImage(_TEMPLATE_PATH, 0, 0, width=width, height=height)

    c.setFont("TimesNewRoman-BoldItalic", 34)
    c.setFillColor(_TEXT_COLOR)
    c.drawCentredString(width / 2.0, 298, recipient_name)

    style = ParagraphStyle(
        name="CertificateCompletionText", fontName="TimesNewRoman-Italic", fontSize=15,
        leading=22, textColor=_TEXT_COLOR, alignment=1,
    )
    p = Paragraph(body_text_template, style)
    p_width = 600
    p_height = p.wrap(p_width, 100)[1]
    p.drawOn(c, (width - p_width) / 2.0, 240 - p_height)

    c.save()
    return buf.getvalue()
