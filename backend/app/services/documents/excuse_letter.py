"""University excuse / formal invitation letter generator using ReportLab.

Generates a branded PDF for finalists qualifying to an on-site cohort,
matching the portal's letterhead format (banner, SpacePoint logo, copyright footer).
Supports both team-wide (table of all members) and single-student letters.
"""

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.documents.letterhead import BOTTOM_MARGIN, LetterheadCanvas, TOP_MARGIN

_STYLES = getSampleStyleSheet()

_TITLE = ParagraphStyle(
    "ExcuseTitle",
    parent=_STYLES["Normal"],
    fontName="Helvetica-Bold",
    fontSize=13,
    leading=18,
    alignment=1,  # Center
    textColor=colors.black,
    spaceAfter=14,
)

_SALUTATION = ParagraphStyle(
    "ExcuseSalutation",
    parent=_STYLES["Normal"],
    fontName="Helvetica-Bold",
    fontSize=10.5,
    leading=15,
    textColor=colors.black,
    spaceAfter=10,
)

_BODY = ParagraphStyle(
    "ExcuseBody",
    parent=_STYLES["Normal"],
    fontName="Helvetica",
    fontSize=9.5,
    leading=14.5,
    textColor=HexColor("#222222"),
    spaceAfter=9,
)

_SECTION_HEADING = ParagraphStyle(
    "ExcuseHeading",
    parent=_STYLES["Normal"],
    fontName="Helvetica-Bold",
    fontSize=10.5,
    leading=15,
    textColor=colors.black,
    spaceAfter=6,
    spaceBefore=8,
)

_DETAIL_LINE = ParagraphStyle(
    "ExcuseDetailLine",
    parent=_STYLES["Normal"],
    fontName="Helvetica",
    fontSize=9,
    leading=14,
    textColor=HexColor("#222222"),
    leftIndent=6,
    spaceAfter=3,
)

_TABLE_HEADER = ParagraphStyle(
    "ExcuseTableHeader",
    parent=_STYLES["Normal"],
    fontName="Helvetica-Bold",
    fontSize=9,
    leading=12,
    textColor=colors.black,
)

_TABLE_CELL = ParagraphStyle(
    "ExcuseTableCell",
    parent=_STYLES["Normal"],
    fontName="Helvetica",
    fontSize=8.5,
    leading=12,
    textColor=HexColor("#222222"),
)

_SIGN_OFF = ParagraphStyle(
    "ExcuseSignOff",
    parent=_STYLES["Normal"],
    fontName="Helvetica",
    fontSize=9,
    leading=13.5,
    textColor=HexColor("#222222"),
)


