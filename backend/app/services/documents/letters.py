"""Generic PDF letter generator using ReportLab.

Handles the standard structural layout: Title, Date, Salutation/Body, and Sincerely/Signatory footer.
"""

from datetime import date
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.services.documents.letterhead import BOTTOM_MARGIN, LetterheadCanvas, TOP_MARGIN

_STYLES = getSampleStyleSheet()
_BODY = ParagraphStyle("Body", parent=_STYLES["Normal"], fontSize=11, leading=16, spaceAfter=10)
_TITLE = ParagraphStyle("Title", parent=_STYLES["Title"], fontSize=15, spaceAfter=14)


def generate_letter_pdf(
    title: str,
    body_text: str,
    signatory_name: str,
    signatory_title: str,
) -> bytes:
    """Renders a generic letter document. Returns PDF bytes."""
    today = date.today().strftime("%d %B %Y").lstrip("0")
    
    # Ensure newlines in text are rendered as line breaks in ReportLab
    formatted_body = body_text.replace("\n", "<br/>")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=25 * mm, rightMargin=25 * mm, topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
    )

    story = [
        Paragraph(title, _TITLE),
        Spacer(1, 10 * mm),
        Paragraph(formatted_body, _BODY),
    ]

    doc.build(story, canvasmaker=LetterheadCanvas)
    return buf.getvalue()
