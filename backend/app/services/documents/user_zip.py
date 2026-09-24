"""Bundles a user's uploaded documents into a single ZIP archive.

Supports all roles (instructors, facilitators, applicants, interns, etc.):
- Personal Vault documents (Emirates ID, Passport, Visa, Clearance, Photo, etc.) from `instructor_documents`
- Application CV / Resume from `applications`
- Signed contracts from `instructor_profiles`
- Signed payment letters from `payment_letters`
- (Optional) Module submissions from onboarding checklist if include_module_submissions=True
- (Optional) System-generated certificates/letters if include_generated=True.
"""

import io
import os
import re
import zipfile
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.certificate import Certificate
from app.models.document import Document
from app.models.enums import CertificateType
from app.models.instructors.checklist import ChecklistModule
from app.models.instructors.instructor_document import InstructorDocument
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.instructors.module_submission import ModuleSubmission
from app.models.instructors.payment import PaymentLetter
from app.models.user import User
from app.services import storage

_CERT_LABEL = {
    CertificateType.workshop_delivery: "Workshop_Delivery_Certificate",
    CertificateType.internship_completion: "Internship_Completion_Certificate",
    CertificateType.instructor_completion: "Instructor_Completion_Certificate",
}


def _clean_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\. ]", "_", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "document"


def _infer_extension(file_path: str | None, file_url: str | None, data: bytes) -> str:
    candidate = file_path or (file_url.split("?")[0] if file_url else "")
    _, ext = os.path.splitext(candidate)
    if ext and 1 < len(ext) <= 6:
        return ext
    # Magic bytes fallback
    if data.startswith(b"%PDF"):
        return ".pdf"
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"PK\x03\x04"):
        return ".zip"
    return ".pdf"


async def _get_file_bytes(
    bucket: str | None, file_path: str | None, file_url: str | None
) -> bytes | None:
    if bucket and file_path:
        try:
            return await storage.download_file(bucket, file_path)
        except Exception:
            pass
    resolved_url = await storage.resolve_url(bucket, file_path, file_url)
    if resolved_url:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(resolved_url)
                if resp.status_code == 200:
                    return resp.content
        except Exception:
            pass
    return None


