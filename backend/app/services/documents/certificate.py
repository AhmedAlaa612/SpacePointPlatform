"""Shared certificate generator (PLAN §4.5/§8.2) — `certificates` table has a
`type` discriminator so this one module serves workshop-delivery certs
(Phase 3, needed now for payment-letter signing) and completion certs
(Phase 4, intern/instructor completion — not built yet, but the table and
this module's shape already accommodate it without rework).
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


def generate_workshop_certificate_pdf(
    recipient_name: str, workshop_name: str, workshop_date: str, location: str,
) -> bytes:
    """Workshop-delivery certificate (certificates.type='workshop_delivery')."""
    _ensure_fonts()
    width, height = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))

    c.drawImage(_TEMPLATE_PATH, 0, 0, width=width, height=height)

    c.setFont("TimesNewRoman-BoldItalic", 34)
    c.setFillColor(_TEXT_COLOR)
    c.drawCentredString(width / 2.0, 298, recipient_name)

    style = ParagraphStyle(
        name="CertificateRecognitionText", fontName="TimesNewRoman-Italic", fontSize=15,
        leading=22, textColor=_TEXT_COLOR, alignment=1,
    )
    text = (
        f"in recognition of his/her outstanding contribution as a facilitator to the<br/>"
        f"<b>{workshop_name}</b>, delivered on <b>{workshop_date}</b> at <b>{location}</b>"
    )
    p = Paragraph(text, style)
    p_width = 600
    p_height = p.wrap(p_width, 100)[1]
    p.drawOn(c, (width - p_width) / 2.0, 240 - p_height)

    c.save()
    return buf.getvalue()
