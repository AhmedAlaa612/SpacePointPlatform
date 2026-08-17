"""Instructor agreement letter — docxtpl fills DOCX template → LibreOffice → PDF.

Template: app/static/templates/docx/agreement.docx
Placeholders: {{ today }}  {{ instructor_name }}  {{ living_area }}

Signing (Phase 6): the template's signature block is a single paragraph
(index 44) with two tab-column "Name/Date/Signature" rows. The admin's
NAME and signature image are baked into the template as static content —
but {{ today }} (run 21) is the admin's DATE field, a real Jinja
placeholder, not static, and the Facilitator's date (run 32) is filled in
by `_fill_facilitator_date` directly on the rendered document. Both are
always filled with the same value: `signed_date` once the instructor has
actually signed, otherwise today's date (2026-08-09: previously left
blank pre-signing — changed on operator request so an unsigned contract
still shows a live, correct preview of both parties' dates rather than
looking half-finished). Run indices below were confirmed by rendering the
template and inspecting the resulting python-docx runs (docxtpl preserves
run boundaries for simple {{ var }} substitutions).

The Facilitator's SIGNATURE IMAGE (run 44's last run) is the only piece
still gated on actually signing — `_add_facilitator_signature_image` is
only called when `instructor_signature_b64` is provided.

The Facilitator "Date:" row is column-aligned by `_fill_facilitator_date`,
which keeps all 7 tabs at runs 24-30 and pads the date with a single space
rather than a tab. See that function for the measured x-positions.
"""

import base64
import copy
import io
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Emu
from docxtpl import DocxTemplate

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
# Empirically matched (measured off a rendered PDF) to the Facilitator
# "Signature:" tab-stop position, offset the same ~0.8" past the label that
# the admin's own anchored signature sits past its label. See
# `_add_facilitator_signature_image`.
_FACILITATOR_SIG_OFFSET_H = 4_849_000

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


def _fill_facilitator_date(doc: Document, date_str: str) -> None:
    """Fill the Facilitator "Date:" field on the signature paragraph.

    Run 31 = the (blank) Facilitator "Date:" label, run 32 = a <w:tab/>
    element followed by padding spaces, overwritten here with the date.

    Both the label's column and the gap after it were calibrated by
    measuring word x-positions in the rendered PDF (letter page, 1"
    margins => default 0.5"/36pt tab stops from x=72):

      * all 7 tabs at runs 24-30 are kept. The admin's date wraps onto its
        own visual line ending at x~175, and those 7 tabs walk
        180 -> 216 -> ... -> 396, putting this label at x=396.1 — exactly
        the "Name:"/"Signature:" column. Dropping tabs here (an earlier
        calibration) left the label at x=324, well left of its column.
      * run 32's <w:tab/> is removed and the date padded with a single
        space, mirroring the admin's own "Date: " + date runs exactly. The
        tab was snapping the date to the next stop instead, opening a gap
        wider than the admin's. Note the tab is an ELEMENT, not a "\t" in
        the run's w:t — rewriting only the text leaves it in place.
    """
    p = doc.paragraphs[_SIGNATURE_PARA_IDX]
    date_run = p.runs[32]._r
    for tab in date_run.findall(qn("w:tab")):
        date_run.remove(tab)
    wt = date_run.find(qn("w:t"))
    if wt is not None:
        wt.text = f" {date_str}"
        wt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _add_facilitator_signature_image(doc: Document, signature_b64: str) -> None:
    """Anchor the instructor's signature at the Facilitator column.

    A plain inline picture (the original approach — `run.add_picture()`
    appended after the last run) flows with the paragraph's own text layout.
    This paragraph is tab-heavy enough that the trailing image can fail to
    fit on the line and wrap down to a new line starting at the paragraph's
    LEFT margin instead of staying under "Facilitator" — landing visually on
    top of, or beside, the admin's own signature instead of in its own
    column. The admin's signature avoids this because it's a fixed-position
    ANCHOR, not inline — so it's placed the same way here: clone the admin's
    anchor XML, swap its image, and shift only the horizontal offset to the
    Facilitator column. Same technique as `payment_letter.py`'s
    `_inject_signatures`.
    """
    p = doc.paragraphs[_SIGNATURE_PARA_IDX]
    anchor_run = next(
        (r for r in p._p.findall(qn("w:r")) if r.find(qn("w:drawing")) is not None),
        None,
    )
    if anchor_run is None:
        return

    extent = anchor_run.find(".//" + qn("wp:extent"))
    sig_cx, sig_cy = int(extent.get("cx")), int(extent.get("cy"))

    raw = signature_b64.split(",", 1)[-1] if "," in signature_b64 else signature_b64
    tmp = doc.add_paragraph()
    tmp.add_run().add_picture(io.BytesIO(base64.b64decode(raw)), width=Emu(sig_cx), height=Emu(sig_cy))
    blip = tmp._p.find(".//" + qn("a:blip"))
    new_rId = blip.get(f"{{{_R_NS}}}embed")
    tmp._p.getparent().remove(tmp._p)

    instr_run = copy.deepcopy(anchor_run)
    instr_run.find(".//" + qn("a:blip")).set(f"{{{_R_NS}}}embed", new_rId)

    pos_h = instr_run.find(".//" + qn("wp:positionH"))
    pos_h.find(qn("wp:posOffset")).text = str(_FACILITATOR_SIG_OFFSET_H)

    # Unique shape IDs — must not collide with the admin's own anchor.
    instr_run.find(".//" + qn("wp:docPr")).set("id", "9001")
    instr_run.find(".//" + qn("wp:docPr")).set("name", "instructor_sig")
    instr_run.find(".//" + qn("pic:cNvPr")).set("id", "9001")
    instr_run.find(".//" + qn("pic:cNvPr")).set("name", "instructor_sig")

    p._p.append(instr_run)


def generate_contract_pdf(
    instructor_name: str,
    living_area: str,
    *,
    contract_date: str | None = None,
    instructor_signature_b64: str | None = None,
) -> bytes:
    """`contract_date` is whatever date should print on the PDF — the frozen
    `instructor_since` date for an unsigned preview, or the real signing
    timestamp when `instructor_signature_b64` is given. Falls back to
    today only if the caller has no date on file at all (shouldn't happen
    once instructor_since is always set — see instructor_profile.py)."""
    is_signing = bool(instructor_signature_b64)
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
    _fill_facilitator_date(doc, today)
    if is_signing:
        _add_facilitator_signature_image(doc, instructor_signature_b64)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    return _libreoffice_to_pdf(buf.getvalue())
