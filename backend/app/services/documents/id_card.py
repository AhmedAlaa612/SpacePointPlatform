"""On-the-fly ID card renderer — SVG template + PIL overlays.

Architecture (PLAN §4.5 / §8.2):
  - Template: frame.svg stored on disk (or admin-uploaded per-role in storage).
    The SVG has a <tspan>Instructor</tspan> placeholder that is replaced with
    the actual role label at render time.
  - Font: Russo One is embedded as base64 @font-face inside the SVG before
    rendering so cairosvg always produces the correct typography regardless of
    what is installed on the host.
  - Rendering pipeline:
      1. Load SVG → inject font → swap role text → cairosvg → PNG bytes
      2. Overlay circular profile photo (center of card) via PIL
      3. Overlay LinkedIn QR code (bottom-right area) via PIL
  - Storage: only the stable card_id value is persisted in the `id_cards` table.
    Rendered images are NEVER stored; they are generated on every GET request.

Role-label map → human-readable display name used on the card.
"""

import base64
import io
import os
import re
import uuid
from datetime import datetime, timezone

import cairosvg
import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.pil import PilImage
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.enums import UserRole
from app.models.id_card import IdCard
from app.models.user import User
from app.services import storage

# ── Paths ─────────────────────────────────────────────────────────────────────
_STATIC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
_TEMPLATES_DIR = os.path.join(_STATIC_DIR, "templates", "id_cards")
_FONTS_DIR = os.path.join(_STATIC_DIR, "fonts")
_DEFAULT_SVG = os.path.join(_TEMPLATES_DIR, "id_front.svg")
_RUSSO_ONE = os.path.join(_FONTS_DIR, "RussoOne-Regular.ttf")

# Card dimensions (must match SVG viewBox)
CARD_W, CARD_H = 359, 568

# Original template dimensions (used for scaling)
ORIG_W, ORIG_H = 638, 1011

# Scaled coordinates for the front card elements (based on original 638x1011 coordinates)
PHOTO_DIAMETER = int(220 * (CARD_W / ORIG_W))  # 123 px
PHOTO_CX = int(319 * (CARD_W / ORIG_W))        # 179 px
PHOTO_CY = int(370 * (CARD_H / ORIG_H))        # 207 px

NAME_CX = int(319 * (CARD_W / ORIG_W))          # 179 px
NAME_Y = int(505 * (CARD_H / ORIG_H))           # 283 px
NAME_FONT_SIZE = int(34 * (CARD_W / ORIG_W))    # 19 px

QR_SIZE = int(190 * (CARD_W / ORIG_W))          # 106 px
QR_X = int((319 - 95) * (CARD_W / ORIG_W))      # 126 px
QR_Y = int(705 * (CARD_H / ORIG_H))             # 396 px

# Purple bar vertical center coordinates in 359x568 template:
# The purple rect is y=526, height=42. Center is 526 + 21 = 547.
ROLE_BAR_Y = 547
ROLE_FONT_SIZE = 26

# Back card constants (matching template size of 638x1011)
BACK_ID_LABEL_XY, BACK_ID_VALUE_XY = (60, 295), (60, 320)
BACK_DATE_LABEL_XY, BACK_DATE_VALUE_XY = (60, 400), (60, 425)
BACK_LABEL_COLOR, BACK_VALUE_COLOR = (160, 130, 200), (255, 255, 255)
BACK_LABEL_FONT_SIZE, BACK_VALUE_FONT_SIZE = 13, 26

def _back_template_path(role: UserRole) -> str:
    path = os.path.join(_TEMPLATES_DIR, f"{role.value}_back.png")
    if os.path.exists(path):
        return path
    return os.path.join(_TEMPLATES_DIR, "id_back.png")

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        if os.path.exists(_RUSSO_ONE):
            return ImageFont.truetype(_RUSSO_ONE, size)
    except Exception:
        pass
    import reportlab
    vera_dir = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        os.path.join(vera_dir, "VeraBd.ttf" if bold else "Vera.ttf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def render_card_back_png(
    role: UserRole,
    card_id: str,
    issue_date: datetime,
) -> bytes:
    path = _back_template_path(role)
    card = Image.open(path).convert("RGBA")
    draw = ImageDraw.Draw(card)
    
    label_font = _load_font(BACK_LABEL_FONT_SIZE, bold=False)
    value_font = _load_font(BACK_VALUE_FONT_SIZE, bold=True)

    draw.text(BACK_ID_LABEL_XY, "ID NUMBER", fill=(*BACK_LABEL_COLOR, 255), font=label_font)
    draw.text(BACK_ID_VALUE_XY, card_id, fill=(*BACK_VALUE_COLOR, 255), font=value_font)
    draw.text(BACK_DATE_LABEL_XY, "ISSUE DATE", fill=(*BACK_LABEL_COLOR, 255), font=label_font)
    draw.text(BACK_DATE_VALUE_XY, issue_date.strftime("%d %B %Y"), fill=(*BACK_VALUE_COLOR, 255), font=value_font)

    # Resize back card to match front card dimensions (359x568)
    card = card.resize((CARD_W, CARD_H), Image.LANCZOS)

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()



# Human-readable role labels for the card
ROLE_LABEL: dict[UserRole, str] = {
    UserRole.admin:       "Admin",
    UserRole.intern:      "Intern",
    UserRole.leader:      "Leader",
    UserRole.applicant:   "Applicant",
    UserRole.instructor:  "Instructor",
    UserRole.facilitator: "Facilitator",
    UserRole.ambassador:  "Ambassador",
    UserRole.teacher:     "Teacher",
}

