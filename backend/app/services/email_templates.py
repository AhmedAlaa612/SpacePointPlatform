"""Email Templates System — one rendering path for every system email
(PLAN: Email Templates System).

`render_and_send` is the funnel every template-backed send goes through:
look up the `EmailTemplate` row by key, skip the send if it's paused, fill
`{token}` placeholders into the (admin-editable) subject/body, then hand off
to `services/email.py::try_send_email` — the low-level SMTP layer, which
stays untouched. If a key has no DB row yet (e.g. a migration hasn't run in
this environment), falls back to the bundled default in
`db/email_template_defaults.py` rather than sending nothing.

The 19 templates whose call sites always lived in `services/email.py` get
their public wrapper functions here too — same names and (almost) the same
arguments as before, with `db` added as the first parameter so the wrapper
can look up its own template row. `account_welcome_set_password` /
`account_password_reset` (services/lms/ops_integration.py),
`ticket_confirmation` (services/sessions/registration.py),
`kits_uncounted_reminder` / `overdue_item_reminder`
(workers/tasks/inventory.py), and `competition_team_advanced`
(services/competitions/progression.py) call `render_and_send` directly from
their own module instead — moving them here would just be a longer import
for no benefit, since each already owns exactly one call site.
"""

import logging
import re
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.email_template_defaults import EMAIL_TEMPLATE_DEFAULTS, STRUCTURAL_TOKENS
from app.models.email_template import EmailTemplate
from app.services.email import try_send_email

logger = logging.getLogger("email_templates")

_DEFAULTS_BY_KEY = {t["key"]: t for t in EMAIL_TEMPLATE_DEFAULTS}

# Sentinel for render_and_send's `template` param — None is itself a
# meaningful value there (no DB row, fall back to the bundled default), so
# "not supplied" needs a value None can't be confused with.
_NOT_FETCHED: Any = object()


async def fetch_template(db: AsyncSession, key: str) -> EmailTemplate | None:
    """The `EmailTemplate` lookup `render_and_send` does on every call,
    pulled out so a batch sender (same key, many recipients — a reminder
    cron, a cohort-wide certificate pass) can fetch it once and pass the
    row into each `render_and_send(..., template=row)` call instead of
    re-querying per recipient.

    Isolated in its own try/except so a lookup failure can't poison the
    caller's transaction: Postgres aborts a transaction after a failed
    statement, and most callers go on to `db.commit()` other work right
    after sending the email, so the rollback here is scoped to just this
    SELECT rather than discarding whatever the caller already wrote."""
    try:
        return (await db.execute(select(EmailTemplate).where(EmailTemplate.key == key))).scalars().first()
    except SQLAlchemyError:
        logger.exception("email_templates: template lookup failed for %r", key)
        await db.rollback()
        return None


def fill_placeholders(text: str, values: dict[str, str], raw_keys: set[str] = frozenset()) -> str:
    """Same `{token}` substitution as `routers/documents.py::_fill_placeholders`
    (kept as a separate copy rather than a shared import — the two have
    diverged just enough, with document templates escaping `{name}` etc. but
    exempting only `{signature}`, that a shared helper would need the same
    per-key raw-token concept added there anyway). An unknown token renders
    as `[TOKEN]` rather than being silently dropped."""

    def repl(match: "re.Match[str]") -> str:
        token = match.group(1)
        if token not in values:
            return f"[{token.upper()}]"
        value = values[token]
        return value if token in raw_keys else escape(value)

    return re.sub(r"\{(\w+)\}", repl, text)


