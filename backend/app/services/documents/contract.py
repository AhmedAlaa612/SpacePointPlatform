"""Instructor agreement letter — pure ReportLab (PLAN §8.2/§9.2).

Replaces the source app's python-docx mail-merge + docx2pdf/LibreOffice
conversion (instructors/HANDOFF.md §2/§7) with a from-scratch PDF build, text
reproduced from the source .docx template with the merge fields parameterized.
Generates in-memory bytes — the caller uploads via services/storage.py.
"""

from datetime import date
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.core.config import settings

_STYLES = getSampleStyleSheet()
_BODY = ParagraphStyle("Body", parent=_STYLES["Normal"], fontSize=10, leading=14, spaceAfter=8)
_HEADING = ParagraphStyle("Heading", parent=_STYLES["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=6)
_TITLE = ParagraphStyle("Title", parent=_STYLES["Title"], fontSize=15, spaceAfter=14)

_SECTIONS = [
    ("1. Scope of Work", [
        "The Facilitator agrees to perform the following duties in connection with the SatKit "
        "workshops organized by SpacePoint:",
        "Deliver the workshops, including preparation and facilitation of course content.",
        "Assist with the setup and preparation of SatKit materials and any related workshop tools.",
        "The Facilitator agrees to perform these duties diligently, professionally, and to the best "
        "of their ability.",
    ]),
    ("2. Authorization for Use of Personal Information", [
        "The Facilitator grants SpacePoint permission to use their photograph and basic personal "
        "information solely for promotional purposes related to their role. SpacePoint agrees to use "
        "such information respectfully and only for the intended purposes.",
    ]),
    ("3. Confidentiality and NDA Terms", [
        "3.1 Purpose — The Facilitator acknowledges that they may access confidential information "
        "during their engagement, which will be disclosed only for purposes related to this Agreement.",
        "3.2 Confidentiality Obligations — The Facilitator agrees not to use or disclose such "
        "information outside the scope of their duties, and to take reasonable measures to protect it.",
        "3.3 Exclusions — Confidentiality obligations do not apply to information that is (i) publicly "
        "available, (ii) rightfully obtained from third parties without restriction, or (iii) "
        "independently developed without access to confidential material.",
        "3.4 Compelled Disclosure — If required by law or court order, the Facilitator shall notify "
        "SpacePoint promptly and cooperate to limit the extent of disclosure.",
        "3.5 Return or Destruction — Upon termination of this Agreement or upon request, the "
        "Facilitator agrees to return or destroy all confidential materials, including digital "
        "content, and confirm such action in writing.",
    ]),
    ("4. Intellectual Property Rights", [
        "All materials, tools, kits, presentations, and content created or used during the "
        "Facilitator's engagement are the exclusive property of SpacePoint. No intellectual property "
        "rights are transferred to the Facilitator, except for limited use necessary to fulfill their role.",
    ]),
    ("5. Payment Terms", [
        "The Facilitator will be compensated for services rendered at rates specified in a separate "
        "Facilitator Payment Letter, to be signed by both parties prior to, or following each session. "
        "These letters will detail the session description, date, assigned role, and agreed-upon payment.",
        "Facilitators may be assigned a specific role (e.g., Lead, Assistant, Technical Support) per "
        "session, which will be reflected in each Payment Letter. Compensation may vary accordingly.",
        "The Facilitator shall not be entitled to additional compensation unless explicitly outlined "
        "in the relevant Facilitator Payment Letter.",
    ]),
    ("6. Conflict of Interest", [
        "The Facilitator agrees to disclose any actual or potential conflicts of interest that may "
        "arise during their engagement and confirms that their participation will not conflict with "
        "other obligations.",
    ]),
    ("7. Termination", [
        "7.1 Voluntary Termination — Either Party may terminate this Agreement with one (1) month "
        "written notice.",
        "7.2 Termination for Cause — The Company may terminate this Agreement immediately upon the "
        "Facilitator's breach of terms, misconduct, or failure to fulfill obligations.",
        "7.3 Post-Termination Obligations — Upon termination, the Facilitator shall return or destroy "
        "all confidential materials and cease using any SpacePoint property or materials.",
    ]),
    ("8. Feedback and Intellectual Property", [
        "Any feedback, ideas, or contributions made by the Facilitator during the engagement shall "
        "become the sole property of SpacePoint. No additional compensation is due beyond the agreed fees.",
    ]),
    ("9. Governing Law and Dispute Resolution", [
        "This Agreement shall be governed by the laws of the United Arab Emirates. In case of any "
        "dispute, the Parties agree to first seek resolution through good-faith mediation. If "
        "mediation fails, the dispute shall be referred to arbitration under the Abu Dhabi Commercial "
        "Conciliation and Arbitration Centre (ADCCAC). The seat of arbitration shall be Abu Dhabi, and "
        "the proceedings shall be conducted in English unless otherwise agreed. The decision shall be "
        "final and binding.",
    ]),
]


def generate_contract_pdf(instructor_name: str, living_area: str) -> bytes:
    """Renders the Facilitators Agreement with the instructor name/location/
    date merge fields filled in. Returns PDF bytes (not written to disk)."""
    # %-d (no leading zero) is a glibc/macOS strftime extension Windows lacks
    # (Windows uses %#d) — strip a leading zero manually so this works on both.
    today = date.today().strftime("%d %B %Y").lstrip("0")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=25 * mm, rightMargin=25 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
    )
    story = [
        Paragraph("SpacePoint's Facilitators Agreement", _TITLE),
        Paragraph(
            f"This Facilitators Agreement (the “Agreement”) is entered into on {today}, "
            "by and between:", _BODY,
        ),
        Paragraph(
            "SpacePoint FZC, a company registered at the Sharjah Research Technology and Innovation "
            "Park (SRTIP), United Arab Emirates (“Company”),", _BODY,
        ),
        Paragraph(
            f"and {instructor_name}, residing in {living_area}, United Arab Emirates "
            "(“Facilitator”).", _BODY,
        ),
        Paragraph(
            "The Company and the Facilitator may each be referred to herein as a “Party” and "
            "collectively as the “Parties.”", _BODY,
        ),
    ]
    for heading, paragraphs in _SECTIONS:
        story.append(Paragraph(heading, _HEADING))
        for p in paragraphs:
            story.append(Paragraph(p, _BODY))

    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph(
        "IN WITNESS WHEREOF, the Parties hereto have executed this Agreement as of the date first "
        "written above.", _BODY,
    ))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        f"For SpacePoint FZC — Name: {settings.DEFAULT_SIGNATORY_NAME}, "
        f"{settings.DEFAULT_SIGNATORY_TITLE}. Date: {today}.", _BODY,
    ))
    story.append(Paragraph(
        f"Facilitator — Name: {instructor_name}. Date: {today}. Signature: ______________________",
        _BODY,
    ))

    doc.build(story)
    return buf.getvalue()
