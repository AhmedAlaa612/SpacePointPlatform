"""Intern confirmation/completion letters — pure ReportLab (PLAN §4.5/§8.2).
Generates in-memory bytes — the caller uploads via services/storage.py.
"""

from datetime import date
from io import BytesIO
from typing import Literal

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_STYLES = getSampleStyleSheet()
_BODY = ParagraphStyle("Body", parent=_STYLES["Normal"], fontSize=11, leading=16, spaceAfter=10)
_TITLE = ParagraphStyle("Title", parent=_STYLES["Title"], fontSize=15, spaceAfter=14)


def generate_intern_letter_pdf(
    recipient_name: str,
    letter_type: Literal["confirmation", "completion"],
    start_date: str,
    end_date: str | None,
    signatory_name: str,
    signatory_title: str,
) -> bytes:
    """Renders an intern confirmation or completion letter. Returns PDF bytes."""
    today = date.today().strftime("%d %B %Y").lstrip("0")

    if letter_type == "completion":
        title = "Internship Completion Letter"
        body = (
            f"This is to confirm that <b>{recipient_name}</b> has successfully completed an "
            f"internship at SpacePoint FZC, from {start_date} to {end_date}, contributing "
            "diligently to the team's projects throughout this period."
        )
    else:
        title = "Internship Confirmation Letter"
        body = (
            f"This is to confirm that <b>{recipient_name}</b> is currently undertaking an "
            f"internship at SpacePoint FZC, since {start_date}."
        )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=25 * mm, rightMargin=25 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
    )
    story = [
        Paragraph(title, _TITLE),
        Paragraph(f"Date: {today}", _BODY),
        Paragraph("To Whom It May Concern,", _BODY),
        Paragraph(body, _BODY),
        Spacer(1, 14 * mm),
        Paragraph("Sincerely,", _BODY),
        Spacer(1, 10 * mm),
        Paragraph(f"{signatory_name}<br/>{signatory_title}<br/>SpacePoint FZC", _BODY),
    ]
    doc.build(story)
    return buf.getvalue()
