"""Facilitator Payment Letter PDF — ported from the source app's
payment_service.py (already ReportLab — same stack, no conversion needed
beyond local-disk-path -> bytes and ORM-relationship-traversal -> explicit
caller-supplied data, matching this codebase's no-`relationship()` style).
"""

import base64
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import Image as RLImage

_STATIC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
_LOGO_PATH = os.path.join(_STATIC_DIR, "spacepoint_logo.png")

BRAND_DARK = colors.HexColor("#1a1135")
TABLE_HEADER_GREY = colors.HexColor("#d8d8d8")


def _draw_full_header(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#231134"))
    canvas.rect(0, 279 * mm, 210 * mm, 18 * mm, fill=1, stroke=0)
    if os.path.exists(_LOGO_PATH):
        canvas.drawImage(_LOGO_PATH, 20 * mm, 282 * mm, width=51.6 * mm, height=12 * mm, mask="auto")
    else:
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawString(20 * mm, 284 * mm, "SPACE.")
    canvas.restoreState()


def generate_payment_letter_pdf(
    *,
    instructor_name: str,
    reference: str,
    letter_date: str,
    sessions: list[dict],
    addons: list[dict],
    bank: dict | None,
    admin_signatory_name: str,
    admin_signature_bytes: bytes | None = None,
    instructor_signature_b64: str | None = None,
    signed_date: str | None = None,
) -> bytes:
    """Each session dict: {session_date, workshop_description, role, location,
    duration_hours, compensation_aed}. Each addon dict: {description,
    amount_aed, notes}. `bank`: {account_holder_name, bank_name, iban, swift_bic} or None.
    """
    base_total = sum(s["compensation_aed"] for s in sessions)
    addons_total = sum(a["amount_aed"] for a in addons)
    grand_total = base_total + addons_total

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=10 * mm, bottomMargin=20 * mm
    )
    styles = getSampleStyleSheet()
    story = [Spacer(1, 18 * mm)]

    title_style = ParagraphStyle("title", fontSize=13, fontName="Helvetica-Bold", textColor=BRAND_DARK,
                                  alignment=1, leading=18)
    story.append(Paragraph("<u><b>SpacePoint's Facilitator Payment Letter</b></u>", title_style))
    story.append(Spacer(1, 5 * mm))

    normal = ParagraphStyle("normal", fontSize=10, fontName="Helvetica", leading=16)
    bold_label = ParagraphStyle("bold_label", fontSize=10, fontName="Helvetica-Bold", leading=16)
    body_style = ParagraphStyle("body", fontSize=10, fontName="Helvetica", leading=14,
                                 textColor=colors.HexColor("#333333"))

    story.append(Paragraph(f"<b>Issued By:</b> SpacePoint FZC", normal))
    story.append(Paragraph(f"<b>Date:</b> {letter_date}", normal))
    story.append(Paragraph(f"<b>Facilitator:</b> {instructor_name}", normal))
    story.append(Paragraph(f"<b>Reference Agreement:</b> {reference or 'Facilitator Agreement'}", normal))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("<b>Subject: Confirmation of Scheduled Workshops and Payment Terms</b>",
                            ParagraphStyle("subject", fontSize=10, fontName="Helvetica-Bold", leading=14)))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "According to the Facilitator Agreement referenced above, this letter confirms the scope of work "
        "and agreed compensation for the following workshop sessions delivered by the Facilitator:",
        body_style,
    ))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("<b>Schedule of Workshops</b>", bold_label))
    story.append(Spacer(1, 2 * mm))
    ws_data = [["Session Date", "Workshop\nDescription", "Role", "Location", "Duration", "Compensation\n(AED)"]]
    for s in sessions:
        dur = s["duration_hours"] or 0
        ws_data.append([
            s["session_date"], s["workshop_description"], s["role"], s["location"],
            f"{dur:.0f} hours" if dur == int(dur) else f"{dur} hours",
            f"{s['compensation_aed']:,.0f}",
        ])
    ws_table = Table(ws_data, colWidths=[28 * mm, 40 * mm, 32 * mm, 38 * mm, 18 * mm, 22 * mm], repeatRows=1)
    ws_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_GREY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"), ("ALIGN", (-2, 0), (-2, -1), "CENTER"),
    ]))
    story.append(ws_table)
    story.append(Spacer(1, 5 * mm))

    if addons:
        story.append(Paragraph("<b>Optional Add-ons</b>", bold_label))
        story.append(Spacer(1, 2 * mm))
        ao_data = [["Description", "Amount (AED)", "Notes"]]
        for a in addons:
            ao_data.append([a["description"], f"{a['amount_aed']:,.0f}", a.get("notes") or ""])
        ao_table = Table(ao_data, colWidths=[65 * mm, 35 * mm, 68 * mm], repeatRows=1)
        ao_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_GREY),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#aaaaaa")),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        story.append(ao_table)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<b>Total Optional Add-ons: AED {addons_total:,.0f}</b>", body_style))
        story.append(Spacer(1, 4 * mm))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Total Compensation Payable: AED {grand_total:,.0f}</b>",
                            ParagraphStyle("total", fontSize=11, fontName="Helvetica-Bold", textColor=BRAND_DARK, leading=16)))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Payment will be made by bank transfer within 30 working days after submission of this signed "
        "letter, subject to verification.", body_style,
    ))
    story.append(Spacer(1, 6 * mm))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("<b>Facilitator Bank Details</b>", bold_label))
    story.append(Spacer(1, 2 * mm))
    if bank:
        for label, val in [
            ("Account Holder Name", bank.get("account_holder_name")), ("Bank Name", bank.get("bank_name")),
            ("IBAN", bank.get("iban")), ("SWIFT/BIC", bank.get("swift_bic")),
        ]:
            story.append(Paragraph(f"• <b>{label}:</b> {val or '—'}", body_style))
    else:
        story.append(Paragraph("• <i>Bank details not yet provided by instructor.</i>", body_style))
    story.append(Spacer(1, 6 * mm))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("<b>Signatures</b>", bold_label))
    story.append(Spacer(1, 4 * mm))

    sp_cell = [Paragraph("<b>For SpacePoint FZC</b>", body_style), Spacer(1, 1 * mm),
               Paragraph(f"Name: {admin_signatory_name}", body_style), Spacer(1, 1 * mm)]
    if admin_signature_bytes:
        sp_cell.append(RLImage(io.BytesIO(admin_signature_bytes), width=30 * mm, height=12 * mm))
    else:
        sp_cell.append(Paragraph("Signature: _______________", body_style))
    sp_cell += [Spacer(1, 1 * mm), Paragraph(f"Date: {letter_date}", body_style)]

    inst_cell = [Paragraph("<b>Facilitator</b>", body_style), Spacer(1, 1 * mm),
                 Paragraph(f"Name: {instructor_name}", body_style), Spacer(1, 1 * mm)]
    if instructor_signature_b64:
        sig_bytes = base64.b64decode(instructor_signature_b64.split(",")[-1])
        inst_cell.append(RLImage(io.BytesIO(sig_bytes), width=30 * mm, height=12 * mm))
    else:
        inst_cell.append(Paragraph("Signature: _______________", body_style))
    inst_cell += [Spacer(1, 1 * mm), Paragraph(f"Date: {signed_date or '_______________'}", body_style)]

    sig_table = Table([[sp_cell, inst_cell]], colWidths=[85 * mm, 85 * mm])
    sig_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(sig_table)

    doc.build(story, onFirstPage=_draw_full_header, onLaterPages=_draw_full_header)
    return buf.getvalue()
