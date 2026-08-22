"""Instructor agreement letter — docxtpl fills DOCX template → LibreOffice → PDF.

Template: app/static/templates/docx/agreement.docx
Placeholders: {{ today }}  {{ instructor_name }}  {{ living_area }}

Signing (Phase 6): the template's signature block is a single paragraph with
two tab-column "Name/Date/Signature" rows, and the SpacePoint signatory's name
and signature image are baked into it as static content. That paragraph is not
rendered as-is — `signature_block.replace_signature_block` swaps it for a
borderless two-column table before the PDF is produced, because the template's
own tab-and-padding layout collapses as soon as a name is longer than the pair
it was measured against (see that module). The SpacePoint signatory's name is
read back out of the template so the block still follows whatever the template
says, and their signature image is lifted out of the template's anchor and
redrawn inline in its own cell.

Both parties' dates are always filled with the same value — whatever
`contract_date` the caller passes, which is `instructor_since`, the day the
role was granted (2026-08-09: previously left blank pre-signing — changed on
operator request so an unsigned contract still shows a live, correct preview
of both parties' dates rather than looking half-finished; 2026-08-22: signing
used to overwrite it with the signing date, so the date moved the moment you
signed). The Facilitator's SIGNATURE IMAGE is the only piece that changes on
signing.
"""

import io
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from docx import Document
from docxtpl import DocxTemplate

from app.services.documents.signature_block import (
    SignatureParty,
    column_headings,
    decode_signature,
    replace_signature_block,
    template_signature_image,
)

_TEMPLATE = (
    Path(__file__).parent.parent.parent
    / "static" / "templates" / "docx" / "agreement.docx"
)

_SOFFICE = (
    r"C:\Program Files\LibreOffice\program\soffice.exe"
    if sys.platform == "win32"
    else "libreoffice"
)

# Fallbacks for the two things the signature block takes from the template
# itself — used only if the template is ever restructured past recognition, so
# a layout change degrades to a stale name rather than an unsigned-looking PDF.
_SPACEPOINT_HEADING = "For SpacePoint FZC"
_FACILITATOR_HEADING = "Facilitator"
_SPACEPOINT_SIGNATORY = "Abdullah Alsalmani"


def format_contract_date(d: date) -> str:
    """"26 June 2026" (cross-platform — no %-d/%#d strftime flag needed).
    Shared by every caller that builds a `contract_date` for
    generate_contract_pdf, so the unsigned-preview and signed dates are
    never formatted two different ways again."""
    return f"{d.day} {d.strftime('%B %Y')}"


def _libreoffice_to_pdf(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.docx"
        src.write_bytes(docx_bytes)
        subprocess.run(
            [_SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
            check=True, timeout=60, capture_output=True,
        )
        return (Path(tmp) / "doc.pdf").read_bytes()


def _find_signature_paragraph(doc: Document):
    """The template's signature block, located by content rather than index.

    It used to be addressed as paragraphs[44]; matching on the text survives
    editors adding or removing a clause above it.
    """
    for para in doc.paragraphs:
        text = para.text
        if _SPACEPOINT_HEADING in text and "Signature:" in text:
            return para
    raise ValueError("agreement.docx: signature block paragraph not found")


def _spacepoint_signatory(text: str) -> str:
    """The SpacePoint signatory's name, as written in the template.

    In the template the name is padded out with the run of spaces that used to
    hold the column open, so it ends at the first double space, tab or newline.
    """
    match = re.search(r"Name:[ \t]*(.+?)(?:[ ]{2,}|\t|\n|$)", text)
    return match.group(1).strip() if match else _SPACEPOINT_SIGNATORY


def generate_contract_pdf(
    instructor_name: str,
    living_area: str,
    *,
    contract_date: str | None = None,
    instructor_signature_b64: str | None = None,
) -> bytes:
    """`contract_date` is whatever date should print on the PDF: the frozen
    `instructor_since` date, for the unsigned preview and the signed copy
    alike — signing does not move it (the real signing timestamp lives in
    `contract_signed_at`, not on the page). Falls back to today only if the
    caller has no date on file at all (shouldn't happen once instructor_since
    is always set — see instructor_profile.py)."""
    today = contract_date or format_contract_date(date.today())

    tpl = DocxTemplate(str(_TEMPLATE))
    tpl.render({
        "today": today,
        "instructor_name": instructor_name,
        "living_area": living_area,
    })
    buf = io.BytesIO()
    tpl.save(buf)
    buf.seek(0)

    doc = Document(buf)
    para = _find_signature_paragraph(doc)
    admin_heading, facilitator_heading = column_headings(
        para.text, (_SPACEPOINT_HEADING, _FACILITATOR_HEADING)
    )
    admin_signature, signature_size = template_signature_image(doc, para)
    replace_signature_block(
        doc,
        [para],
        SignatureParty(
            heading=admin_heading,
            name=_spacepoint_signatory(para.text),
            date=today,
            signature=admin_signature,
        ),
        SignatureParty(
            heading=facilitator_heading,
            name=instructor_name,
            date=today,
            signature=decode_signature(instructor_signature_b64),
        ),
        signature_size=signature_size,
    )

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    return _libreoffice_to_pdf(buf.getvalue())
