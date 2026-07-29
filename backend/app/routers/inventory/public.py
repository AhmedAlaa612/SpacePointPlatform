"""Public kit scan (I2-6). No auth.

Whoever is holding the box can read the sticker, so the scan page tells them
nothing they can't already see — plus who to contact. It deliberately does
**not** expose where the kit lives, who holds it, or what is inside: a QR code
on a box that leaves the building is readable by anyone who picks it up.

`public_token` is random and unrelated to the label, for the same reason
ticket tokens are (see `services/documents/ticket.py`): a code on a physical
object must not be guessable from anything printed next to it.
"""

import io

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Response, status
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.inventory.kit import Kit
from app.models.inventory.kit_template import KitTemplate
from app.schemas.inventory.kits import PublicKitOut

router = APIRouter(prefix="/public", tags=["inventory-public"])


def _scan_url(token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/k/{token}"


@router.get("/kit/{token}", response_model=PublicKitOut)
async def public_kit(token: str, db: AsyncSession = Depends(get_db)):
    kit = (await db.execute(select(Kit).where(Kit.public_token == token))).scalars().first()
    if kit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown kit")

    template = await db.get(KitTemplate, kit.template_id)
    return PublicKitOut(
        label=kit.label,
        template_name=template.name if template else "",
        status=kit.status,
        owner="SpacePoint",
        contact_email=settings.ADMIN_EMAIL,
    )


@router.get("/kit/{token}/qr.png")
async def public_kit_qr(token: str, db: AsyncSession = Depends(get_db)):
    """Rendered on demand.

    The legacy system stored two PNG blobs per kit in BYTEA and had to
    regenerate them whenever the base URL changed. A QR code is a pure
    function of a string; caching it in the database is storing a derived
    value that can go stale.
    """
    exists = await db.scalar(select(Kit.id).where(Kit.public_token == token))
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown kit")

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(_scan_url(token))
    qr.make(fit=True)
    img = qr.make_image(image_factory=StyledPilImage, module_drawer=RoundedModuleDrawer())

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
