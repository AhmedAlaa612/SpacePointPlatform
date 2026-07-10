"""Shared documents router (PLAN §4.5/§8.2/§9.4) — top-level, not nested under
any one domain, since recommendation letters apply to any role. Same mounting
pattern as routers/notifications.py.
"""

import logging
import uuid
import base64
from datetime import date, datetime, timezone

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.dependencies import get_current_active_user, require_admin
from app.db.session import get_db
from app.models.enums import UserRole
from app.schemas.instructors.instructor import IdCardOut
from app.services.documents.id_card import ensure_card_id, render_card_png, render_card_back_png
from app.models.certificate import Certificate
from app.models.document_request import DocumentRequest
from app.models.document_template import DocumentTemplate
from app.models.enums import CertificateType
from app.services.settings import get_portal_setting as _get_setting
from app.models.document import Document
from app.models.user import User
from app.schemas.document_request import (
    DocumentRequestApprove,
    DocumentRequestCreate,
    DocumentRequestOut,
    DocumentRequestReview,
)
from app.schemas.documents import (
    DocumentOut,
    MyDocumentsOut,
    RecommendationLetterCreate,
    AvailableTemplateOut,
    DocumentTemplateOut,
    DocumentTemplateUpdate,
    DocumentTemplateCreate,
    StorageFileOut,
)
from app.schemas.instructors.payment import CertificateOut
from app.services import storage
from app.services.documents.certificate import generate_completion_certificate_pdf
from xml.sax.saxutils import escape
from app.services.documents.letters import generate_letter_pdf
from app.services.email import send_recommendation_letter_email
from app.services.notification import create_notification as notify

router = APIRouter(prefix="/documents", tags=["documents"])

logger = logging.getLogger("documents")


async def _get_signature_image_tag(db: AsyncSession) -> tuple[str | None, str]:
    """Downloads the admin signature from storage, saves it to a temp file, and returns the path and img tag."""
    import os
    import tempfile
    sig_url = await _get_setting(db, "admin_signature_url", "")
    if not sig_url:
        return None, "<br/><br/>"
        
    try:
        sig_data = await storage.download_file("instructor-documents", "settings/admin_signature.png")
        fd, temp_path = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as f:
            f.write(sig_data)
        img_tag = f'<br/><br/><img src="{temp_path}" width="100" height="35" valign="bottom"/><br/><br/>'
        return temp_path, img_tag
    except Exception as e:
        logger.warning("admin signature download failed: %s", e)
        return None, "<br/><br/>"


