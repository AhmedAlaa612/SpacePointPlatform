"""Global Certificate Email Templates CRUD & Test Email (2026-11)."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_lms_content, require_operations
from app.db.session import get_db
from app.models.sessions.certificate_email_template import CertificateEmailTemplate
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.schemas.sessions.program_certificate_template import (
    CertificateEmailTemplateCreate,
    CertificateEmailTemplateOut,
    CertificateEmailTemplateTestIn,
    CertificateEmailTemplateUpdate,
)
from app.services.competitions.certificates import (
    _resolve_certificate_template,
    render_certificate_email,
)
from app.services.documents.certificate import (
    STUDENT_COMPLETION_FALLBACK_BODY,
    expand_certificate_body_template,
    generate_completion_certificate_pdf,
)
from app.services.email import try_send_email
from app.services.sessions.registration import format_cohort_dates
from app.services.sessions.staffing import resolve_session_location_display

router = APIRouter(prefix="/sessions/certificate-email-templates", tags=["certificate-email-templates"])


@router.get("", response_model=list[CertificateEmailTemplateOut])
async def list_certificate_email_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lms_content),
):
    rows = (
        await db.execute(
            select(CertificateEmailTemplate).order_by(
                CertificateEmailTemplate.is_default.desc(),
                CertificateEmailTemplate.created_at.asc(),
            )
        )
    ).scalars().all()
    return rows


@router.post("", response_model=CertificateEmailTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_certificate_email_template(
    body: CertificateEmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    row = CertificateEmailTemplate(id=uuid.uuid4(), **body.model_dump())
    db.add(row)
    await db.flush()
    if row.is_default:
        others = (
            await db.execute(
                select(CertificateEmailTemplate).where(
                    CertificateEmailTemplate.kind == row.kind,
                    CertificateEmailTemplate.is_default.is_(True),
                    CertificateEmailTemplate.id != row.id,
                )
            )
        ).scalars().all()
        for o in others:
            o.is_default = False
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{template_id}", response_model=CertificateEmailTemplateOut)
async def update_certificate_email_template(
    template_id: uuid.UUID,
    body: CertificateEmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    row = await db.get(CertificateEmailTemplate, template_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Email template not found")

    changes = body.model_dump(exclude_unset=True)
    effective_kind = changes.get("kind") or row.kind
    if changes.get("is_default") is True:
        others = (
            await db.execute(
                select(CertificateEmailTemplate).where(
                    CertificateEmailTemplate.kind == effective_kind,
                    CertificateEmailTemplate.is_default.is_(True),
                    CertificateEmailTemplate.id != template_id,
                )
            )
        ).scalars().all()
        for o in others:
            o.is_default = False

    for k, v in changes.items():
        setattr(row, k, v)

    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certificate_email_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    row = await db.get(CertificateEmailTemplate, template_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Email template not found")
    await db.delete(row)
    await db.commit()


@router.post("/test-email")
async def send_test_from_email_template(
    body: CertificateEmailTemplateTestIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lms_content),
):
    """Send a test email using draft subject/body (or a saved template) with sample data."""
    prog_name = "Space Mission 101"
    cohort_name = "Cohort 1"
    dates = "12 – 16 October 2026"
    location_name = "SpacePoint HQ"
    program = None
    cohort = None

    if body.cohort_id:
        cohort = await db.get(Cohort, body.cohort_id)
        if cohort:
            program = await db.get(Program, cohort.program_id)
            prog_name = program.name if program else prog_name
            cohort_name = cohort.name or cohort_name
            dates = format_cohort_dates(cohort)
            loc = await resolve_session_location_display(db, None, cohort)
            location_name = loc.get("name") or location_name

    effective_name = (body.recipient_name or "").strip() or "Sample Student"
    profile_link = f"{settings.FRONTEND_URL.rstrip('/')}/learn/profile"
    cert_list = (
        "Student Certificate and Team Certificate"
        if body.kind == "combined"
        else ("Team Certificate" if body.kind == "team" else "Student Certificate")
    )

    subj, html_body = render_certificate_email(
        student_name=effective_name,
        program_name=prog_name,
        cohort_name=cohort_name,
        dates=dates,
        team_name="Sample Team",
        team_rank=1,
        certificate_type="team" if body.kind == "team" else "completion",
        custom_subject=body.subject,
        custom_body=body.body_html,
        certificate_list=cert_list,
        profile_link=profile_link,
    )

    attachments = []
    if body.kind != "profile":
        layout = (
            await _resolve_certificate_template(
                db,
                program=program,
                template_id=body.certificate_template_id,
                theme="dark",
                kind="team" if body.kind == "team" else "individual",
            )
            if program
            else {
                "background_bytes": None,
                "theme": "dark",
                "name_font_size": 34,
                "name_y": 298.0,
                "name_color": None,
                "body_font_size": 20,
                "body_y": 260.0,
                "body_color": None,
                "body_max_width": 600.0,
                "body_alignment": "center",
                "show_signature": False,
                "signature_bytes": None,
                "signature_x": None,
                "signature_y": 90.0,
                "signature_width": 140.0,
                "signature_height": 50.0,
                "signatory_name": settings.DEFAULT_SIGNATORY_NAME,
                "signatory_title": settings.DEFAULT_SIGNATORY_TITLE,
                "body_text_template": None,
            }
        )
        raw_body = layout.get("body_text_template") or STUDENT_COMPLETION_FALLBACK_BODY
        expanded = expand_certificate_body_template(
            raw_body,
            program_name=prog_name,
            cohort_name=cohort_name,
            dates=dates,
            starts_on=cohort.starts_on if cohort else None,
            ends_on=cohort.ends_on if cohort else None,
            location=location_name,
            team_name="Sample Team",
            rank=1,
        )
        pdf_bytes = await asyncio.to_thread(
            generate_completion_certificate_pdf,
            recipient_name=effective_name,
            body_text_template=expanded,
            background_bytes=layout["background_bytes"],
            theme=layout["theme"],
            name_font_size=layout["name_font_size"],
            name_y=layout["name_y"],
            name_color=layout["name_color"],
            body_font_size=layout["body_font_size"],
            body_y=layout["body_y"],
            body_color=layout["body_color"],
            body_max_width=layout["body_max_width"],
            body_alignment=layout["body_alignment"],
            show_signature=layout["show_signature"],
            signature_bytes=layout["signature_bytes"],
            signature_x=layout["signature_x"],
            signature_y=layout["signature_y"],
            signature_width=layout["signature_width"],
            signature_height=layout["signature_height"],
            signatory_name=layout.get("signatory_name"),
            signatory_title=layout.get("signatory_title"),
        )
        safe_pname = "".join(c for c in prog_name if c.isalnum() or c in " -_").strip() or "Program"
        label = "Team Certificate" if body.kind == "team" else "Certificate"
        attachments.append((f"{safe_pname} - {label}.pdf", pdf_bytes, "pdf"))

    banner = (
        "<div style=\"background:#6D28D9;color:#ffffff;padding:8px 14px;"
        "border-radius:10px;font-size:12px;font-weight:600;margin-bottom:14px;\">"
        "TEST EMAIL — Preview of the certificate email. No records were created.</div>"
    )
    await try_send_email(
        body.to_email,
        f"[TEST] {subj}",
        banner + html_body,
        html=True,
        attachments=attachments or None,
    )
    return {"sent": True, "to": body.to_email, "subject": f"[TEST] {subj}"}