# ── Font embedding ─────────────────────────────────────────────────────────────

def _font_style_block() -> str:
    """Return a <style> block that embeds Russo One as a base64 @font-face."""
    with open(_RUSSO_ONE, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    return (
        "<style>\n"
        "@font-face {\n"
        "  font-family: 'Russo One';\n"
        f"  src: url('data:font/truetype;base64,{b64}') format('truetype');\n"
        "}\n"
        "</style>"
    )


# ── SVG loading & patching ────────────────────────────────────────────────────

def _load_svg_template(role: UserRole) -> str:
    """
    Load the SVG template for this role.
    Falls back to the default frame.svg if no role-specific file exists.
    """
    role_svg = os.path.join(_TEMPLATES_DIR, f"{role.value}_front.svg")
    path = role_svg if os.path.exists(role_svg) else _DEFAULT_SVG
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _prepare_svg(role: UserRole) -> str:
    """Remove default text elements from the SVG so we can draw them in PIL. Returns modified SVG string."""
    svg = _load_svg_template(role)

    # Strip out the <text> elements entirely
    svg = re.sub(r"<text.*?</text>", "", svg, flags=re.DOTALL)

    return svg


# ── PIL helpers ───────────────────────────────────────────────────────────────

def _circle_crop(img: Image.Image, diameter: int) -> Image.Image:
    img = img.convert("RGBA").resize((diameter, diameter), Image.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    result = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    result.paste(img, (0, 0))
    result.putalpha(mask)
    return result


def _generate_qr(data: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)
    return img.convert("RGBA").resize((size, size), Image.LANCZOS)


# ── Main render function ───────────────────────────────────────────────────────

def render_card_png(
    role: UserRole,
    photo_bytes: bytes | None,
    linkedin_url: str | None,
    full_name: str,
) -> bytes:
    """
    Render a complete ID card PNG using the SVG template and PIL.

    Steps:
      1. Prepare SVG (strip default text) → cairosvg → base PIL image
      2. Draw role label on the purple bar via PIL
      3. Draw user name via PIL
      4. Overlay circular profile photo (if provided)
      5. Overlay QR code for LinkedIn URL (if provided)

    Returns raw PNG bytes.
    """
    # Step 1 — SVG → PNG via cairosvg
    svg_str = _prepare_svg(role)
    png_bytes = cairosvg.svg2png(
        bytestring=svg_str.encode("utf-8"),
        output_width=CARD_W,
        output_height=CARD_H,
    )
    card = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Step 2 — Draw role label centered on the bottom purple bar
    label = ROLE_LABEL.get(role, role.value.capitalize()).upper()  # Uppercase like original
    role_font = _load_font(ROLE_FONT_SIZE, bold=True)
    draw.text(
        (CARD_W // 2, ROLE_BAR_Y),
        label,
        fill=(255, 255, 255),
        font=role_font,
        anchor="mm",
    )

    # Step 3 — Draw user full name
    name_font = _load_font(NAME_FONT_SIZE, bold=True)
    draw.text(
        (NAME_CX, NAME_Y),
        full_name,
        fill=(255, 255, 255),
        font=name_font,
        anchor="mm",
    )

    # Step 4 — profile photo
    if photo_bytes:
        try:
            photo = Image.open(io.BytesIO(photo_bytes))
            circle = _circle_crop(photo, PHOTO_DIAMETER)
            x = PHOTO_CX - PHOTO_DIAMETER // 2
            y = PHOTO_CY - PHOTO_DIAMETER // 2
            overlay.paste(circle, (x, y), circle)
        except Exception:
            pass  # silently skip bad photo bytes

    # Step 5 — LinkedIn QR code
    if linkedin_url:
        try:
            qr_img = _generate_qr(linkedin_url, QR_SIZE)
            # White backing square for contrast
            qr_bg = Image.new("RGBA", (QR_SIZE + 12, QR_SIZE + 12), (255, 255, 255, 250))
            overlay.paste(qr_bg, (QR_X - 6, QR_Y - 6), qr_bg)
            overlay.paste(qr_img, (QR_X, QR_Y), qr_img)
        except Exception:
            pass

    result = Image.alpha_composite(card, overlay).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── DB helper: ensure stable card_id ─────────────────────────────────────────

async def _ensure_person_number(db: AsyncSession, user: User) -> int:
    """Allocate (once) or return the shared per-person card number.

    One number per person, reused by every role's card — not a per-role
    sequence. Allocated lazily on first-ever card generation for that person.
    """
    if user.card_number is not None:
        return user.card_number

    from sqlalchemy import text
    number = (await db.execute(text("SELECT nextval('card_seq_person')"))).scalar_one()
    user.card_number = number
    return number


async def ensure_card_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    role: UserRole,
) -> IdCard:
    """
    Return (or create) the IdCard row for this user+role.
    The row carries only the stable card_id; URL columns are kept null
    because images are generated on-the-fly. `card_id` is derived from the
    user's shared card_number — identical across every role this person holds.
    """
    existing = (
        await db.execute(
            select(IdCard).where(IdCard.user_id == user_id, IdCard.role == role)
        )
    ).scalars().first()

    user = await db.get(User, user_id)
    number = await _ensure_person_number(db, user)
    card_id = f"SP-{number:04d}-UAE"

    if existing:
        existing.card_id = card_id
        existing.generated_at = datetime.now(timezone.utc)
        return existing

    card = IdCard(
        user_id=user_id,
        role=role,
        card_id=card_id,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(card)
    return card
