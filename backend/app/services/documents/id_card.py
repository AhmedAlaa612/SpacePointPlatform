"""Shared ID card generator — ALL roles, same template engine (PLAN §4.5/§8.2).

Pulled forward from Phase 4 into Phase 3 because the instructor portal's
Profile Card page needs it now. Genuinely role-generic: `role` is a
parameter throughout, never hardcoded, so interns/ambassadors/etc. can call
this unchanged once their pages land. The one thing that ISN'T generic yet
is the template *artwork* — only an instructor-branded template exists
today (ported from the source app); `_template_paths()` already resolves
per-role (`static/templates/id_cards/{role}_front.png`) and falls back to
the instructor template only because no other role's artwork exists yet.
Drop in `{role}_front.png`/`{role}_back.png` and it just works, no code
change needed.
"""

import io
import os
from datetime import datetime, timezone
from uuid import UUID

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.pil import PilImage
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.enums import UserRole
from app.models.id_card import IdCard
from app.services import storage

_STATIC_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "static"))
_TEMPLATES_DIR = os.path.join(_STATIC_DIR, "templates", "id_cards")

# Card layout — same coordinates as the source app (newID_Front/Back.png,
# 638x1011 RGBA). If a future role's template uses different dimensions,
# these become per-template constants; not needed until that's true.
PHOTO_SIZE, PHOTO_CX, PHOTO_CY = 220, 319, 370
NAME_CX, NAME_Y, NAME_COLOR, NAME_FONT_SIZE = 319, 505, (255, 255, 255), 34
QR_SIZE, QR_X, QR_Y = 190, 319 - 95, 705
BACK_ID_LABEL_XY, BACK_ID_VALUE_XY = (60, 295), (60, 320)
BACK_DATE_LABEL_XY, BACK_DATE_VALUE_XY = (60, 400), (60, 425)
BACK_LABEL_COLOR, BACK_VALUE_COLOR = (160, 130, 200), (255, 255, 255)
BACK_LABEL_FONT_SIZE, BACK_VALUE_FONT_SIZE = 13, 26

ROLE_PREFIX = {
    UserRole.admin: "ADM", UserRole.intern: "INT", UserRole.leader: "LEA",
    UserRole.applicant: "APP", UserRole.instructor: "INS", UserRole.facilitator: "FAC",
    UserRole.ambassador: "AMB", UserRole.teacher: "TEA",
}


def _template_paths(role: str) -> tuple[str, str]:
    front = os.path.join(_TEMPLATES_DIR, f"{role}_front.png")
    back = os.path.join(_TEMPLATES_DIR, f"{role}_back.png")
    if os.path.exists(front) and os.path.exists(back):
        return front, back
    return (
        os.path.join(_TEMPLATES_DIR, "instructor_front.png"),
        os.path.join(_TEMPLATES_DIR, "instructor_back.png"),
    )


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """System fonts first (look native when present), then reportlab's
    bundled Vera font as a guaranteed-portable fallback — resolved via the
    installed package, not a hardcoded venv/python-version path (the source
    app's loader hardcoded `venv/lib/python3.12/...`, which breaks on any
    other Python version)."""
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
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _circle_crop(photo: Image.Image, diameter: int) -> Image.Image:
    photo = photo.convert("RGBA").resize((diameter, diameter), Image.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter, diameter), fill=255)
    result = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    result.paste(photo, (0, 0))
    result.putalpha(mask)
    return result


def _generate_qr(data: str, size: int) -> Image.Image:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)
    return img.convert("RGBA").resize((size, size), Image.LANCZOS)