async def render_and_send(
    db: AsyncSession,
    *,
    key: str,
    to: str,
    placeholders: dict[str, str],
    attachments: list[tuple[str, bytes, str]] | None = None,
    inline_images: dict[str, tuple[bytes, str, str]] | None = None,
    template: EmailTemplate | None = _NOT_FETCHED,
) -> bool:
    """Best-effort, never raises — matches `try_send_email`'s contract.
    Returns False (logged) if the template is paused, if `key` is unknown
    entirely (a coding error, not a runtime one — every real key is seeded),
    or if the underlying SMTP send fails.

    Pass `template=` (a row from `fetch_template`, possibly None) to skip
    this function's own lookup — for a batch sender that already fetched it
    once outside a per-recipient loop."""
    row = await fetch_template(db, key) if template is _NOT_FETCHED else template
    default = _DEFAULTS_BY_KEY.get(key)
    if row is None and default is None:
        logger.error("email_templates: unknown key %r — nothing to send to %s", key, to)
        return False

    if row is not None and row.is_paused:
        logger.info("email_templates: %s is paused — skipping send to %s", key, to)
        return False

    subject_tpl = row.subject if row is not None else default["subject"]
    body_tpl = row.body_html if row is not None else default["body_html"]
    raw_keys = STRUCTURAL_TOKENS.get(key, frozenset())

    subject = fill_placeholders(subject_tpl, placeholders, raw_keys)
    body = fill_placeholders(body_tpl, placeholders, raw_keys)

    return await try_send_email(to, subject, body, html=True, attachments=attachments, inline_images=inline_images)


# ── Applications & Instructors ──────────────────────────────────────────

async def send_phase1_approval_email(db: AsyncSession, to_email: str, name: str) -> bool:
    return await render_and_send(
        db, key="phase1_approval", to=to_email,
        placeholders={"name": name, "status_link": f"{settings.FRONTEND_URL}/instructors/status"},
    )


async def send_moved_to_onboarding_email(db: AsyncSession, to_email: str, name: str) -> bool:
    return await render_and_send(
        db, key="moved_to_onboarding", to=to_email,
        placeholders={"name": name, "login_link": f"{settings.FRONTEND_URL}/login"},
    )


_APPLICATION_ROLE_LABELS = {
    "ambassador": "Ambassador",
    "intern": "Intern",
    "teacher": "Teacher",
    "facilitator": "Facilitator",
}


async def send_application_approved_email(db: AsyncSession, to_email: str, name: str, role: str) -> bool:
    label = _APPLICATION_ROLE_LABELS.get(role, role.title())
    return await render_and_send(
        db, key="application_approved", to=to_email,
        placeholders={"name": name, "role": label, "login_link": f"{settings.FRONTEND_URL}/login"},
    )


async def send_approval_credentials_email(
    db: AsyncSession, to_email: str, name: str, temp_password: str | None = None, contract_pdf: bytes | None = None
) -> bool:
    if temp_password:
        login_info = (
            f"Email: {escape(to_email)}<br>Temporary password: {escape(temp_password)}"
            "<br><br>You'll be asked to set a new password on first login."
        )
    else:
        login_info = f"Email: {escape(to_email)}<br>Use your existing password to log in."
    attachments = [("SpacePoint_Instructor_Agreement.pdf", contract_pdf, "pdf")] if contract_pdf else None
    return await render_and_send(
        db, key="approval_credentials", to=to_email,
        placeholders={"name": name, "login_info": login_info, "login_link": f"{settings.FRONTEND_URL}/login"},
        attachments=attachments,
    )


async def send_instructor_welcome_email(db: AsyncSession, to_email: str, name: str, set_password_link: str) -> bool:
    return await render_and_send(
        db, key="instructor_welcome", to=to_email,
        placeholders={"name": name, "set_password_link": set_password_link},
    )


async def send_intern_welcome_email(db: AsyncSession, to_email: str, name: str, set_password_link: str) -> bool:
    return await render_and_send(
        db, key="intern_welcome", to=to_email,
        placeholders={"name": name, "set_password_link": set_password_link},
    )


async def send_contract_signed_notification_email(db: AsyncSession, admin_email: str, instructor_name: str) -> bool:
    return await render_and_send(
        db, key="contract_signed_notify_admin", to=admin_email,
        placeholders={"instructor_name": instructor_name},
    )


async def send_signed_contract_email(db: AsyncSession, to_email: str, name: str, signed_pdf: bytes) -> bool:
    return await render_and_send(
        db, key="contract_signed", to=to_email,
        placeholders={"name": name},
        attachments=[("SpacePoint_Instructor_Agreement_Signed.pdf", signed_pdf, "pdf")],
    )


async def send_certificates_email(db: AsyncSession, to_email: str, name: str, pdfs: list[tuple[str, bytes]]) -> bool:
    return await render_and_send(
        db, key="certificates_ready", to=to_email,
        placeholders={"name": name},
        attachments=[(fname, data, "pdf") for fname, data in pdfs],
    )


