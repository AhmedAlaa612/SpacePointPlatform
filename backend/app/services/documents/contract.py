"""Instructor agreement letter — docxtpl fills DOCX template → LibreOffice → PDF.

Template: app/static/templates/docx/agreement.docx
Placeholders: {{ today }}  {{ instructor_name }}  {{ living_area }}

Signing (Phase 6): the template's signature block is a single paragraph
(index 44) with two tab-column "Name/Date/Signature" rows. The admin's name,
date and signature are already baked into the template as static content
(an anchored image) — only the Facilitator (instructor) side is blank,
filled in here at signing time. Run indices below were confirmed by
rendering the template and inspecting the resulting python-docx runs
(docxtpl preserves run boundaries for simple {{ var }} substitutions).
"""

import base64
import io
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches
from docxtpl import DocxTemplate

_TEMPLATE = (
    Path(__file__).parent.parent.parent
    / "static" / "templates" / "docx" / "agreement.docx"
)

_SOFFICE = (
    r"C:\Program Files\LibreOffice\program\soffice.exe"
    if sys.platform == "win32"
    else "libreoffice"
)

_SIGNATURE_PARA_IDX = 44


def _libreoffice_to_pdf(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.docx"
        src.write_bytes(docx_bytes)
        subprocess.run(
            [_SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
            check=True, timeout=60, capture_output=True,
        )
        return (Path(tmp) / "doc.pdf").read_bytes()


def _fill_facilitator_signature(doc: Document, signed_date: str, signature_b64: str) -> None:
    """Fill the blank Facilitator Date + Signature on the signature paragraph.

    Run 31 = the (blank) Facilitator "Date:" label, run 32 = "\t" + padding
    spaces to overwrite with the date. Run 43 = the (blank) Facilitator
    "Signature:" label, the paragraph's last run — a new inline-picture run
    is appended right after it, which reliably continues on the same line
    (or wraps below it) without touching any of the preceding tab-stop math.
    """
    p = doc.paragraphs[_SIGNATURE_PARA_IDX]
    date_run = p.runs[32]._r
    wt = date_run.find(qn("w:t"))
    if wt is not None:
        wt.text = f"\t{signed_date}"
        wt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    raw = signature_b64.split(",", 1)[-1] if "," in signature_b64 else signature_b64
    p.add_run().add_picture(io.BytesIO(base64.b64decode(raw)), width=Inches(1.1))


def generate_contract_pdf(
    instructor_name: str,
    living_area: str,
    *,
    signed_date: str | None = None,
    instructor_signature_b64: str | None = None,
) -> bytes:
    d = date.today()
    today = f"{d.day} {d.strftime('%B %Y')}"  # "26 June 2026" (cross-platform)
    tpl = DocxTemplate(str(_TEMPLATE))
    tpl.render({
        "today": today,
        "instructor_name": instructor_name,
        "living_area": living_area,
    })
    buf = io.BytesIO()
    tpl.save(buf)
    buf.seek(0)

    if instructor_signature_b64:
        doc = Document(buf)
        _fill_facilitator_signature(doc, signed_date or today, instructor_signature_b64)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

    return _libreoffice_to_pdf(buf.getvalue())