def _render_front(template_path: str, photo_bytes: bytes, name: str, linkedin_url: str | None) -> Image.Image:
    card = Image.open(template_path).convert("RGBA")
    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    circle = _circle_crop(Image.open(io.BytesIO(photo_bytes)), PHOTO_SIZE)
    overlay.paste(circle, (PHOTO_CX - PHOTO_SIZE // 2, PHOTO_CY - PHOTO_SIZE // 2), circle)

    font = _load_font(NAME_FONT_SIZE, bold=True)
    bbox = draw.textbbox((0, 0), name, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text((NAME_CX - text_w // 2, NAME_Y), name, fill=(*NAME_COLOR, 255), font=font)

    if linkedin_url:
        qr_img = _generate_qr(linkedin_url, QR_SIZE)
        qr_bg = Image.new("RGBA", (QR_SIZE + 12, QR_SIZE + 12), (255, 255, 255, 250))
        overlay.paste(qr_bg, (QR_X - 6, QR_Y - 6), qr_bg)
        overlay.paste(qr_img, (QR_X, QR_Y), qr_img)

    return Image.alpha_composite(card, overlay).convert("RGB")


def _render_back(template_path: str, card_id: str, issue_date: datetime) -> Image.Image:
    card = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(card)
    label_font, value_font = _load_font(BACK_LABEL_FONT_SIZE), _load_font(BACK_VALUE_FONT_SIZE, bold=True)

    draw.text(BACK_ID_LABEL_XY, "ID NUMBER", fill=(*BACK_LABEL_COLOR, 255), font=label_font)
    draw.text(BACK_ID_VALUE_XY, card_id, fill=(*BACK_VALUE_COLOR, 255), font=value_font)
    draw.text(BACK_DATE_LABEL_XY, "ISSUE DATE", fill=(*BACK_LABEL_COLOR, 255), font=label_font)
    draw.text(BACK_DATE_VALUE_XY, issue_date.strftime("%d %B %Y"), fill=(*BACK_VALUE_COLOR, 255), font=value_font)

    return card.convert("RGB")


def _render_pdf(front: Image.Image, back: Image.Image) -> bytes:
    """Two-page CR80 (3.375in x 2.125in landscape) PDF for download/print."""
    buf = io.BytesIO()
    width, height = 3.375 * inch, 2.125 * inch
    c = canvas.Canvas(buf, pagesize=(width, height))
    for img in (front, back):
        img_buf = io.BytesIO()
        img.rotate(-90, expand=True).save(img_buf, format="PNG")
        img_buf.seek(0)
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(img_buf), 0, 0, width=width, height=height)
        c.showPage()
    c.save()
    return buf.getvalue()


async def generate_id_card(
    db: AsyncSession, user_id: UUID, role: UserRole, full_name: str,
    photo_bytes: bytes, linkedin_url: str | None,
) -> IdCard:
    front_template, back_template = _template_paths(role.value)

    existing = (await db.execute(
        select(IdCard).where(IdCard.user_id == user_id, IdCard.role == role)
    )).scalars().first()

    if existing and existing.card_id:
        card_id = existing.card_id
    else:
        count = (await db.execute(
            select(func.count()).select_from(IdCard).where(IdCard.role == role)
        )).scalar_one()
        card_id = f"SP-{ROLE_PREFIX[role]}-{count + 1:04d}"

    issue_date = datetime.now(timezone.utc)
    front_img = _render_front(front_template, photo_bytes, full_name, linkedin_url)
    back_img = _render_back(back_template, card_id, issue_date)
    pdf_bytes = _render_pdf(front_img, back_img)

    front_buf, back_buf = io.BytesIO(), io.BytesIO()
    front_img.save(front_buf, format="PNG")
    back_img.save(back_buf, format="PNG")

    base_path = f"{user_id}/{role.value}"
    front_url = await storage.upload_file("id-cards", f"{base_path}/front.png", front_buf.getvalue(), "image/png")
    back_url = await storage.upload_file("id-cards", f"{base_path}/back.png", back_buf.getvalue(), "image/png")
    pdf_url = await storage.upload_file("id-cards", f"{base_path}/card.pdf", pdf_bytes, "application/pdf")

    if existing:
        existing.card_id, existing.front_url, existing.back_url, existing.pdf_url = card_id, front_url, back_url, pdf_url
        existing.generated_at = issue_date
        card = existing
    else:
        card = IdCard(
            user_id=user_id, role=role, card_id=card_id,
            front_url=front_url, back_url=back_url, pdf_url=pdf_url, generated_at=issue_date,
        )
        db.add(card)

    return card
