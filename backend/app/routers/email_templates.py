"""Email Templates System (admin) — list/edit/pause/preview every system
email. Mirrors `routers/documents.py`'s admin template endpoints, but this
table is never a create/delete surface (see `models/email_template.py`).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.email_template import EmailTemplate
from app.models.user import User
from app.schemas.email_templates import (
    EmailTemplateOut,
    EmailTemplatePauseUpdate,
    EmailTemplatePreviewOut,
    EmailTemplatePreviewRequest,
    EmailTemplateSendTestOut,
    EmailTemplateUpdate,
)
from app.services.email import try_send_email
from app.services.email_templates import fill_placeholders
from app.db.email_template_defaults import STRUCTURAL_TOKENS

router = APIRouter(prefix="/email-templates", tags=["email-templates"])

logger = logging.getLogger("email_templates")


async def _get_or_404(db: AsyncSession, id: uuid.UUID) -> EmailTemplate:
    template = await db.get(EmailTemplate, id)
    if not template:
        raise HTTPException(status_code=404, detail="Email template not found")
    return template


@router.get("", response_model=list[EmailTemplateOut])
async def list_email_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    templates = (await db.execute(
        select(EmailTemplate).order_by(EmailTemplate.category, EmailTemplate.name)
    )).scalars().all()
    return templates


@router.get("/{id}", response_model=EmailTemplateOut)
async def get_email_template(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return await _get_or_404(db, id)


@router.put("/{id}", response_model=EmailTemplateOut)
async def update_email_template(
    id: uuid.UUID,
    body: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template = await _get_or_404(db, id)
    if body.subject is not None:
        template.subject = body.subject
    if body.body_html is not None:
        template.body_html = body.body_html
    await db.commit()
    await db.refresh(template)
    return template


@router.patch("/{id}/pause", response_model=EmailTemplateOut)
async def pause_email_template(
    id: uuid.UUID,
    body: EmailTemplatePauseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template = await _get_or_404(db, id)
    template.is_paused = body.is_paused
    await db.commit()
    await db.refresh(template)
    return template


# Sample values for the preview/send-test panel — keyed by placeholder token,
# with a couple of per-key overrides where the same token name means
# something different shape-wise between templates (see STRUCTURAL_TOKENS).
_GENERIC_SAMPLES: dict[str, str] = {
    "name": "Jane Doe",
    "role": "Instructor",
    "program_name": "Intro to Orbits",
    "meeting_date": "12 August 2026",
    "workshop_name": "CubeSat Basics",
    "team_name": "Team Nova",
    "to_cohort_name": "Finalists Cohort",
    "instructor_name": "Jane Doe",
    "intern_name": "Jane Doe",
    "student_name": "Jane Doe",
    "dates": "12 – 14 August 2026",
    "labels": "Kit A, Kit B",
    "what": "Kit A",
    "due_back_on": "20 August 2026",
    "kind": "course",
    "login_link": f"{settings.FRONTEND_URL}/login",
    "status_link": f"{settings.FRONTEND_URL}/instructors/status",
    "documents_link": f"{settings.FRONTEND_URL}/documents",
    "payments_link": f"{settings.FRONTEND_URL}/instructors/payments",
    "my_sessions_link": f"{settings.FRONTEND_URL}/instructors/my-sessions",
    "available_sessions_link": f"{settings.FRONTEND_URL}/instructors/available-sessions",
    "catalog_link": f"{settings.FRONTEND_URL}/learn/catalog?tab=programs",
    "set_password_link": f"{settings.FRONTEND_URL}/set-password?token=sample",
    "ticket_link": f"{settings.FRONTEND_URL}/t/sample-token",
}

_KEY_OVERRIDES: dict[tuple[str, str], str] = {
    ("ticket_confirmation", "where"): 'SpacePoint HQ<br>Al Quoz, Dubai<br><a href="#" style="color:#2563eb">Open in Google Maps</a>',
    ("ticket_confirmation", "ticket_qr"): (
        '<span style="display:inline-block;padding:32px 56px;background:#eee;'
        'border-radius:12px;color:#888;font-family:sans-serif;font-size:13px;">[QR CODE]</span>'
    ),
    ("session_assignment", "where"): " at Dubai (SpacePoint HQ) — map: https://maps.google.com/?q=SpacePoint+HQ",
    ("call_invite", "where"): " at Dubai (SpacePoint HQ) — map: https://maps.google.com/?q=SpacePoint+HQ",
    ("approval_credentials", "login_info"): "Email: jane.doe@example.com<br>Use your existing password to log in.",
}


def _sample_placeholders(template: EmailTemplate) -> dict[str, str]:
    return {
        token: _KEY_OVERRIDES.get((template.key, token), _GENERIC_SAMPLES.get(token, f"Sample {token}"))
        for token in (template.placeholders or [])
    }


def _render(template_key: str, subject: str, body_html: str, values: dict[str, str]) -> tuple[str, str]:
    raw_keys = STRUCTURAL_TOKENS.get(template_key, frozenset())
    return fill_placeholders(subject, values, raw_keys), fill_placeholders(body_html, values, raw_keys)


@router.post("/{id}/preview", response_model=EmailTemplatePreviewOut)
async def preview_email_template(
    id: uuid.UUID,
    body: EmailTemplatePreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Renders whatever subject/body the admin currently has in the editor
    (not necessarily saved yet) against sample values, so this is safe to
    call before hitting Save."""
    template = await _get_or_404(db, id)
    values = {**_sample_placeholders(template), **(body.values or {})}
    subject, rendered = _render(template.key, body.subject, body.body_html, values)
    return EmailTemplatePreviewOut(subject=subject, body_html=rendered)


@router.post("/{id}/send-test", response_model=EmailTemplateSendTestOut)
async def send_test_email_template(
    id: uuid.UUID,
    body: EmailTemplatePreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Sends the rendered preview to the current admin's own inbox — real
    confirmation it renders correctly in a client, not just in-browser.
    Bypasses `is_paused` on purpose: testing a paused template is exactly
    when you'd want to see what it looks like."""
    template = await _get_or_404(db, id)
    values = {**_sample_placeholders(template), **(body.values or {})}
    subject, rendered = _render(template.key, body.subject, body.body_html, values)
    sent = await try_send_email(current_user.email, f"[Test] {subject}", rendered, html=True)
    return EmailTemplateSendTestOut(sent=sent, to=current_user.email)
