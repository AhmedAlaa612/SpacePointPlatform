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


async def send_instructor_welcome_email(to_email: str, name: str, set_password_link: str) -> bool:
    """Bulk-instructor-import welcome email (2026-08-17) — the account was
    created directly by an admin, not through public signup, so there's no
    password for `send_approval_credentials_email`'s "use your existing
    password" branch to point at. Uses the same stateless set-password-link
    mechanism as `ops_integration.send_set_password_email` (24h token)
    rather than emailing a temp password in plaintext."""
    body = (
        f"Hi {name},\n\n"
        "An instructor account has been created for you on the SpacePoint portal.\n\n"
        f"Set your password here: {set_password_link}\n"
        "(This link is valid for 24 hours.)\n\n"
        "Once you're in, please go to your Profile and fill in your city and the "
        "cities you're able to deliver workshops in.\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, "Welcome to SpacePoint — set your password", body)


async def send_intern_welcome_email(to_email: str, name: str, set_password_link: str) -> bool:
    """Bulk-intern-import welcome email (2026-08-20) — same shape as
    send_instructor_welcome_email (admin-created account, no password to
    point at, stateless set-password link), but a 3-day validity — the
    operator's call, longer than the instructor script's 24h since interns
    are often less immediately reachable than a newly-onboarded instructor."""
    body = (
        f"Hi {name},\n\n"
        "An intern account has been created for you on the SpacePoint portal.\n\n"
        f"Set your password here: {set_password_link}\n"
        "(This link is valid for 3 days.)\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, "Welcome to SpacePoint — set your password", body)


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


async def send_internship_letter_ready_email(to_email: str, intern_name: str) -> bool:
    """Sent when admin approves an internship request (public application or
    the authenticated self-apply flow) — same shape as
    send_payment_letter_ready_email, pointing at the shared My Documents page
    (services/internship/approval.py::approve_internship)."""
    body = (
        f"Hi {intern_name},\n\n"
        "Your internship request has been approved! Your internship letter is ready "
        "for your signature.\n\n"
        f"View and sign it here: {settings.FRONTEND_URL}/documents\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, "SpacePoint Internship Letter Ready for Signature", body)


async def send_signed_internship_letter_email(to_email: str, intern_name: str, signed_pdf: bytes) -> bool:
    """Sent once the intern signs in-app — welcome-aboard message + the
    signed copy attached, same attachment shape as send_signed_contract_email."""
    body = (
        f"Hi {intern_name},\n\n"
        "Welcome aboard! Your internship letter has been signed by both parties — "
        "the signed copy is attached for your records.\n\n"
        "— SpacePoint"
    )
    attachments = [("SpacePoint_Internship_Letter.pdf", signed_pdf, "pdf")]
    return await try_send_email(to_email, "Welcome to SpacePoint — Signed Internship Letter", body, attachments=attachments)


async def send_internship_letter_signed_notification_email(admin_email: str, intern_name: str) -> bool:
    body = f"{intern_name} has signed their internship letter. Review it in the admin panel.\n\n— SpacePoint"
    return await try_send_email(admin_email, "Internship Letter Signed", body)


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


async def send_course_review_submission_email(
    admin_email: str, author_name: str, course_title: str, course_id: str
) -> bool:
    body = (
        f"Hi,\n\n"
        f"{author_name} has submitted the course \"{course_title}\" for review and publishing.\n\n"
        f"Review it here: {settings.FRONTEND_URL}/lms-authoring/courses/{course_id}\n\n"
        f"— SpacePoint"
    )
    return await try_send_email(admin_email, f"LMS Course Review: {course_title}", body)


async def send_learning_path_review_submission_email(
    admin_email: str, author_name: str, path_title: str, path_id: str
) -> bool:
    body = (
        f"Hi,\n\n"
        f"{author_name} has submitted the learning path \"{path_title}\" for review and publishing.\n\n"
        f"Review it here: {settings.FRONTEND_URL}/lms-authoring/learning-paths/{path_id}\n\n"
        f"— SpacePoint"
    )
    return await try_send_email(admin_email, f"LMS Learning Path Review: {path_title}", body)



async def send_session_assignment_email(
    to_email: str, name: str, program_name: str, meeting_date: str,
    location: str | None, location_address: str | None = None, location_maps_url: str | None = None,
) -> bool:
    """V2 W4 S4-2 — sent when ops selects an instructor for a session
    (whether through the marketplace or a direct assign). Transactional,
    not a marketing send, so it never goes through a consent gate.
    The location is the fully-resolved one (name + address + maps link —
    see `resolve_session_location_display`)."""
    where = f" at {location}" if location else ""
    if location_address:
        where += f" ({location_address})"
    if location_maps_url:
        where += f" — map: {location_maps_url}"
    body = (
        f"Hi {name},\n\n"
        f"You've been assigned to a session of \"{program_name}\" on {meeting_date}{where}.\n\n"
        f"See it on your calendar: {settings.FRONTEND_URL}/instructors/my-sessions\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, f"You're assigned: {program_name}", body)


async def send_call_invite_email(
    to_email: str, name: str, program_name: str, meeting_date: str,
    location: str | None = None, location_address: str | None = None, location_maps_url: str | None = None,
) -> bool:
    """Sent when ops targets an instructor on a staffing call (open_call /
    open_cohort_call with target_user_ids) — being targeted only showed up
    in the "Available sessions" list before this; targeted instructors had
    no way to know unless they happened to check. The location is the
    fully-resolved one (name + address + maps link)."""
    where = f" at {location}" if location else ""
    if location_address:
        where += f" ({location_address})"
    if location_maps_url:
        where += f" — map: {location_maps_url}"
    body = (
        f"Hi {name},\n\n"
        f"You're invited to take part in \"{program_name}\" on {meeting_date}{where}.\n\n"
        f"Visit the portal to register your interest: {settings.FRONTEND_URL}/instructors/available-sessions\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, f"You're invited: {program_name}", body)


async def send_cohort_call_invite_email(
    to_email: str, name: str, program_name: str, cohort_name: str,
    starts_on: str | None = None, ends_on: str | None = None,
) -> bool:
    """Sent once per cohort call, once per recipient (2026-09-13) — the
    cohort-level counterpart to `send_call_invite_email` above. That one is
    session-shaped (one email per session a call opened); a cohort call can
    group many sessions, and firing one of those per session per recipient
    was the bug this exists to fix. Ops's `email_mode` choice (open_cohort_call)
    decides who gets this at all — same audience-vs-recipients split as the
    in-app notification, just opt-in rather than automatic."""
    when = ""
    if starts_on and ends_on:
        when = f" running from {starts_on} to {ends_on}"
    elif starts_on:
        when = f" starting {starts_on}"
    body = (
        f"Hi {name},\n\n"
        f"You're invited to register interest for \"{cohort_name}\" ({program_name}){when}.\n\n"
        f"Check the sessions and apply here: {settings.FRONTEND_URL}/instructors/available-sessions\n\n"
        "— SpacePoint"
    )
    return await try_send_email(to_email, f"You're invited: {program_name} cohort", body)


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


def _get_first_name(full_name: str) -> str:
    if not full_name:
        return "there"
    parts = full_name.strip().split()
    if not parts:
        return "there"
    first = parts[0]
    return first.capitalize() if first.islower() else first


def _condense_explanation(text: str, max_chars: int = 240) -> str:
    if not text:
        return "A breathtaking glimpse of the cosmos captured on your birth date."
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    shortened = cleaned[:max_chars].rsplit(" ", 1)[0]
    return shortened.rstrip(".,;:!?") + "..."


async def send_birthday_greeting_email(
    to_email: str,
    full_name: str,
    apod_data: dict,
) -> bool:
    """Sends a rich HTML birthday email featuring a NASA Astronomy Picture of the Day
    from a past year on this user's birthdate.
    """
    first_name = _get_first_name(full_name)
    title = apod_data.get("title") or "Cosmic Wonder"
    raw_explanation = apod_data.get("explanation") or "A breathtaking glimpse of our universe."
    concise_explanation = _condense_explanation(raw_explanation)
    image_url = apod_data.get("image_url") or "https://images-assets.nasa.gov/image/PIA25421/PIA25421~orig.jpg"
    year = apod_data.get("year", 2022)
    apod_url = apod_data.get("apod_url") or "https://apod.nasa.gov/apod/archivepix.html"

    subject = "SpacePoint - Your Birthday Cosmic View"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #0b0f19; padding: 40px 10px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 600px; background-color: #0c071e; border: 1px solid rgba(168, 85, 247, 0.25); border-radius: 20px; overflow: hidden; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.75);" cellspacing="0" cellpadding="0">
          <!-- Mission Orbit Purple Header -->
          <tr>
            <td style="padding: 34px 30px 24px; text-align: left; background: radial-gradient(circle at 85% 15%, rgba(139, 92, 246, 0.3) 0%, rgba(12, 7, 30, 1) 75%); border-bottom: 1px solid rgba(168, 85, 247, 0.25);">
              <div style="margin-bottom: 12px;">
                <span style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; font-weight: 700; letter-spacing: 2px; color: #a78bfa; text-transform: uppercase;">
                  [ TRANSMISSION // SP-ORBIT-LOG ]
                </span>
              </div>
              <h1 style="margin: 0 0 8px; font-size: 21px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px; line-height: 1.3;">
                Happy Orbit Completion, {first_name}! <span style="white-space: nowrap;">🎂🚀</span>
              </h1>
              <p style="margin: 0; font-size: 13.5px; color: #c4b5fd; line-height: 1.5;">
                SpacePoint Mission Control has logged another successful solar revolution around the Sun.
              </p>
            </td>
          </tr>

          <!-- Intro -->
          <tr>
            <td style="padding: 26px 30px 16px;">
              <p style="margin: 0; font-size: 14.5px; line-height: 1.6; color: #e2e8f0;">
                A view captured from space on your <span style="white-space: nowrap;">birthday in <strong style="color: #c084fc;">{year}</strong>:</span>
              </p>
            </td>
          </tr>

          <!-- NASA APOD Card -->
          <tr>
            <td style="padding: 0 30px 24px;">
              <div style="background-color: #070312; border: 1px solid rgba(168, 85, 247, 0.25); border-radius: 14px; overflow: hidden;">
                <img src="{image_url}" alt="{title}" style="width: 100%; max-height: 340px; object-fit: cover; display: block; border-bottom: 1px solid rgba(168, 85, 247, 0.15);" />
                <div style="padding: 18px 20px;">
                  <h3 style="margin: 0 0 8px; font-size: 17px; color: #ffffff; font-weight: 700;">{title}</h3>
                  <p style="margin: 0 0 14px; font-size: 13.5px; line-height: 1.6; color: #94a3b8;">{concise_explanation}</p>
                  <div style="font-size: 12px; border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 10px;">
                    <span style="color: #64748b;">Reference: </span>
                    <a href="{apod_url}" target="_blank" style="color: #c084fc; text-decoration: none; font-weight: 600;">
                      NASA Astronomy Picture of the Day Archive ↗
                    </a>
                  </div>
                </div>
              </div>
            </td>
          </tr>

          <!-- Closing & Sign-off -->
          <tr>
            <td style="padding: 0 30px 32px;">
              <p style="margin: 0 0 20px; font-size: 14px; line-height: 1.6; color: #cbd5e1;">
                Thank you for being an inspiring part of our SpacePoint community. May your upcoming year bring new heights, boundary-pushing discoveries, and stellar achievements!
              </p>
              <div style="font-size: 14px; line-height: 1.6; color: #cbd5e1;">
                Best regards,<br>
                <strong style="color: #ffffff;">— SpacePoint Team</strong>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    plain_body = (
        "SpacePoint - Your Birthday Cosmic View\n\n"
        "[ TRANSMISSION // SP-ORBIT-LOG ]\n"
        f"Happy Orbit Completion, {first_name}! 🎂🚀\n\n"
        "SpacePoint Mission Control has logged another successful solar revolution around the Sun.\n\n"
        f"A view captured from space on your birthday in {year}:\n\n"
        f"Title: {title}\n"
        f"Image: {image_url}\n\n"
        f"{concise_explanation}\n\n"
        f"Reference: {apod_url}\n\n"
        "Thank you for being an inspiring part of our SpacePoint community. May your upcoming year bring new heights, boundary-pushing discoveries, and stellar achievements!\n\n"
        "Best regards,\n"
        "— SpacePoint Team\n"
    )

    return await try_send_email(
        to=to_email,
        subject=subject,
        body=html_content,
        html=True,
    )
