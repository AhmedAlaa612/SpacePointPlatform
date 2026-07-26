"""Ticket image renderer — cairosvg base + PIL overlays with clipping.

Pipeline:
  1. Strip embedded PNGs and patterns from SVG → cairosvg renders base
     (background path + dashed line + clip-path).
  2. Composite background pattern, logo, wrapped text, and styled QR
     via PIL — all clipped to the rounded-rect clip-path.
"""

import base64
import io
import os
import re

import cairosvg
import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer

_STATIC_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "static")
)
_TEMPLATES_DIR = os.path.join(_STATIC_DIR, "templates", "tickets")
_DEFAULT_SVG = os.path.join(_TEMPLATES_DIR, "ticket.svg")
_FONTS_DIR = os.path.join(_STATIC_DIR, "fonts")
_RUSSO_ONE = os.path.join(_FONTS_DIR, "RussoOne-Regular.ttf")
_QR_LOGO = os.path.join(_STATIC_DIR, "spacepoint_logo.png")

TICKET_W, TICKET_H = 525, 979
CORNER_RADIUS = 18

# Text bounding boxes (estimated from SVG element positions)
# program_name: centered within the ticket's upper text frame
PG_CENTER_X, PG_Y, PG_MAX_W, PG_LINE_H = TICKET_W // 2, 218, 330, 32
# dates: x≈74 y≈357
DT_X, DT_Y, DT_MAX_W, DT_LINE_H = 74, 357, 430, 32
# location: x≈74 y≈470
LC_X, LC_Y, LC_MAX_W, LC_LINE_H = 74, 470, 430, 32
# student_name: x≈142 y≈621
SN_X, SN_Y, SN_MAX_W, SN_LINE_H = 142, 621, 330, 32

TEXT_COLOR = (255, 255, 255)
TEXT_FONT_SIZE = 26

# Logo
LOGO_X, LOGO_Y, LOGO_W, LOGO_H = 80, 34, 365, 85

# Background pattern
BG_X, BG_Y, BG_W, BG_H = 337, 194, 512, 379
BG_ANGLE = 6
BG_OPACITY = 0.62

# QR
QR_X, QR_Y, QR_W, QR_H = 163, 735, 200, 200
QR_MARGIN = 5
# The SpacePoint wordmark is intentionally presented in a wide, shallow clear
# area.  This keeps it legible without treating the wordmark like a square app
# icon, and leaves enough QR modules around it to scan reliably.
QR_LOGO_PAD_W, QR_LOGO_PAD_H = 106, 58
QR_LOGO_PAD_RADIUS = 10
QR_LOGO_W, QR_LOGO_H = 86, 20


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        if os.path.exists(_RUSSO_ONE):
            return ImageFont.truetype(_RUSSO_ONE, size)
    except Exception:
        pass
    return ImageFont.load_default()


def _make_rounded_rect_mask(w: int, h: int, r: int) -> Image.Image:
    """Return an RGBA mask with a white rounded rectangle on transparent."""
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=r, fill=(255, 255, 255, 255))
    return mask


def _extract_embedded_pngs(svg: str) -> tuple[bytes | None, bytes | None]:
    images = re.findall(
        r'<image[^>]*?xlink:href="data:image/png;base64,([A-Za-z0-9+/=]+)"',
        svg,
    )
    if len(images) >= 2:
        return base64.b64decode(images[0]), base64.b64decode(images[1])
    if len(images) == 1:
        return base64.b64decode(images[0]), None
    return None, None


def _strip_svg(svg: str) -> str:
    """Strip images, patterns, text, and QR rect for cairosvg."""
    svg = re.sub(
        r'<image[^>]*xlink:href="data:image/png;base64,[A-Za-z0-9+/=]+"[^>]*/>',
        "",
        svg,
    )
    svg = re.sub(r"<pattern[^>]*>.*?</pattern>", "", svg, flags=re.DOTALL)
    svg = re.sub(r"<text[^>]*>.*?</text>", "", svg, flags=re.DOTALL)
    # Remove pattern rects (they reference deleted patterns)
    svg = re.sub(
        r'<rect[^>]*fill="url\(#[^)]+\)"[^>]*/>',
        "",
        svg,
    )
    # Remove QR placeholder
    svg = svg.replace(
        '<rect x="163" y="735" width="200" height="200" fill="#D9D9D9"/>',
        "",
    )
    return svg


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int,
               max_w: int, line_h: int, font: ImageFont.FreeTypeFont,
               fill, *, centered: bool = False) -> int:
    """Draw text wrapped to max_w. Returns the y after the last line drawn."""
    words = text.split()
    if not words:
        return y
    lines = []
    cur = ""
    for w in words:
        test = cur + (" " if cur else "") + w
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    for i, line in enumerate(lines):
        draw.text(
            (x, y + i * line_h),
            line,
            fill=fill,
            font=font,
            anchor="ms" if centered else "ls",
        )
    return y + len(lines) * line_h


