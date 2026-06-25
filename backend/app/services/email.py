"""Transactional email over async SMTP (PLAN §8.3).

Uses aiosmtplib (not smtplib) so sending never blocks the event loop. Full set of
email types is wired in Phase 3 (instructors domain). Credentials come from env
(`SMTP_*`), never hardcoded.
"""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger("email")


async def send_email(
    to: str,
    subject: str,
    body: str,
    html: bool = False,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """`attachments` is a list of (filename, data, mime_subtype) e.g.
    ("contract.pdf", pdf_bytes, "pdf")."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be set")

    message = EmailMessage()
    message["From"] = settings.SMTP_USER
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body, subtype="html" if html else "plain")

    for filename, data, subtype in attachments or []:
        message.add_attachment(data, maintype="application", subtype=subtype, filename=filename)

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        start_tls=True,
    )


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


async def send_phase1_approval_email(to_email: str, name: str) -> bool:
    body = (
        f"Hi {name},\n\n"
        "Congratulations — your Phase 1 application has been approved!\n\n"
        "Next step: record and submit a 10-15 minute presentation (max 10 slides) "
        "covering CubeSat fundamentals, subsystems, onboard memory, and communications.\n\n"
        f"Submit it here: {settings.FRONTEND_URL}/instructors/status\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, "SpacePoint Instructor Application - Phase 1 Approved", body)


async def send_approval_credentials_email(
    to_email: str, name: str, temp_password: str, contract_pdf: bytes | None = None
) -> bool:
    body = (
        f"Hi {name},\n\n"
        "Congratulations — your instructor application has been approved!\n\n"
        f"Email: {to_email}\nTemporary password: {temp_password}\n\n"
        "You'll be asked to set a new password on first login.\n\n"
        f"Log in to the instructor portal: {settings.FRONTEND_URL}/login\n\n"
        "— SpacePoint"
    )
    attachments = [("SpacePoint_Instructor_Agreement.pdf", contract_pdf, "pdf")] if contract_pdf else None
    return await try_send_email(
        to_email, "SpacePoint Instructor Application Approved", body, attachments=attachments
    )


async def send_payment_letter_ready_email(to_email: str, instructor_name: str) -> bool:
    body = (
        f"Hi {instructor_name},\n\n"
        "A new payment letter is ready for your signature.\n\n"
        f"View and sign it here: {settings.FRONTEND_URL}/instructors/payments\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, "SpacePoint Payment Letter Ready for Signature", body)


async def send_payment_signed_notification_email(admin_email: str, instructor_name: str) -> bool:
    body = f"{instructor_name} has signed their payment letter. Review it in the admin Payments tab.\n\n— SpacePoint"
    return await try_send_email(admin_email, "Payment Letter Signed", body)


async def send_certificates_email(to_email: str, name: str, pdfs: list[tuple[str, bytes]]) -> bool:
    body = f"Hi {name},\n\nAttached are your certificate(s) for the workshop(s) you delivered.\n\n— SpacePoint"
    attachments = [(fname, data, "pdf") for fname, data in pdfs]
    return await try_send_email(to_email, "Your SpacePoint Certificate(s)", body, attachments=attachments)


async def send_recommendation_letter_email(to_email: str, name: str) -> bool:
    body = (
        f"Hi {name},\n\n"
        "A recommendation letter has been generated for you — you can view and download it "
        "from your profile.\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, "Your SpacePoint Recommendation Letter", body)
