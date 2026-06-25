"""Recommendation letter — pure ReportLab (PLAN §4.5/§8.2). Admin-only, manual
trigger, any role. Generates in-memory bytes — the caller uploads via
services/storage.py.
"""

from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_STYLES = getSampleStyleSheet()
_BODY = ParagraphStyle("Body", parent=_STYLES["Normal"], fontSize=11, leading=16, spaceAfter=10)
_TITLE = ParagraphStyle("Title", parent=_STYLES["Title"], fontSize=15, spaceAfter=14)


def generate_recommendation_letter_pdf(
    recipient_name: str,
    recommendation_text: str,
    signatory_name: str,
    signatory_title: str,
) -> bytes:
    """Renders a "To Whom It May Concern" recommendation letter. Returns PDF bytes
    (not written to disk). `recommendation_text` is admin-authored free text —
    escaped before embedding since ReportLab's Paragraph parses a mini-XML subset."""
    today = date.today().strftime("%d %B %Y").lstrip("0")
    body_html = escape(recommendation_text).replace("\n", "<br/>")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=25 * mm, rightMargin=25 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
    )
    story = [
        Paragraph("Letter of Recommendation", _TITLE),
        Paragraph(f"Date: {today}", _BODY),
        Paragraph("To Whom It May Concern,", _BODY),
        Paragraph(body_html, _BODY),
        Spacer(1, 14 * mm),
        Paragraph("Sincerely,", _BODY),
        Spacer(1, 10 * mm),
        Paragraph(f"{signatory_name}<br/>{signatory_title}<br/>SpacePoint FZC", _BODY),
    ]
    doc.build(story)
    return buf.getvalue()
