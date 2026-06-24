"""Transactional email over async SMTP (PLAN §8.3).

Uses aiosmtplib (not smtplib) so sending never blocks the event loop. Full set of
email types is wired in Phase 3 (instructors domain). Credentials come from env
(`SMTP_*`), never hardcoded.
"""

from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings


async def send_email(to: str, subject: str, body: str, html: bool = False) -> None:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be set")

    message = EmailMessage()
    message["From"] = settings.SMTP_USER
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body, subtype="html" if html else "plain")

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        start_tls=True,
    )
