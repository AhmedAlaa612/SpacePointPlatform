"""Transactional email over async SMTP (PLAN §8.3).

Uses aiosmtplib (not smtplib) so sending never blocks the event loop. Credentials
come from env (`SMTP_*`), never hardcoded.

Low-level transport only — `send_email` / `try_send_email`. Every actual system
email (subject/body, which template, whether it's paused) lives in
`services/email_templates.py` (Email Templates System) and the handful of
modules that call `render_and_send` directly for their own single trigger.
"""

import logging
from email.message import EmailMessage
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger("email")


async def send_email(
    to: str,
    subject: str,
    body: str,
    html: bool = False,
    attachments: list[tuple[str, bytes, str]] | None = None,
    inline_images: dict[str, tuple[bytes, str, str]] | None = None,
) -> None:
    """`attachments` is a list of (filename, data, mime_subtype) e.g.
    ("contract.pdf", pdf_bytes, "pdf").

    `inline_images` is a dict mapping Content-ID -> (data, maintype, subtype)
    used for CID-embedded images in HTML email, e.g.
    {"ticket": (png_bytes, "image", "png")}.
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be set")

    message = _build_message(to, subject, body, html, attachments, inline_images)

    message["From"] = settings.SMTP_FROM or settings.SMTP_USER
    message["To"] = to
    message["Subject"] = subject

    use_tls = settings.SMTP_PORT == 465
    start_tls = settings.SMTP_PORT == 587 or (not use_tls and settings.SMTP_PORT != 25)

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=use_tls,
        start_tls=start_tls,
    )


def _build_message(
    to: str,
    subject: str,
    body: str,
    html: bool,
    attachments: list[tuple[str, bytes, str]] | None,
    inline_images: dict[str, tuple[bytes, str, str]] | None,
) -> EmailMessage:
    """Construct the appropriate MIME tree depending on whether inline images
    and/or regular attachments are present."""
    subtype = "html" if html else "plain"

    if inline_images:
        # multipart/related so CID references in the HTML resolve
        related = MIMEMultipart("related")
        html_part = MIMEText(body, subtype)
        related.attach(html_part)

        for cid, (data, maintype, mime_subtype) in inline_images.items():
            if maintype == "image" and mime_subtype == "png":
                img = MIMEImage(data, _subtype="png")
            elif maintype == "image" and mime_subtype == "jpeg":
                img = MIMEImage(data, _subtype="jpeg")
            else:
                continue
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline")
            related.attach(img)

        if attachments:
            mixed = MIMEMultipart("mixed")
            mixed.attach(related)
            for filename, data, mime_subtype in attachments:
                if mime_subtype in ("png", "jpeg"):
                    att = MIMEImage(data, _subtype=mime_subtype)
                elif mime_subtype == "pdf":
                    att = MIMEApplication(data, _subtype="pdf")
                else:
                    att = MIMEApplication(data, _subtype=mime_subtype)
                att.add_header("Content-Disposition", "attachment", filename=filename)
                mixed.attach(att)
            return mixed

        return related

    # No inline images — plain or HTML with optional attachments
    message = EmailMessage()
    message.set_content(body, subtype=subtype)
    for filename, data, mime_subtype in attachments or []:
        message.add_attachment(data, maintype="application", subtype=mime_subtype, filename=filename)
    return message


async def try_send_email(to: str, subject: str, body: str, **kwargs) -> bool:
    """Best-effort send — state transitions (approvals, etc.) must not fail
    just because SMTP is unreachable/unconfigured. Mirrors the source app's
    "Approved, but credentials email failed to send..." degrade-gracefully
    behavior."""
    try:
        await send_email(to, subject, body, **kwargs)
        return True
    except Exception:
        logger.exception("Email send failed (to=%s, subject=%s)", to, subject)
        return False