async def send_workshop_certificate_ready_email(
    db: AsyncSession, to_email: str, instructor_name: str, workshop_name: str, cert_pdf: bytes
) -> bool:
    return await render_and_send(
        db, key="workshop_certificate_ready", to=to_email,
        placeholders={"name": instructor_name, "workshop_name": workshop_name},
        attachments=[("SpacePoint_Certificate.pdf", cert_pdf, "pdf")],
    )


# ── Internship ───────────────────────────────────────────────────────────

async def send_internship_letter_ready_email(db: AsyncSession, to_email: str, intern_name: str) -> bool:
    return await render_and_send(
        db, key="internship_letter_ready", to=to_email,
        placeholders={"name": intern_name, "documents_link": f"{settings.FRONTEND_URL}/documents"},
    )


async def send_signed_internship_letter_email(db: AsyncSession, to_email: str, intern_name: str, signed_pdf: bytes) -> bool:
    return await render_and_send(
        db, key="internship_letter_signed", to=to_email,
        placeholders={"name": intern_name},
        attachments=[("SpacePoint_Internship_Letter.pdf", signed_pdf, "pdf")],
    )


async def send_internship_letter_signed_notification_email(db: AsyncSession, admin_email: str, intern_name: str) -> bool:
    return await render_and_send(
        db, key="internship_signed_notify_admin", to=admin_email,
        placeholders={"intern_name": intern_name},
    )


# ── Payments ─────────────────────────────────────────────────────────────

async def send_payment_letter_ready_email(db: AsyncSession, to_email: str, instructor_name: str) -> bool:
    return await render_and_send(
        db, key="payment_letter_ready", to=to_email,
        placeholders={"name": instructor_name, "payments_link": f"{settings.FRONTEND_URL}/instructors/payments"},
    )


async def send_payment_signed_notification_email(db: AsyncSession, admin_email: str, instructor_name: str) -> bool:
    return await render_and_send(
        db, key="payment_signed_notify_admin", to=admin_email,
        placeholders={"instructor_name": instructor_name},
    )


# ── Documents ────────────────────────────────────────────────────────────

async def send_recommendation_letter_email(db: AsyncSession, to_email: str, name: str) -> bool:
    return await render_and_send(db, key="recommendation_letter_ready", to=to_email, placeholders={"name": name})


# ── Sessions & Staffing ──────────────────────────────────────────────────

def _where_suffix(location: str | None, location_address: str | None, location_maps_url: str | None) -> str:
    where = f" at {location}" if location else ""
    if location_address:
        where += f" ({location_address})"
    if location_maps_url:
        where += f" — map: {location_maps_url}"
    return where


async def send_session_assignment_email(
    db: AsyncSession, to_email: str, name: str, program_name: str, meeting_date: str,
    location: str | None, location_address: str | None = None, location_maps_url: str | None = None,
) -> bool:
    return await render_and_send(
        db, key="session_assignment", to=to_email,
        placeholders={
            "name": name, "program_name": program_name, "meeting_date": meeting_date,
            "where": _where_suffix(location, location_address, location_maps_url),
            "my_sessions_link": f"{settings.FRONTEND_URL}/instructors/my-sessions",
        },
    )


async def send_call_invite_email(
    db: AsyncSession, to_email: str, name: str, program_name: str, meeting_date: str,
    location: str | None = None, location_address: str | None = None, location_maps_url: str | None = None,
) -> bool:
    return await render_and_send(
        db, key="call_invite", to=to_email,
        placeholders={
            "name": name, "program_name": program_name, "meeting_date": meeting_date,
            "where": _where_suffix(location, location_address, location_maps_url),
            "available_sessions_link": f"{settings.FRONTEND_URL}/instructors/available-sessions",
        },
    )


async def send_cohort_interest_notification_email(db: AsyncSession, to_email: str, name: str, program_name: str) -> bool:
    return await render_and_send(
        db, key="cohort_interest_open", to=to_email,
        placeholders={
            "name": name, "program_name": program_name,
            "catalog_link": f"{settings.FRONTEND_URL}/learn/catalog?tab=programs",
        },
    )
