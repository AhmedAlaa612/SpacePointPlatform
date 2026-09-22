"""Program Certificate Templates Router (2026-09).

Provides CRUD, asset uploads (backgrounds and signatures), and live PDF
preview rendering for program-level custom certificate layouts.
"""

from __future__ import annotations

import asyncio
from html import escape
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.sessions.program import Program
from app.models.sessions.program_certificate_template import ProgramCertificateTemplate
from app.models.user import User
from app.schemas.sessions.program_certificate_template import (
    CertificatePreviewRequest,
    ProgramCertificateTemplateCreate,
    ProgramCertificateTemplateOut,
    ProgramCertificateTemplateUpdate,
)
from app.services import storage
from app.services.documents.certificate import (
    _TEMPLATE_PATHS,
    format_certificate_program_title,
    generate_completion_certificate_pdf,
)
from app.services.settings import get_portal_setting

router = APIRouter(prefix="/sessions/programs", tags=["sessions-certificate-templates"])


@router.get("/stock-template-image")
async def get_stock_template_image(theme: str = "dark"):
    """Serves the stock background template image for live UI preview."""
    import os
    template_path = _TEMPLATE_PATHS.get(theme, _TEMPLATE_PATHS["dark"])
    if os.path.exists(template_path):
        with open(template_path, "rb") as f:
            content = f.read()
        return Response(content=content, media_type="image/png")
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template image not found")


@router.get("/stock-signature-image")
async def get_stock_signature_image(theme: str = "dark"):
    """Serves the global admin signature image if uploaded, or fallback to static branding asset."""
    import os
    from app.services.documents.certificate import _STATIC_DIR

    try:
        sig_bytes = await storage.download_file("instructor-documents", "settings/admin_signature.png")
        if sig_bytes:
            return Response(content=sig_bytes, media_type="image/png")
    except Exception:
        pass

    branding_file = "admin_signature_white.png" if theme == "dark" else "admin_signature_dark.png"
    fallback_path = os.path.join(_STATIC_DIR, "branding", branding_file)
    if os.path.exists(fallback_path):
        with open(fallback_path, "rb") as f:
            content = f.read()
        return Response(content=content, media_type="image/png")
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Stock signature not configured")


@router.get("/stock-signatory-info")
async def get_stock_signatory_info(db: AsyncSession = Depends(get_db)):
    """Returns the global admin signatory name and title from portal_settings."""
    from app.core.config import settings as app_settings
    sig_name = await get_portal_setting(db, "admin_signatory_name", app_settings.DEFAULT_SIGNATORY_NAME)
    sig_title = await get_portal_setting(db, "admin_signatory_title", app_settings.DEFAULT_SIGNATORY_TITLE)
    return {
        "signatory_name": sig_name or app_settings.DEFAULT_SIGNATORY_NAME,
        "signatory_title": sig_title or app_settings.DEFAULT_SIGNATORY_TITLE,
    }


async def _enrich_template_urls(template: ProgramCertificateTemplate) -> None:
    """Resolves fresh storage URLs for background and signature images."""
    if template.background_file_path:
        template.background_file_url = await storage.resolve_url(
            "documents", template.background_file_path, fallback_url=template.background_file_url
        )
    if template.signature_image_path:
        template.signature_image_url = await storage.resolve_url(
            "documents", template.signature_image_path, fallback_url=template.signature_image_url
        )


