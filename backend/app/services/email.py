"""Transactional email over async SMTP (PLAN §8.3).

Uses aiosmtplib (not smtplib) so sending never blocks the event loop. Full set of
email types is wired in Phase 3 (instructors domain). Credentials come from env
(`SMTP_*`), never hardcoded.
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


async def send_moved_to_onboarding_email(to_email: str, name: str) -> bool:
    body = (
        f"Hi {name},\n\n"
        "Thanks for applying for the SpacePoint internship program.\n\n"
        "Your application passed the initial screening and has been moved to the "
        "onboarding phase.\n\n"
        f"Log in to your account and complete it within 10 days: {settings.FRONTEND_URL}/login\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, "SpacePoint Internship Application - Onboarding", body)


_APPLICATION_ROLE_LABELS = {
    "ambassador": "Ambassador",
    "intern": "Intern",
    "teacher": "Teacher",
    "facilitator": "Facilitator",
}


async def send_application_approved_email(to_email: str, name: str, role: str) -> bool:
    label = _APPLICATION_ROLE_LABELS.get(role, role.title())
    body = (
        f"Hi {name},\n\n"
        f"Congratulations — your {label} application has been approved! Welcome to SpacePoint.\n\n"
        f"Log in with the email and password you used to apply: {settings.FRONTEND_URL}/login\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, f"SpacePoint {label} Application Approved", body)


async def send_approval_credentials_email(
    to_email: str, name: str, temp_password: str | None = None, contract_pdf: bytes | None = None
) -> bool:
    if temp_password:
        login_info = f"Email: {to_email}\nTemporary password: {temp_password}\n\nYou'll be asked to set a new password on first login."
    else:
        login_info = f"Email: {to_email}\nUse your existing password to log in."

    body = (
        f"Hi {name},\n\n"
        "Congratulations — your instructor application has been approved!\n\n"
        f"{login_info}\n\n"
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


async def send_workshop_certificate_ready_email(
    to_email: str, instructor_name: str, workshop_name: str, cert_pdf: bytes
) -> bool:
    body = (
        f"Hi {instructor_name},\n\n"
        f"Your certificate of achievement for \"{workshop_name}\" is ready — see the attached PDF.\n\n"
        "— SpacePoint"
    )
    attachments = [("SpacePoint_Certificate.pdf", cert_pdf, "pdf")]
    return await try_send_email(to_email, "Your SpacePoint Certificate of Achievement", body, attachments=attachments)


async def send_contract_signed_notification_email(admin_email: str, instructor_name: str) -> bool:
    body = f"{instructor_name} has signed their instructor contract. Review it in the admin Instructors directory.\n\n— SpacePoint"
    return await try_send_email(admin_email, "Instructor Contract Signed", body)


async def send_signed_contract_email(to_email: str, name: str, signed_pdf: bytes) -> bool:
    body = f"Hi {name},\n\nAttached is your fully signed SpacePoint Instructor Agreement.\n\n— SpacePoint"
    attachments = [("SpacePoint_Instructor_Agreement_Signed.pdf", signed_pdf, "pdf")]
    return await try_send_email(to_email, "Your Signed SpacePoint Instructor Agreement", body, attachments=attachments)


async def send_session_assignment_email(
    to_email: str, name: str, program_name: str, meeting_date: str, location: str | None,
) -> bool:
    """V2 W4 S4-2 — sent when ops selects an instructor for a session
    (whether through the marketplace or a direct assign). Transactional,
    not a marketing send, so it never goes through a consent gate."""
    where = f" at {location}" if location else ""
    body = (
        f"Hi {name},\n\n"
        f"You've been assigned to a session of \"{program_name}\" on {meeting_date}{where}.\n\n"
        f"See it on your calendar: {settings.FRONTEND_URL}/instructors/my-sessions\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, f"You're assigned: {program_name}", body)


async def send_call_invite_email(
    to_email: str, name: str, program_name: str, meeting_date: str,
) -> bool:
    """Sent when ops targets an instructor on a staffing call (open_call /
    open_cohort_call with target_user_ids) — being targeted only showed up
    in the "Available sessions" list before this; targeted instructors had
    no way to know unless they happened to check."""
    body = (
        f"Hi {name},\n\n"
        f"You're invited to take part in \"{program_name}\" on {meeting_date}.\n\n"
        f"Visit the portal to register your interest: {settings.FRONTEND_URL}/instructors/available-sessions\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, f"You're invited: {program_name}", body)


async def send_cohort_interest_notification_email(to_email: str, name: str, program_name: str) -> bool:
    """Sent to everyone in `cohort_interest` for a cohort the moment ops
    flips its status from `planned` to `registration_open` (2026-08-07) —
    the "we said we'd tell you" half of the Notify-me / Register-now pair."""
    body = (
        f"Hi {name},\n\n"
        f"Registration is now open for \"{program_name}\" — you asked to be notified when it did.\n\n"
        f"Register here: {settings.FRONTEND_URL}/learn/catalog?tab=programs\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, f"Registration is open: {program_name}", body)


async def send_recommendation_letter_email(to_email: str, name: str) -> bool:
    body = (
        f"Hi {name},\n\n"
        "A recommendation letter has been generated for you — you can view and download it "
        "from your profile.\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, "Your SpacePoint Recommendation Letter", body)
