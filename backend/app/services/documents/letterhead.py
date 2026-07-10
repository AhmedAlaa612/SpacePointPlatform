"""Reusable branded header/footer for ReportLab-generated letters.

Matches the header/footer already baked into the Word header/footer parts of
payment_letter.docx and agreement.docx (banner color #231134, cropped
SPACE. logo, footer with copyright / page link / page numbers) — extracted
directly from those files so the two pipelines produce a visually identical
letterhead.
"""

from pathlib import Path

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as _canvas

_STATIC_DIR = Path(__file__).parent.parent.parent / "static"
LOGO_PATH = _STATIC_DIR / "branding" / "logo_on_dark.png"

BANNER_COLOR = HexColor("#231134")
LINK_COLOR = HexColor("#0563C1")

PAGE_W, PAGE_H = A4
BANNER_HEIGHT = 21 * 2.834645  # 21mm in points (1mm = 2.834645pt)
FOOTER_HEIGHT = 24  # points reserved at the bottom for footer text

_logo_reader = ImageReader(str(LOGO_PATH)) if LOGO_PATH.exists() else None


def draw_header(c: _canvas.Canvas) -> None:
    """Full-bleed dark banner across the top of the page with the logo on it."""
    c.saveState()
    c.setFillColor(BANNER_COLOR)
    c.rect(0, PAGE_H - BANNER_HEIGHT, PAGE_W, BANNER_HEIGHT, stroke=0, fill=1)

    if _logo_reader is not None:
        logo_w, logo_h = _logo_reader.getSize()
        aspect = logo_h / float(logo_w)
        draw_w = 130
        draw_h = draw_w * aspect
        x = 36
        y = PAGE_H - BANNER_HEIGHT + (BANNER_HEIGHT - draw_h) / 2
        c.drawImage(
            _logo_reader, x, y, width=draw_w, height=draw_h,
            mask="auto", preserveAspectRatio=True,
        )
    c.restoreState()


def draw_footer(c: _canvas.Canvas, page_num: int, total_pages: int) -> None:
    c.saveState()
    c.setFont("Helvetica", 9)
    c.setFillColor(black)

    baseline_1 = 26
    baseline_2 = 14

    c.drawString(36, baseline_1, "Copyright © 2026 SpacePoint. All rights reserved.")

    link_text = "https://www.spacepoint.ae"
    link_width = c.stringWidth(link_text, "Helvetica", 9)
    link_x = PAGE_W - 36 - link_width
    c.setFillColor(LINK_COLOR)
    c.drawString(link_x, baseline_1, link_text)
    c.line(link_x, baseline_1 - 1.5, link_x + link_width, baseline_1 - 1.5)
    c.linkURL(
        link_text, (link_x, baseline_1 - 2, link_x + link_width, baseline_1 + 9),
        relative=0,
    )

    c.setFillColor(black)
    page_label = f"Page {page_num} of {total_pages}"
    label_width = c.stringWidth(page_label, "Helvetica", 9)
    c.drawString((PAGE_W - label_width) / 2, baseline_2, page_label)
    c.restoreState()


class LetterheadCanvas(_canvas.Canvas):
    """Draws the banner on every page immediately, and defers the footer
    (which needs the total page count) until save() — the standard ReportLab
    "Page X of Y" pattern.
    """

    def __init__(self, *args, **kwargs):
        _canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            # __dict__.update() above just rolled back _annotationCount to
            # whatever it was when this page's showPage() ran (0, since no
            # links existed yet during the first pass) — every page would
            # then mint the same annotation name ("NUMBER1") for its footer
            # link. Force it page-unique before drawing the link.
            self._annotationCount = i * 1000
            draw_header(self)
            draw_footer(self, i, total_pages)
            _canvas.Canvas.showPage(self)
        _canvas.Canvas.save(self)


TOP_MARGIN = BANNER_HEIGHT + 14
BOTTOM_MARGIN = FOOTER_HEIGHT + 20