def _generate_styled_qr(ticket_token: str, size: int) -> Image.Image:
    """Styled QR encoding the raw token — staff scanner sends this directly
    to POST /sessions/checkin. No URL wrapping needed."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(ticket_token)
    qr.make(fit=True)

    kwargs = dict(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
    )
    img = qr.make_image(**kwargs)
    pil_img = img.get_image() if hasattr(img, "get_image") else img
    return pil_img.convert("RGBA").resize((size, size), Image.LANCZOS)


def render_ticket_png(
    student_name: str,
    program_name: str,
    dates: str,
    location: str | None,
    ticket_token: str,
) -> bytes:
    """Render full ticket PNG with all overlays."""
    with open(_DEFAULT_SVG, "r", encoding="utf-8") as fh:
        svg = fh.read()

    img_bg, img_logo = _extract_embedded_pngs(svg)

    svg = _strip_svg(svg)

    # Render base via cairosvg
    base_png = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=TICKET_W,
        output_height=TICKET_H,
    )
    ticket = Image.open(io.BytesIO(base_png)).convert("RGBA")
    overlay = Image.new("RGBA", ticket.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ── 1. Background pattern ──
    if img_bg:
        try:
            pattern = Image.open(io.BytesIO(img_bg)).convert("RGBA")
            pattern = pattern.resize((BG_W, BG_H), Image.LANCZOS)
            pattern = pattern.rotate(BG_ANGLE, expand=False, center=(0, 0),
                                     fillcolor=(0, 0, 0, 0))
            r, g, b, a = pattern.split()
            a = a.point(lambda v: int(v * BG_OPACITY))
            pattern = Image.merge("RGBA", (r, g, b, a))
            overlay.paste(pattern, (BG_X, BG_Y), pattern)
        except Exception:
            pass

    # ── 2. Logo ──
    if img_logo:
        try:
            logo = Image.open(io.BytesIO(img_logo)).convert("RGBA")
            logo = logo.resize((LOGO_W, LOGO_H), Image.LANCZOS)
            overlay.paste(logo, (LOGO_X, LOGO_Y), logo)
        except Exception:
            pass

    # ── 3. Text with wrapping ──
    font = _load_font(TEXT_FONT_SIZE)
    if font is not None:
        _wrap_text(
            draw, program_name, PG_CENTER_X, PG_Y, PG_MAX_W, PG_LINE_H, font, TEXT_COLOR,
            centered=True,
        )
        _wrap_text(draw, dates, DT_X, DT_Y, DT_MAX_W, DT_LINE_H, font, TEXT_COLOR)
        _wrap_text(draw, location or "", LC_X, LC_Y, LC_MAX_W, LC_LINE_H, font, TEXT_COLOR)
        _wrap_text(draw, student_name, SN_X, SN_Y, SN_MAX_W, SN_LINE_H, font, TEXT_COLOR)

    # ── 4. Styled QR ──
    try:
        qr_img = _generate_styled_qr(ticket_token, QR_W)
        qr_bg = Image.new(
            "RGBA", (QR_W + QR_MARGIN * 2, QR_H + QR_MARGIN * 2), (255, 255, 255, 255)
        )
        overlay.paste(qr_bg, (QR_X - QR_MARGIN, QR_Y - QR_MARGIN), qr_bg)
        overlay.paste(qr_img, (QR_X, QR_Y), qr_img)

        if os.path.exists(_QR_LOGO):
            logo = Image.open(_QR_LOGO).convert("RGBA")
            logo.thumbnail((QR_LOGO_W, QR_LOGO_H), Image.LANCZOS)
            pad_x = QR_X + (QR_W - QR_LOGO_PAD_W) // 2
            pad_y = QR_Y + (QR_H - QR_LOGO_PAD_H) // 2
            logo_bg = Image.new("RGBA", (QR_LOGO_PAD_W, QR_LOGO_PAD_H), (0, 0, 0, 0))
            ImageDraw.Draw(logo_bg).rounded_rectangle(
                [(0, 0), (QR_LOGO_PAD_W - 1, QR_LOGO_PAD_H - 1)],
                radius=QR_LOGO_PAD_RADIUS,
                fill=(255, 255, 255, 255),
            )
            overlay.paste(logo_bg, (pad_x, pad_y), logo_bg)
            logo_x = QR_X + (QR_W - logo.width) // 2
            logo_y = QR_Y + (QR_H - logo.height) // 2
            overlay.paste(logo, (logo_x, logo_y), logo)
    except Exception:
        pass

    # ── Apply rounded-rect clip mask ──
    mask = _make_rounded_rect_mask(TICKET_W, TICKET_H, CORNER_RADIUS)
    overlay = Image.composite(overlay, Image.new("RGBA", overlay.size, (0, 0, 0, 0)), mask)

    result = Image.alpha_composite(ticket, overlay)
    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