def generate_excuse_letter_pdf(
    *,
    team_name: str,
    institution_name: str | None = None,
    members: list[dict[str, Any]],
    event_name: str,
    organizer: str = "SpacePoint in collaboration with the UAE Space Agency",
    dates_text: str,
    location_text: str,
    student_role: str = "Finalist - Lander Design, Prototyping & Presentation",
    participation_mode: str = "On-site Exhibition, Technical Demonstration, Industry Engagement",
    description_text: str | None = None,
    committee_name: str = "PlanetX Organizing Committee",
    contact_email: str = "info@spacepoint.ae",
    contact_phone: str = "+971562987005",
    contact_website: str = "www.spacepoint.ae",
    single_student: dict[str, Any] | None = None,
) -> bytes:
    """Renders the official invitation & university excuse letter as a PDF.

    If `single_student` is provided (e.g. {"name": "...", "student_id": "..."}),
    the document is tailored specifically for that individual student.
    Otherwise, it is issued for the entire team roster.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=TOP_MARGIN + 6,
        bottomMargin=BOTTOM_MARGIN + 4,
    )

    story = []

    # 1. Title
    story.append(Paragraph(f"Formal Invitation to Participate in {event_name}", _TITLE))
    story.append(Spacer(1, 4 * mm))

    # 2. Salutation
    story.append(Paragraph("To Whom It May Concern,", _SALUTATION))

    # 3. Invitation paragraph
    inst_phrase = f"from {institution_name}" if institution_name else "from your esteemed institution"
    if single_student:
        stud_name = single_student.get("name") or "the student"
        lead_html = (
            f"We are pleased to formally invite <b>{stud_name}</b> {inst_phrase} to represent their team "
            f"(<b>{team_name}</b>) as finalists in the <b>{event_name}</b>, organized by <b>{organizer}</b>. "
            f"This prestigious competition will culminate in a live showcase at <b>{location_text}</b>."
        )
    else:
        lead_html = (
            f"We are pleased to formally invite the below-mentioned student(s) {inst_phrase} to represent their team "
            f"(<b>{team_name}</b>) as finalists in the <b>{event_name}</b>, organized by <b>{organizer}</b>. "
            f"This prestigious competition will culminate in a live showcase at <b>{location_text}</b>."
        )
    story.append(Paragraph(lead_html, _BODY))
    story.append(Spacer(1, 3 * mm))

    # 4. Student Roster Table
    display_members = [single_student] if single_student else (members or [])
    table_data = [[
        Paragraph("Student Name", _TABLE_HEADER),
        Paragraph("University ID", _TABLE_HEADER),
    ]]
    for m in display_members:
        name = m.get("name") or m.get("full_name") or ""
        sid = m.get("student_id") or m.get("university_id") or m.get("card_number") or "—"
        table_data.append([
            Paragraph(str(name), _TABLE_CELL),
            Paragraph(str(sid), _TABLE_CELL),
        ])

    table = Table(table_data, colWidths=[105 * mm, 65 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#F5F5F7")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#D0D0D5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    # 5. Event Details
    story.append(Paragraph("Event Details:", _SECTION_HEADING))
    story.append(Paragraph(f"<b>Name:</b> {event_name}", _DETAIL_LINE))
    story.append(Paragraph(f"<b>Organizer:</b> {organizer}", _DETAIL_LINE))
    story.append(Paragraph(f"<b>Dates:</b> {dates_text}", _DETAIL_LINE))
    story.append(Paragraph(f"<b>Location:</b> {location_text}", _DETAIL_LINE))
    story.append(Paragraph(f"<b>Student Role:</b> {student_role}", _DETAIL_LINE))
    story.append(Paragraph(f"<b>Participation Mode:</b> {participation_mode}", _DETAIL_LINE))
    story.append(Spacer(1, 3 * mm))

    # 6. Description / Context paragraph
    if not description_text:
        description_text = (
            "The student has been selected as part of the finalist teams representing top talent across "
            "the region. This hands-on experience includes presenting their prototype, engaging with "
            "industry experts, and attending key technical sessions, offering an unparalleled educational "
            "and professional development opportunity in aerospace engineering and innovation."
        )
    story.append(Paragraph(description_text, _BODY))

    # 7. University Excuse Clause & Closing Block
    closing_elements = [
        Paragraph(
            "We kindly request your support in <b>excusing the student(s) from academic activities during this "
            "period</b> to allow full participation in the finals. Their involvement not only honors their "
            "academic institution but also contributes meaningfully to national ambitions in space "
            "exploration and youth empowerment.",
            _BODY,
        ),
        Paragraph(
            "Should you require any further documentation or verification, please feel free to contact us.",
            _BODY,
        ),
        Paragraph("Thank you for your cooperation and support.", _BODY),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Sincerely,<br/>"
            f"<b>{committee_name}</b><br/>"
            f"<b>SpacePoint</b><br/>"
            f"{contact_email} | {contact_phone}<br/>"
            f"{contact_website}",
            _SIGN_OFF,
        ),
    ]

    story.append(KeepTogether(closing_elements))

    doc.build(story, canvasmaker=LetterheadCanvas)
    return buf.getvalue()
