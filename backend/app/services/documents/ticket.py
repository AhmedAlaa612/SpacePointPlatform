"""Registration ticket QR generation (V2 R1-4).

The QR encodes the ticket URL (which embeds `ticket_token`) — never a name,
email, or phone, and never a short/guessable id. Two reasons, both discussed
explicitly while designing this: encoding PII means anyone who scans or even
photographs the ticket gets the student's personal data, and a guessable id
in the QR means entry can be forged by anyone who can generate a QR code.
`ticket_token` is a 64-char urlsafe-random string specifically so neither is
possible (see services/sessions/registration.py).
"""

import io
import os

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer

from app.core.config import settings

# Optional branding logo embedded in the QR's center. None of this repo's
# static assets are a usable square logo yet — this path simply won't exist
# until one is added, and generate_ticket_qr_png() degrades gracefully.
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "static", "branding", "qr_logo.png")


def ticket_url(ticket_token: str) -> str:
    """The public ticket page — same URL a staff scanner reads the token from."""
    return f"{settings.FRONTEND_URL}/t/{ticket_token}"


def generate_ticket_qr_png(ticket_token: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # highest — needed if a logo is embedded
        box_size=10,
        border=4,
    )
    qr.add_data(ticket_url(ticket_token))
    qr.make(fit=True)

    if os.path.exists(_LOGO_PATH):
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            embeded_image_path=_LOGO_PATH,
            embedded_image_ratio=0.25,
        )
    else:
        img = qr.make_image(image_factory=StyledPilImage, module_drawer=RoundedModuleDrawer())

    buf = io.BytesIO()
    img.save(buf, format="PNG") if hasattr(img, "save") else img.get_image().save(buf, format="PNG")
    return buf.getvalue()