@router.get("/{program_id}/certificate-templates", response_model=list[ProgramCertificateTemplateOut])
async def list_program_certificate_templates(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    templates = (
        await db.execute(
            select(ProgramCertificateTemplate)
            .where(ProgramCertificateTemplate.program_id == program_id)
            .order_by(ProgramCertificateTemplate.created_at.asc())
        )
    ).scalars().all()

    for t in templates:
        await _enrich_template_urls(t)

    return templates


@router.post(
    "/{program_id}/certificate-templates",
    response_model=ProgramCertificateTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_program_certificate_template(
    program_id: uuid.UUID,
    body: ProgramCertificateTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    data = body.model_dump()
    new_template = ProgramCertificateTemplate(id=uuid.uuid4(), program_id=program_id, **data)
    db.add(new_template)
    await db.flush()

    if new_template.is_default:
        # Clear default on all other templates for this program
        existing_defaults = (
            await db.execute(
                select(ProgramCertificateTemplate).where(
                    ProgramCertificateTemplate.program_id == program_id,
                    ProgramCertificateTemplate.is_default.is_(True),
                    ProgramCertificateTemplate.id != new_template.id,
                )
            )
        ).scalars().all()
        for t in existing_defaults:
            t.is_default = False
        program.default_certificate_template_id = new_template.id

    await db.commit()
    await db.refresh(new_template)
    await _enrich_template_urls(new_template)
    return new_template


@router.get("/{program_id}/certificate-templates/{template_id}", response_model=ProgramCertificateTemplateOut)
async def get_program_certificate_template(
    program_id: uuid.UUID,
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    template = await db.get(ProgramCertificateTemplate, template_id)
    if template is None or template.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Certificate template not found")

    await _enrich_template_urls(template)
    return template


@router.put("/{program_id}/certificate-templates/{template_id}", response_model=ProgramCertificateTemplateOut)
async def update_program_certificate_template(
    program_id: uuid.UUID,
    template_id: uuid.UUID,
    body: ProgramCertificateTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    template = await db.get(ProgramCertificateTemplate, template_id)
    if template is None or template.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Certificate template not found")

    changes = body.model_dump(exclude_unset=True)

    if changes.get("is_default") is True:
        existing_defaults = (
            await db.execute(
                select(ProgramCertificateTemplate).where(
                    ProgramCertificateTemplate.program_id == program_id,
                    ProgramCertificateTemplate.is_default.is_(True),
                    ProgramCertificateTemplate.id != template_id,
                )
            )
        ).scalars().all()
        for t in existing_defaults:
            t.is_default = False
        program.default_certificate_template_id = template.id
    elif changes.get("is_default") is False:
        if program.default_certificate_template_id == template.id:
            program.default_certificate_template_id = None

    for field, value in changes.items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)
    await _enrich_template_urls(template)
    return template


@router.delete(
    "/{program_id}/certificate-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_program_certificate_template(
    program_id: uuid.UUID,
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    template = await db.get(ProgramCertificateTemplate, template_id)
    if template is None or template.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Certificate template not found")

    if program and program.default_certificate_template_id == template.id:
        program.default_certificate_template_id = None

    # Delete storage assets if custom
    if template.background_file_path:
        try:
            await storage.delete_file("documents", template.background_file_path)
        except Exception:
            pass
    if template.signature_image_path:
        try:
            await storage.delete_file("documents", template.signature_image_path)
        except Exception:
            pass

    await db.delete(template)
    await db.commit()


@router.post(
    "/{program_id}/certificate-templates/{template_id}/set-default",
    response_model=ProgramCertificateTemplateOut,
)
async def set_default_program_certificate_template(
    program_id: uuid.UUID,
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    template = await db.get(ProgramCertificateTemplate, template_id)
    if template is None or template.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Certificate template not found")

    all_templates = (
        await db.execute(
            select(ProgramCertificateTemplate).where(ProgramCertificateTemplate.program_id == program_id)
        )
    ).scalars().all()

    for t in all_templates:
        t.is_default = (t.id == template_id)

    program.default_certificate_template_id = template.id
    await db.commit()
    await db.refresh(template)
    await _enrich_template_urls(template)
    return template


@router.post("/{program_id}/certificate-templates/set-stock-default")
async def set_stock_default_certificate_template(
    program_id: uuid.UUID,
    theme: str = "dark",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Sets the stock default template ('dark' or 'light') as auto-send default,
    clearing custom defaults.
    """
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    all_templates = (
        await db.execute(
            select(ProgramCertificateTemplate).where(ProgramCertificateTemplate.program_id == program_id)
        )
    ).scalars().all()

    for t in all_templates:
        t.is_default = False

    program.default_certificate_template_id = None
    await db.commit()
    return {"default_theme": theme if theme in ("dark", "light") else "dark"}


@router.post("/{program_id}/certificate-templates/upload-background")
async def upload_certificate_background(
    program_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    ext = (file.filename or "").split(".")[-1].lower() if "." in (file.filename or "") else "png"
    if ext not in ("png", "jpg", "jpeg", "webp"):
        ext = "png"

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty file uploaded")

    storage_path = f"certificate-templates/{program_id}/{uuid.uuid4()}.{ext}"
    content_type = file.content_type or f"image/{ext}"
    url = await storage.upload_file("documents", storage_path, file_bytes, content_type)
    return {
        "file_path": storage_path,
        "file_url": url,
    }


@router.post("/{program_id}/certificate-templates/upload-signature")
async def upload_certificate_signature(
    program_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    ext = (file.filename or "").split(".")[-1].lower() if "." in (file.filename or "") else "png"
    if ext not in ("png", "jpg", "jpeg", "webp"):
        ext = "png"

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty file uploaded")

    storage_path = f"certificate-signatures/{program_id}/{uuid.uuid4()}.{ext}"
    content_type = file.content_type or f"image/{ext}"
    url = await storage.upload_file("documents", storage_path, file_bytes, content_type)
    return {
        "file_path": storage_path,
        "file_url": url,
    }


@router.post("/{program_id}/certificate-templates/preview")
async def preview_certificate_template(
    program_id: uuid.UUID,
    body: CertificatePreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Generates a real-time single-page PDF certificate matching the draft
    parameters for interactive designer preview and validation.
    """
    program = await db.get(Program, program_id)
    prog_name = program.name if program else (body.program_name or "Program Name")
    cohort_name = body.cohort_name or "Cohort Title"
    dates = body.dates or "12 – 16 October 2026"
    location = body.location or "Muscat, Oman"
    raw_template = body.body_text or "For successfully completing<br/>{program_name}<br/>{dates}"
    body_text = (
        raw_template.replace("{program_name}", escape(prog_name))
        .replace("{cohort_name}", escape(cohort_name))
        .replace("{cohort}", escape(cohort_name))
        .replace("{dates}", escape(dates))
        .replace("{location}", escape(location))
    )

    # 1. Background bytes
    bg_bytes: bytes | None = None
    if body.background_type == "custom" and body.background_file_path:
        try:
            bg_bytes = await storage.download_file("documents", body.background_file_path)
        except Exception:
            bg_bytes = None

    # 2. Signature bytes & Signatory info
    sig_bytes: bytes | None = None
    from app.core.config import settings as app_settings
    sig_name = await get_portal_setting(db, "admin_signatory_name", app_settings.DEFAULT_SIGNATORY_NAME)
    sig_title = await get_portal_setting(db, "admin_signatory_title", app_settings.DEFAULT_SIGNATORY_TITLE)

    if body.show_signature:
        if body.signature_image_path:
            try:
                sig_bytes = await storage.download_file("documents", body.signature_image_path)
            except Exception:
                sig_bytes = None
        if not sig_bytes:
            # Fall back to global admin signature in system settings if configured
            try:
                sig_bytes = await storage.download_file("instructor-documents", "settings/admin_signature.png")
            except Exception:
                sig_bytes = None

    theme = body.background_type if body.background_type in ("dark", "light") else "dark"

    pdf_bytes = await asyncio.to_thread(
        generate_completion_certificate_pdf,
        recipient_name=body.recipient_name or "Student Name",
        body_text_template=body_text,
        background_bytes=bg_bytes,
        theme=theme,
        name_font_size=body.name_font_size,
        name_y=body.name_y,
        name_color=body.name_color,
        body_font_size=body.body_font_size,
        body_y=body.body_y,
        body_color=body.body_color,
        body_max_width=body.body_max_width,
        body_alignment=body.body_alignment,
        show_signature=body.show_signature,
        signature_bytes=sig_bytes,
        signature_x=body.signature_x,
        signature_y=body.signature_y,
        signature_width=body.signature_width,
        signature_height=body.signature_height,
        signatory_name=sig_name,
        signatory_title=sig_title,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="certificate_preview.pdf"'},
    )