async def get_user_document_items(
    user_id: UUID,
    db: AsyncSession,
    include_generated: bool = False,
    include_module_submissions: bool = False,
) -> tuple[User, list[tuple[str, bytes]]]:
    """Retrieve all document files (filename, bytes) for a user."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    items_to_fetch: list[tuple[str, str | None, str | None, str | None]] = []

    # 1. Personal Vault documents (Emirates ID, Passport, Visa, CV, etc.)
    vault_docs = (
        await db.execute(
            select(InstructorDocument)
            .where(InstructorDocument.user_id == user_id)
            .order_by(InstructorDocument.uploaded_at.desc())
        )
    ).scalars().all()
    for doc in vault_docs:
        label = doc.document_type or "Document"
        items_to_fetch.append((label, doc.bucket, doc.file_path, doc.file_url))

    # 2. Application CV / Resume
    applications = (
        await db.execute(
            select(Application)
            .where(Application.email == user.email)
            .order_by(Application.created_at.desc())
        )
    ).scalars().all()
    for app_row in applications:
        if app_row.cv_path or app_row.cv_url:
            items_to_fetch.append(("CV_Resume", "cvs", app_row.cv_path, app_row.cv_url))

    # 3. Module Submissions (checklist onboarding modules) - excluded unless explicitly requested
    if include_module_submissions:
        subs = (
            await db.execute(
                select(ModuleSubmission, ChecklistModule.title)
                .join(ChecklistModule, ChecklistModule.id == ModuleSubmission.module_id)
                .where(ModuleSubmission.user_id == user_id)
            )
        ).all()
        for sub, module_title in subs:
            if sub.file_path or sub.file_url:
                label = f"{module_title}_{sub.original_filename or 'submission'}"
                items_to_fetch.append((label, sub.bucket, sub.file_path, sub.file_url))

    # 4. Instructor Profile - signed contract
    profile = (
        await db.execute(
            select(InstructorProfile).where(InstructorProfile.user_id == user_id)
        )
    ).scalars().first()
    if profile:
        if profile.signed_contract_path or profile.signed_contract_url:
            items_to_fetch.append(
                ("Signed_Contract", "contracts", profile.signed_contract_path, profile.signed_contract_url)
            )
        elif include_generated and (profile.contract_path or profile.contract_url):
            items_to_fetch.append(
                ("Contract", "contracts", profile.contract_path, profile.contract_url)
            )

    # 5. Payment Letters - signed letters
    letters = (
        await db.execute(
            select(PaymentLetter).where(PaymentLetter.instructor_user_id == user_id)
        )
    ).scalars().all()
    for letter in letters:
        if letter.signed_pdf_path or letter.signed_pdf_url:
            items_to_fetch.append(
                (f"Signed_Payment_Letter_{letter.reference}", "payment-letters", letter.signed_pdf_path, letter.signed_pdf_url)
            )
        elif include_generated and (letter.pdf_path or letter.pdf_url):
            items_to_fetch.append(
                (f"Payment_Letter_{letter.reference}", "payment-letters", letter.pdf_path, letter.pdf_url)
            )

    # 6. Generated certificates and documents if requested
    if include_generated:
        docs = (
            await db.execute(select(Document).where(Document.user_id == user_id))
        ).scalars().all()
        for d in docs:
            items_to_fetch.append((d.label, d.bucket, d.file_path, d.file_url))

        certs = (
            await db.execute(select(Certificate).where(Certificate.user_id == user_id))
        ).scalars().all()
        for c in certs:
            label = _CERT_LABEL.get(c.type, str(c.type))
            if c.workshop_name:
                label = f"{label}_{c.workshop_name}"
            items_to_fetch.append((label, c.bucket, c.file_path, c.file_url))

    files_to_zip: list[tuple[str, bytes]] = []
    used_names: set[str] = set()

    for base_label, bucket, file_path, file_url in items_to_fetch:
        data = await _get_file_bytes(bucket, file_path, file_url)
        if not data:
            continue

        ext = _infer_extension(file_path, file_url, data)
        cleaned_base = _clean_filename(base_label)
        if cleaned_base.lower().endswith(ext.lower()):
            candidate = cleaned_base
        else:
            candidate = f"{cleaned_base}{ext}"

        stem, file_ext = os.path.splitext(candidate)
        final_name = candidate
        counter = 2
        while final_name.lower() in used_names:
            final_name = f"{stem}_{counter}{file_ext}"
            counter += 1
        used_names.add(final_name.lower())

        files_to_zip.append((final_name, data))

    return user, files_to_zip


async def build_user_documents_zip(
    user_id: UUID,
    db: AsyncSession,
    include_generated: bool = False,
    include_module_submissions: bool = False,
) -> tuple[bytes, str]:
    """Compile all uploaded documents for a single user into a ZIP archive.

    Returns (zip_bytes, zip_filename).
    Raises HTTPException(404) if user not found or no documents are available.
    """
    user, files_to_zip = await get_user_document_items(
        user_id, db, include_generated=include_generated, include_module_submissions=include_module_submissions
    )
    if not files_to_zip:
        raise HTTPException(
            status_code=404,
            detail="No uploaded documents found for this user.",
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, file_bytes in files_to_zip:
            zf.writestr(fname, file_bytes)

    zip_buffer.seek(0)
    zip_bytes = zip_buffer.getvalue()

    safe_name = "".join(c for c in user.full_name if c.isalnum() or c in " -_").strip().replace(" ", "_")
    zip_filename = f"{safe_name or str(user.id)}_documents.zip"

    return zip_bytes, zip_filename


async def build_multi_users_documents_zip(
    user_ids: Sequence[UUID],
    db: AsyncSession,
    include_generated: bool = False,
    include_module_submissions: bool = False,
) -> tuple[bytes, str]:
    """Compile uploaded documents for multiple users into a single ZIP archive,
    with a dedicated folder for each user named after them.
    """
    if not user_ids:
        raise HTTPException(status_code=400, detail="No users specified.")

    zip_buffer = io.BytesIO()
    total_files = 0
    used_folder_names: dict[str, int] = {}

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for uid in user_ids:
            try:
                user, files = await get_user_document_items(
                    uid, db, include_generated=include_generated, include_module_submissions=include_module_submissions
                )
            except HTTPException:
                continue

            base_folder = "".join(c for c in user.full_name if c.isalnum() or c in " -_").strip().replace(" ", "_")
            if not base_folder:
                base_folder = f"User_{str(uid)[:8]}"

            # Disambiguate folder names if users share identical names
            count = used_folder_names.get(base_folder.lower(), 0)
            used_folder_names[base_folder.lower()] = count + 1
            folder_name = base_folder if count == 0 else f"{base_folder}_{count + 1}"

            if not files:
                zf.writestr(
                    f"{folder_name}/_no_documents_uploaded.txt",
                    f"No uploaded documents found for {user.full_name} ({user.email}).\n".encode("utf-8"),
                )
                total_files += 1
            else:
                for fname, file_bytes in files:
                    zf.writestr(f"{folder_name}/{fname}", file_bytes)
                    total_files += 1

    if total_files == 0:
        raise HTTPException(status_code=404, detail="No documents found for the selected users.")

    zip_buffer.seek(0)
    zip_bytes = zip_buffer.getvalue()
    zip_filename = f"instructors_documents_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"

    return zip_bytes, zip_filename