@router.get("/me", response_model=MyDocumentsOut)
async def my_documents(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    certs = (await db.execute(
        select(Certificate).where(Certificate.user_id == current_user.id).order_by(Certificate.generated_at.desc())
    )).scalars().all()
    docs = (await db.execute(
        select(Document).where(Document.user_id == current_user.id).order_by(Document.generated_at.desc())
    )).scalars().all()

    return MyDocumentsOut(
        certificates=[
            CertificateOut(
                id=c.id, user_id=c.user_id, type=c.type.value,
                workshop_name=c.workshop_name, workshop_date=c.workshop_date, location=c.location,
                file_url=await storage.resolve_url(c.bucket, c.file_path, c.file_url),
            )
            for c in certs
        ],
        documents=[
            DocumentOut(
                id=d.id, label=d.label, generated_at=d.generated_at,
                file_url=await storage.resolve_url(d.bucket, d.file_path, d.file_url),
            )
            for d in docs
        ],
    )


@router.post("/recommendation-letters", response_model=DocumentOut)
async def create_recommendation_letter(
    body: RecommendationLetterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = (await db.execute(select(User).where(User.id == body.user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    signatory_name = body.signatory_name or await _get_setting(
        db, "admin_signatory_name", settings.DEFAULT_SIGNATORY_NAME
    )
    signatory_title = body.signatory_title or await _get_setting(
        db, "admin_signatory_title", settings.DEFAULT_SIGNATORY_TITLE
    )

    import os
    sig_path, sig_tag = await _get_signature_image_tag(db)
    
    today = date.today().strftime("%d %B %Y").lstrip("0")
    escaped_body = escape(body.recommendation_text)
    formatted_body = (
        escaped_body
        .replace("{name}", escape(user.full_name))
        .replace("{date}", today)
        .replace("{role}", (user.role_values[0].title() if user.role_values else "Intern"))
        .replace("{signatory_name}", escape(signatory_name))
        .replace("{signatory_title}", escape(signatory_title))
        .replace("{signature}", sig_tag)
    )

    try:
        pdf_bytes = generate_letter_pdf(
            title="Letter of Recommendation",
            body_text=formatted_body,
            signatory_name=signatory_name,
            signatory_title=signatory_title,
        )
    finally:
        if sig_path and os.path.exists(sig_path):
            try:
                os.remove(sig_path)
            except Exception:
                pass
    doc_path = f"{user.id}/{uuid.uuid4()}.pdf"
    file_url = await storage.upload_file("documents", doc_path, pdf_bytes, "application/pdf")

    doc = Document(
        user_id=user.id, generated_by=current_user.id,
        label="Letter of Recommendation", file_url=file_url,
        bucket="documents", file_path=doc_path,
        data={"signatory_name": signatory_name, "signatory_title": signatory_title,
              "recommendation_text": body.recommendation_text},
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    await send_recommendation_letter_email(user.email, user.full_name)
    return doc


@router.get("/recommendation-letters", response_model=list[DocumentOut])
async def list_recommendation_letters(
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rows = (await db.execute(
        select(Document).where(Document.user_id == user_id)
        .order_by(Document.generated_at.desc())
    )).scalars().all()
    return [
        DocumentOut(
            id=d.id, label=d.label, generated_at=d.generated_at,
            file_url=await storage.resolve_url(d.bucket, d.file_path, d.file_url),
        )
        for d in rows
    ]


@router.delete("/{document_id}")
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin-only: remove a generated letter (Recommendation/Confirmation/Completion/
    template-based) — both the storage file and the `documents` row. Certificates have
    their own delete route (instructors/admin/payments/certificates/{id})."""
    doc = (await db.execute(select(Document).where(Document.id == document_id))).scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.bucket and doc.file_path:
        try:
            await storage.delete_file(doc.bucket, doc.file_path)
        except Exception as e:
            logger.warning("document file delete failed (%s/%s): %s", doc.bucket, doc.file_path, e)

    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}


# ── Document Requests (PLAN §8.2 / Task List) ───

@router.post("/requests", response_model=DocumentRequestOut)
async def create_document_request(
    body: DocumentRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Check if there is already a pending request of this type
    existing = (await db.execute(
        select(DocumentRequest).where(
            DocumentRequest.user_id == current_user.id,
            DocumentRequest.type == body.type,
            DocumentRequest.status == "pending"
        )
    )).scalars().first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"You already have a pending request for a {body.type}."
        )

    req = DocumentRequest(
        id=uuid.uuid4(),
        user_id=current_user.id,
        type=body.type,
        status="pending",
        requested_role=body.requested_role,
        notes=body.notes,
    )
    db.add(req)
    
    # Notify admins
    role_label = f" as {body.requested_role.title()}" if body.requested_role else ""
    type_label = body.type.replace("_", " ").title()
    admins = (await db.execute(
        select(User).where(User.roles.any("admin"))
    )).scalars().all()
    for admin in admins:
        await notify(
            db,
            admin.id,
            "New Document Request",
            f"{current_user.full_name} requested a {type_label}{role_label}.",
            "document_request"
        )
        
    await db.commit()
    await db.refresh(req)
    
    return DocumentRequestOut(
        id=req.id,
        user_id=req.user_id,
        user_name=current_user.full_name,
        user_email=current_user.email,
        type=req.type,
        status=req.status,
        requested_role=req.requested_role,
        notes=req.notes,
        admin_notes=req.admin_notes,
        file_url=req.file_url,
        created_at=req.created_at,
        updated_at=req.updated_at
    )


@router.get("/requests/me", response_model=list[DocumentRequestOut])
async def my_document_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    rows = (await db.execute(
        select(DocumentRequest)
        .where(DocumentRequest.user_id == current_user.id)
        .order_by(DocumentRequest.created_at.desc())
    )).scalars().all()
    
    return [
        DocumentRequestOut(
            id=req.id,
            user_id=req.user_id,
            user_name=current_user.full_name,
            user_email=current_user.email,
            type=req.type,
            status=req.status,
            requested_role=req.requested_role,
            notes=req.notes,
            admin_notes=req.admin_notes,
            file_url=await storage.resolve_url(req.bucket, req.file_path, req.file_url),
            user_created_at=current_user.created_at,
            created_at=req.created_at,
            updated_at=req.updated_at
        )
        for req in rows
    ]


@router.get("/requests", response_model=list[DocumentRequestOut])
async def list_document_requests(
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    query = select(DocumentRequest, User).join(User, DocumentRequest.user_id == User.id)
    if status:
        query = query.where(DocumentRequest.status == status)
    query = query.order_by(DocumentRequest.created_at.desc())
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        DocumentRequestOut(
            id=req.id,
            user_id=req.user_id,
            user_name=u.full_name,
            user_email=u.email,
            type=req.type,
            status=req.status,
            requested_role=req.requested_role,
            notes=req.notes,
            admin_notes=req.admin_notes,
            file_url=await storage.resolve_url(req.bucket, req.file_path, req.file_url),
            user_created_at=u.created_at,
            created_at=req.created_at,
            updated_at=req.updated_at
        )
        for req, u in rows
    ]


_ROLE_PROGRAM_MAP = {
    "instructor": "Instructor Program",
    "facilitator": "Facilitator Program",
    "teacher": "Teacher Program",
    "ambassador": "Ambassador Program",
}


async def _render_and_store_document(
    db: AsyncSession,
    *,
    user: User,
    template: DocumentTemplate,
    role: str,
    title: str,
    body_text: str | None,
    signatory_name: str,
    signatory_title: str,
    date_str: str,
    generated_by: uuid.UUID,
) -> tuple[str, str, str]:
    # Render a certificate/letter PDF from a template, upload it, persist the row,
    # and return (signed_url, bucket, path). Certificate vs letter is decided by
    # template.type (NOT by parsing the key). Shared by the document-request and
    # admin-generate flows. bucket/path are the durable identifiers (A2); the URL
    # is only for the immediate response.
    import os

    raw_body = body_text or template.body_text or ""
    start_date = user.created_at.strftime("%d %B %Y").lstrip("0")

    sig_path, sig_tag = await _get_signature_image_tag(db)
    try:
        # The body is template HTML; escape only the dynamic VALUES we substitute in.
        formatted_body = (
            raw_body
            .replace("{name}", escape(user.full_name))
            .replace("{start_date}", start_date)
            .replace("{end_date}", date_str)
            .replace("{date}", date_str)
            .replace("{role}", escape(role.title()))
            .replace("{signatory_name}", escape(signatory_name))
            .replace("{signatory_title}", escape(signatory_title))
            .replace("{signature}", sig_tag)
        )

        if template.type == "certificate":
            bg_bytes = None
            bg_path = template.template_file_path or (
                template.template_file_url.split("/library-resources/")[-1].split("?")[0]
                if template.template_file_url else None
            )
            if bg_path:
                try:
                    bg_bytes = await storage.download_file("library-resources", bg_path)
                except Exception as e:
                    logger.warning("certificate template background download failed: %s", e)
            program_label = _ROLE_PROGRAM_MAP.get(role, "Internship Program")
            pdf_bytes = generate_completion_certificate_pdf(
                recipient_name=user.full_name,
                body_text_template=formatted_body.replace("{program}", program_label),
                background_bytes=bg_bytes,
            )
            bucket, path = "certificates", f"{user.id}/completion_{uuid.uuid4()}.pdf"
            file_url = await storage.upload_file(bucket, path, pdf_bytes, "application/pdf")
            cert_type = CertificateType.instructor_completion if role == "instructor" else CertificateType.internship_completion
            db.add(Certificate(
                user_id=user.id, type=cert_type, file_url=file_url,
                bucket=bucket, file_path=path, generated_by=generated_by,
            ))
        else:
            pdf_bytes = generate_letter_pdf(
                title=title,
                body_text=formatted_body,
                signatory_name=signatory_name,
                signatory_title=signatory_title,
            )
            bucket, path = "documents", f"{user.id}/{uuid.uuid4()}.pdf"
            file_url = await storage.upload_file(bucket, path, pdf_bytes, "application/pdf")
            db.add(Document(
                user_id=user.id, template_id=template.id, generated_by=generated_by,
                label=title, file_url=file_url, bucket=bucket, file_path=path,
                data={"signatory_name": signatory_name, "signatory_title": signatory_title, "body": raw_body},
            ))
    finally:
        if sig_path and os.path.exists(sig_path):
            try:
                os.remove(sig_path)
            except Exception:
                pass

    return file_url, bucket, path


@router.post("/requests/{id}/generate", response_model=DocumentRequestOut)
async def generate_document_request(
    id: uuid.UUID,
    body: DocumentRequestApprove,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    req = await db.get(DocumentRequest, id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Request has already been processed")

    user = await db.get(User, req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == req.type)
    )).scalars().first()
    if not template:
        raise HTTPException(status_code=400, detail=f"No document template found for type: {req.type}")

    signatory_name = body.signatory_name or await _get_setting(db, "admin_signatory_name", settings.DEFAULT_SIGNATORY_NAME)
    signatory_title = body.signatory_title or await _get_setting(db, "admin_signatory_title", settings.DEFAULT_SIGNATORY_TITLE)
    today = body.date or date.today().strftime("%d %B %Y").lstrip("0")

    req.file_url, req.bucket, req.file_path = await _render_and_store_document(
        db, user=user, template=template,
        role=req.requested_role or "intern",
        title=body.title or template.name,
        body_text=body.recommendation_text,
        signatory_name=signatory_name, signatory_title=signatory_title,
        date_str=today, generated_by=current_user.id,
    )
    req.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(req)

    return DocumentRequestOut(
        id=req.id,
        user_id=req.user_id,
        user_name=user.full_name,
        user_email=user.email,
        type=req.type,
        status=req.status,
        notes=req.notes,
        admin_notes=req.admin_notes,
        file_url=await storage.resolve_url(req.bucket, req.file_path, req.file_url),
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


def _parse_storage_url(url: str) -> tuple[str, str]:
    """Parse bucket and path from a Supabase storage URL (signed or public).
    Legacy fallback only — new rows carry bucket/file_path columns (A2)."""
    import re
    from urllib.parse import unquote
    m = re.search(r"/storage/v1/object/(?:sign|public)/([^/]+)/([^?]+)", url)
    if m:
        return m.group(1), unquote(m.group(2))
    return "", ""


@router.post("/requests/{id}/approve", response_model=DocumentRequestOut)
async def approve_document_request(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    req = await db.get(DocumentRequest, id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Request has already been processed")
    if not req.file_url:
        raise HTTPException(status_code=400, detail="Document PDF must be generated before approving")
        
    user = await db.get(User, req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # The Certificate / Document row was already persisted at generate time
    # (generate_document_request → _render_and_store_document). Approval only
    # finalizes the request status — no second write, no key-substring routing.
    req.status = "approved"
    req.updated_at = datetime.now(timezone.utc)

    await notify(
        db,
        user.id,
        "Document Request Approved",
        f"Your request for a {req.type.replace('_', ' ').title()} has been approved and generated.",
        "document_request_approved"
    )

    await db.commit()
    await db.refresh(req)

    return DocumentRequestOut(
        id=req.id,
        user_id=req.user_id,
        user_name=user.full_name,
        user_email=user.email,
        type=req.type,
        status=req.status,
        notes=req.notes,
        admin_notes=req.admin_notes,
        file_url=await storage.resolve_url(req.bucket, req.file_path, req.file_url),
        created_at=req.created_at,
        updated_at=req.updated_at
    )


@router.post("/requests/{id}/regenerate", response_model=DocumentRequestOut)
async def regenerate_document_request(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    req = await db.get(DocumentRequest, id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Request has already been processed")
    user = await db.get(User, req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete file from storage if present — prefer the stored bucket/path (A2),
    # fall back to parsing the legacy URL.
    bucket, path = (req.bucket, req.file_path) if (req.bucket and req.file_path) \
        else (_parse_storage_url(req.file_url) if req.file_url else ("", ""))
    if bucket and path:
        try:
            await storage.delete_file(bucket, path)
        except Exception as e:
            logger.warning("storage delete during regeneration failed: %s", e)

    req.file_url = None
    req.bucket = None
    req.file_path = None
    req.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(req)
    
    return DocumentRequestOut(
        id=req.id,
        user_id=req.user_id,
        user_name=user.full_name,
        user_email=user.email,
        type=req.type,
        status=req.status,
        notes=req.notes,
        admin_notes=req.admin_notes,
        file_url=req.file_url,
        created_at=req.created_at,
        updated_at=req.updated_at
    )


@router.post("/requests/{id}/reject", response_model=DocumentRequestOut)
async def reject_document_request(
    id: uuid.UUID,
    body: DocumentRequestReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    req = await db.get(DocumentRequest, id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Request has already been processed")
        
    req.status = "rejected"
    req.admin_notes = body.admin_notes
    req.updated_at = datetime.now(timezone.utc)
    
    user = await db.get(User, req.user_id)
    user_name = user.full_name if user else ""
    user_email = user.email if user else ""
    
    await notify(
        db,
        req.user_id,
        "Document Request Rejected",
        f"Your request for a {req.type} has been rejected: {body.admin_notes or ''}",
        "document_request_rejected"
    )
    
    await db.commit()
    await db.refresh(req)
    
    return DocumentRequestOut(
        id=req.id,
        user_id=req.user_id,
        user_name=user_name,
        user_email=user_email,
        type=req.type,
        status=req.status,
        notes=req.notes,
        admin_notes=req.admin_notes,
        created_at=req.created_at,
        updated_at=req.updated_at
    )


def _ext(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1]


@router.get("/id-card", response_model=IdCardOut)
async def get_my_id_card(
    role: UserRole,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Render the ID card front and back on-the-fly for any role."""
    if role not in current_user.roles:
        raise HTTPException(status_code=403, detail="You do not have this role")

    card_row = await ensure_card_id(db, current_user.id, role)
    await db.commit()

    linkedin_url = current_user.linkedin_url

    from app.routers.instructors.instructor import _photo_bytes_for
    photo_bytes = await _photo_bytes_for(current_user)
    await db.commit()
    photo_url = current_user.photo_url

    front_png = render_card_png(role, photo_bytes, linkedin_url, current_user.full_name)
    issue_date = card_row.generated_at or datetime.now(timezone.utc)
    back_png = render_card_back_png(role, card_row.card_id, issue_date)

    return IdCardOut(
        card_id=card_row.card_id,
        front_b64=base64.b64encode(front_png).decode(),
        back_b64=base64.b64encode(back_png).decode(),
        generated_at=card_row.generated_at,
        has_photo=bool(photo_url or current_user.photo_path),
        has_linkedin=bool(linkedin_url),
        photo_url=photo_url,
        linkedin_url=linkedin_url,
    )


@router.post("/id-card", response_model=IdCardOut)
async def update_my_id_card(
    role: UserRole,
    photo: UploadFile | None = None,
    linkedin_url: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload photo and/or update LinkedIn URL for any role's ID card."""
    if role not in current_user.roles:
        raise HTTPException(status_code=403, detail="You do not have this role")

    try:
        card_row = await ensure_card_id(db, current_user.id, role)

        if linkedin_url is not None:
            current_user.linkedin_url = linkedin_url or None

        photo_bytes = None
        if photo and photo.filename:
            photo_bytes = await photo.read()
            photo_path = f"{current_user.id}{_ext(photo.filename)}"
            uploaded_url = await storage.upload_file(
                "profile_pictures",
                photo_path,
                photo_bytes,
                photo.content_type or "image/jpeg",
            )
            current_user.photo_url = uploaded_url
            current_user.photo_path = photo_path

        await db.commit()

        final_photo_url = current_user.photo_url
        final_linkedin_url = current_user.linkedin_url

        if photo_bytes is None:
            from app.routers.instructors.instructor import _photo_bytes_for
            photo_bytes = await _photo_bytes_for(current_user)
            await db.commit()
            final_photo_url = current_user.photo_url

        front_png = render_card_png(role, photo_bytes, final_linkedin_url, current_user.full_name)
        issue_date = card_row.generated_at or datetime.now(timezone.utc)
        back_png = render_card_back_png(role, card_row.card_id, issue_date)

        return IdCardOut(
            card_id=card_row.card_id,
            front_b64=base64.b64encode(front_png).decode(),
            back_b64=base64.b64encode(back_png).decode(),
            generated_at=card_row.generated_at,
            has_photo=bool(final_photo_url or current_user.photo_path),
            has_linkedin=bool(final_linkedin_url),
            photo_url=final_photo_url,
            linkedin_url=final_linkedin_url,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update ID card: {str(e)}"
        )


@router.get("/id-card/pdf")
async def download_my_id_card_pdf(
    role: UserRole,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Download a printable PDF of the ID card for any role."""
    if role not in current_user.roles:
        raise HTTPException(status_code=403, detail="You do not have this role")

    card_row = await ensure_card_id(db, current_user.id, role)
    await db.commit()

    final_linkedin_url = current_user.linkedin_url

    from app.routers.instructors.instructor import _photo_bytes_for
    photo_bytes = await _photo_bytes_for(current_user)
    await db.commit()

    front_png = render_card_png(role, photo_bytes, final_linkedin_url, current_user.full_name)
    issue_date = card_row.generated_at or datetime.now(timezone.utc)
    back_png = render_card_back_png(role, card_row.card_id, issue_date)

    from io import BytesIO
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image as PILImage

    # Wrap front and back in a CR80-sized PDF
    buf = BytesIO()
    w, h = 3.375 * inch, 2.125 * inch
    c = rl_canvas.Canvas(buf, pagesize=(w, h))
    
    # Page 1: Front
    front_img = PILImage.open(BytesIO(front_png)).rotate(-90, expand=True)
    img_buf1 = BytesIO()
    front_img.save(img_buf1, format="PNG")
    img_buf1.seek(0)
    c.drawImage(ImageReader(img_buf1), 0, 0, width=w, height=h)
    c.showPage()
    
    # Page 2: Back
    back_img = PILImage.open(BytesIO(back_png)).rotate(-90, expand=True)
    img_buf2 = BytesIO()
    back_img.save(img_buf2, format="PNG")
    img_buf2.seek(0)
    c.drawImage(ImageReader(img_buf2), 0, 0, width=w, height=h)
    c.showPage()

    c.save()

    filename = f"SpacePoint_ID_{card_row.card_id or current_user.id}.pdf"
    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Admin: generate document directly from template ───────────────────────────

class AdminGenerateDocBody(BaseModel):
    user_id: uuid.UUID
    template_key: str
    body_text: str
    signatory_name: Optional[str] = None
    signatory_title: Optional[str] = None
    date: Optional[str] = None
    title: Optional[str] = None


@router.post("/admin/generate")
async def admin_generate_document(
    body: AdminGenerateDocBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Generate a document for any user using a template, with admin-edited body text.
    user = (await db.execute(select(User).where(User.id == body.user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == body.template_key)
    )).scalars().first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    signatory_name = body.signatory_name or await _get_setting(db, "admin_signatory_name", settings.DEFAULT_SIGNATORY_NAME)
    signatory_title = body.signatory_title or await _get_setting(db, "admin_signatory_title", settings.DEFAULT_SIGNATORY_TITLE)
    today = body.date or date.today().strftime("%d %B %Y").lstrip("0")
    role = user.role_values[0] if user.role_values else "intern"

    file_url, _bucket, _path = await _render_and_store_document(
        db, user=user, template=template, role=role,
        title=body.title or template.name,
        body_text=body.body_text,
        signatory_name=signatory_name, signatory_title=signatory_title,
        date_str=today, generated_by=current_user.id,
    )

    await notify(db, user.id, "New Document",
                 f"A new document ({template.name}) has been generated for you.", type="document")
    await db.commit()
    return {"file_url": file_url}


# ── Templates & Storage Endpoints ─────────────────────────────────────────────

@router.get("/templates/available", response_model=list[AvailableTemplateOut])
async def get_available_templates(
    role: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve templates where the given role is in the roles array."""
    from sqlalchemy import func, cast
    templates = (await db.execute(
        select(DocumentTemplate).where(
            DocumentTemplate.roles.any(role)  # type: ignore[attr-defined]
        )
    )).scalars().all()
    return [
        AvailableTemplateOut(id=t.id, key=t.key, name=t.name, roles=t.roles or [])
        for t in templates
    ]


@router.get("/admin/storage/buckets", response_model=list[str])
async def list_buckets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List names of all Supabase storage buckets."""
    return [
        "documents", "certificates", "instructor-documents",
        "applicant-submissions", "contracts", "payment-letters",
        "profile_pictures", "library-resources", "cvs",
    ]


async def _list_files_recursive(bucket: str, path: str = "") -> list[dict]:
    items = await storage.list_files(bucket, path)
    res = []
    for item in items:
        name = item.get("name", "")
        if not name or name == ".keep":
            continue
            
        item_path = f"{path}/{name}" if path else name
        metadata = item.get("metadata")
        
        if metadata is None:
            # Recursively traverse directory
            sub_items = await _list_files_recursive(bucket, item_path)
            res.extend(sub_items)
        else:
            item["name"] = item_path
            res.append(item)
    return res


@router.get("/admin/storage/files", response_model=list[StorageFileOut])
async def list_bucket_files(
    bucket: str,
    path: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List files inside a bucket path recursively, complete with signed URL links, owner names, and clean document type labels."""
    import re
    files = await _list_files_recursive(bucket, path)
    
    # 1. Extract unique user UUIDs from file paths
    uuid_pattern = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    user_ids = set()
    for f in files:
        name = f.get("name", "")
        match = uuid_pattern.search(name)
        if match:
            try:
                user_ids.add(uuid.UUID(match.group(0)))
            except ValueError:
                pass
                
    # 2. Bulk query users to resolve full names
    user_map = {}
    if user_ids:
        db_users = (await db.execute(
            select(User).where(User.id.in_(list(user_ids)))
        )).scalars().all()
        user_map = {str(u.id): u.full_name for u in db_users}
        
    # Helper to clean up filenames & build readable doc types
    def get_doc_type_label(b: str, filename: str) -> str:
        lower_name = filename.lower()
        if b == "certificates":
            if "instructor" in lower_name:
                return "Instructor Program Completion Certificate"
            return "Internship Completion Certificate"
        if b == "intern-letters":
            if "confirmation" in lower_name:
                return "Internship Confirmation Letter"
            if "completion" in lower_name:
                return "Internship Completion Letter"
            return "Internship Letter"
        if b == "recommendation-letters":
            return "Recommendation Letter"
        if b == "profile_pictures":
            return "Profile Photo"

        if b == "payment-letters":
            if "signed" in lower_name:
                return "Signed Payment Letter"
            return "Payment Letter Draft"
        if b == "contracts":
            return "Signed Contract"
            
        # Fallback parsing
        basename = filename.split("/")[-1]
        name_no_ext = basename.split(".")[0]
        # Strip uuid matching, replace underscores, title case
        clean = uuid_pattern.sub("", name_no_ext)
        clean = clean.replace("_", " ").replace("-", " ").strip()
        return clean.title() or "Document"

    res = []
    for f in files:
        name = f.get("name", "")
        metadata = f.get("metadata") or {}
        size = metadata.get("size")
        mimetype = metadata.get("mimetype")
        last_modified = metadata.get("lastModified")
        
        signed_url = None
        if size is not None:
            try:
                signed_url = await storage.get_signed_url(bucket, name)
            except Exception:
                pass
                
        # Resolve owner name
        owner_name = None
        match = uuid_pattern.search(name)
        if match and match.group(0) in user_map:
            owner_name = user_map[match.group(0)]
            
        doc_label = get_doc_type_label(bucket, name)
        
        res.append(
            StorageFileOut(
                name=name,
                size=size,
                mimetype=mimetype,
                last_modified=last_modified,
                signed_url=signed_url,
                owner_name=owner_name,
                document_type_label=doc_label
            )
        )
    return res


@router.delete("/admin/storage/files")
async def delete_bucket_file(
    bucket: str,
    path: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a file from a storage bucket."""
    await storage.delete_file(bucket, path)
    return {"message": "File deleted successfully"}


@router.get("/admin/templates", response_model=list[DocumentTemplateOut])
async def list_document_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Retrieve all document templates, sorted by role and name."""
    templates = (await db.execute(
        select(DocumentTemplate).order_by(DocumentTemplate.name)
    )).scalars().all()
    return templates


@router.put("/admin/templates/{id}", response_model=DocumentTemplateOut)
async def update_document_template(
    id: uuid.UUID,
    name: Optional[str] = Form(None),
    roles: Optional[str] = Form(None),  # JSON array string e.g. '["intern","instructor"]'
    body_text: Optional[str] = Form(None),
    type: Optional[str] = Form(None),   # 'letter' | 'certificate'
    file: Optional[UploadFile] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update template properties, body text, or upload a custom frame background file."""
    import os, json
    template = await db.get(DocumentTemplate, id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    if name is not None:
        template.name = name
    if roles is not None:
        try:
            parsed_roles = json.loads(roles)
            if isinstance(parsed_roles, list):
                template.roles = parsed_roles
        except (json.JSONDecodeError, ValueError):
            pass
    if body_text is not None:
        template.body_text = body_text
    if type is not None and type in ("letter", "certificate"):
        template.type = type

    if file and file.filename:
        file_bytes = await file.read()
        ext = os.path.splitext(file.filename)[1]
        file_path = f"templates/{template.key}{ext}"
        file_url = await storage.upload_file(
            "library-resources",
            file_path,
            file_bytes,
            file.content_type or "application/octet-stream"
        )
        template.template_file_url = file_url
        template.template_file_path = file_path
        
    await db.commit()
    await db.refresh(template)
    return template


@router.post("/admin/templates", response_model=DocumentTemplateOut)
async def create_document_template(
    body: DocumentTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new document template."""
    existing = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == body.key)
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Template key already exists")
        
    template = DocumentTemplate(
        id=uuid.uuid4(),
        key=body.key,
        name=body.name,
        roles=body.roles,
        body_text=body.body_text,
        type=body.type if body.type in ("letter", "certificate") else "letter",
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/admin/templates/{id}")
async def delete_document_template(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a document template."""
    template = await db.get(DocumentTemplate, id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.is_system:
        raise HTTPException(status_code=400, detail="System templates can't be deleted")

    await db.delete(template)
    await db.commit()
    return {"message": "Template deleted successfully"}
