"""Instructor agreement letter — docxtpl fills DOCX template → LibreOffice → PDF.

Template: app/static/templates/docx/agreement.docx
Placeholders: {{ today }}  {{ instructor_name }}  {{ living_area }}
"""

import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

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


def _libreoffice_to_pdf(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.docx"
        src.write_bytes(docx_bytes)
        subprocess.run(
            [_SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
            check=True, timeout=60, capture_output=True,
        )
        return (Path(tmp) / "doc.pdf").read_bytes()


def generate_contract_pdf(instructor_name: str, living_area: str) -> bytes:
    d = date.today()
    today = f"{d.day} {d.strftime('%B %Y')}"  # "26 June 2026" (cross-platform)
    tpl = DocxTemplate(str(_TEMPLATE))
    tpl.render({
        "today": today,
        "instructor_name": instructor_name,
        "living_area": living_area,
    })
    import io
    buf = io.BytesIO()
    tpl.save(buf)
    buf.seek(0)
    return _libreoffice_to_pdf(buf.getvalue())
