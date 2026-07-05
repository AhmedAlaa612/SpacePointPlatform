"""Consolidated applicant dossier PDF — the admin "Export Consolidated PDF" on the
assessment page (parity with the source's admin_dashboard.html). Builds a cover
sheet + one divider sheet per module, and merges in each module's uploaded PDF
submission after its divider.

Cover/divider pages are drawn with ReportLab; merging uses pypdf. Non-PDF or
unreadable submissions are skipped gracefully (their divider still notes the file).
"""

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_ACCENT = HexColor("#7C3AED")
_MUTED = HexColor("#666666")


def _text_page(heading: str, lines: list[str], big: bool = False) -> io.BytesIO:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 60 * mm

    c.setFillColor(_ACCENT)
    c.setFont("Helvetica-Bold", 26 if big else 20)
    for chunk in _wrap(heading, 34 if big else 44):
        c.drawString(25 * mm, y, chunk)
        y -= (12 if big else 9) * mm

    y -= 4 * mm
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 12)
    for line in lines:
        for chunk in _wrap(line, 80):
            c.drawString(25 * mm, y, chunk)
            y -= 7 * mm

    c.setFillColor(_MUTED)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(25 * mm, 15 * mm, "SpacePoint — Applicant Assessment Dossier")
    c.save()
    buf.seek(0)
    return buf


def _wrap(text: str, width: int) -> list[str]:
    text = text or ""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def build_applicant_dossier_pdf(
    applicant_name: str,
    applicant_email: str,
    status: str,
    modules: list[dict],
) -> bytes:
    """`modules`: list of {title, status, filename, pdf_bytes(optional)}."""
    writer = PdfWriter()

    cover = _text_page(
        f"Assessment Dossier — {applicant_name}",
        [
            f"Email: {applicant_email}",
            f"Application status: {status.replace('_', ' ').title()}",
            f"Modules with submissions: {sum(1 for m in modules if m.get('pdf_bytes'))} / {len(modules)}",
        ],
        big=True,
    )
    for p in PdfReader(cover).pages:
        writer.add_page(p)

    for i, m in enumerate(modules, 1):
        sub_status = (m.get("status") or "no submission").replace("_", " ").title()
        filename = m.get("filename") or "—"
        divider = _text_page(
            f"Module {i}: {m['title']}",
            [f"Submission status: {sub_status}", f"File: {filename}"],
        )
        for p in PdfReader(divider).pages:
            writer.add_page(p)

        pdf_bytes = m.get("pdf_bytes")
        if pdf_bytes:
            try:
                for p in PdfReader(io.BytesIO(pdf_bytes)).pages:
                    writer.add_page(p)
            except Exception:  # noqa: BLE001 — non-PDF / corrupt upload, skip its pages
                pass

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()
