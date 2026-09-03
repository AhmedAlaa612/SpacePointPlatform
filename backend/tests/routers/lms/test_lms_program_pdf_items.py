"""LMS Program 'pdf' checklist steps (2026-08-31) — replaces the old
'article' (link-only) type with an uploaded, no-download-viewer PDF, same
two-step create-then-upload shape as a module attachment. Covers the admin
upload/replace/remove/resolve legs, the student resolve leg, and that
forking a cohort override duplicates the file rather than sharing it.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program, fork_cohort_override


async def _staff(db, *, roles=("operations",)) -> User:
    user = User(
        id=uuid.uuid4(), full_name="PDF Item Staff", email=f"pdf-staff-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles), status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name="PDF Item Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name="PDF Item Student", email=f"pdf-stu-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _program_cohort_and_item(db, *, author):
    program_row = Program(
        id=uuid.uuid4(), code=f"PDF-{uuid.uuid4().hex[:8]}", name="PDF Item Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program_row)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program_row.id, name="PDF Item Cohort", status="running")
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program_row.id, name="PDF Checklist")
    db.add(lms_program)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="pdf", title="Read the handbook",
    )
    db.add(item)
    await db.flush()
    return lms_program, cohort, item


# ── admin: upload / replace / remove / resolve ──────────────────────────────

@pytest.mark.asyncio
async def test_upload_requires_content_role_pdf_content_type_and_a_pdf_item(db, client):
    ops = await _staff(db)
    _, _, item = await _program_cohort_and_item(db, author=ops)
    await db.commit()

    student = await _student(db)
    denied = await client.post(
        f"/lms/admin/items/{item.id}/pdf", headers=_headers(student),
        files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert denied.status_code == http_status.HTTP_403_FORBIDDEN

    not_pdf = await client.post(
        f"/lms/admin/items/{item.id}/pdf", headers=_headers(ops),
        files={"file": ("doc.txt", b"not a pdf", "text/plain")},
    )
    assert not_pdf.status_code == http_status.HTTP_400_BAD_REQUEST

    link_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type=item.owner_type, owner_id=item.owner_id, position=2,
        item_type="external_link", title="Elsewhere", external_url="https://example.com",
    )
    db.add(link_item)
    await db.commit()
    wrong_type = await client.post(
        f"/lms/admin/items/{link_item.id}/pdf", headers=_headers(ops),
        files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert wrong_type.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_upload_then_replace_then_remove(db, client):
    ops = await _staff(db)
    _, _, item = await _program_cohort_and_item(db, author=ops)
    await db.commit()

    upload = await client.post(
        f"/lms/admin/items/{item.id}/pdf", headers=_headers(ops),
        files={"file": ("Handbook.pdf", b"%PDF-1.4 v1", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["has_pdf"] is True

    resolved = await client.get(f"/lms/admin/items/{item.id}/pdf-url", headers=_headers(ops))
    assert resolved.status_code == 200, resolved.text
    assert "url" in resolved.json()

    replaced = await client.post(
        f"/lms/admin/items/{item.id}/pdf", headers=_headers(ops),
        files={"file": ("Handbook-v2.pdf", b"%PDF-1.4 v2", "application/pdf")},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["has_pdf"] is True

    removed = await client.delete(f"/lms/admin/items/{item.id}/pdf", headers=_headers(ops))
    assert removed.status_code == 200, removed.text
    assert removed.json()["has_pdf"] is False

    gone = await client.get(f"/lms/admin/items/{item.id}/pdf-url", headers=_headers(ops))
    assert gone.status_code == http_status.HTTP_404_NOT_FOUND


# ── Roadmap board (2026-09) — a pdf-kind guideline on a non-pdf item ────────

@pytest.mark.asyncio
async def test_pdf_upload_and_resolve_works_for_a_pdf_guideline_on_any_item_type(db, client):
    """A `manual`/`submission`/`mission_run`/etc. item can carry a `pdf`
    guideline (Roadmap board task drawer's "view the guideline" step) —
    same file, same upload/resolve endpoints as a real `pdf`-type item,
    gated on `guideline_kind == 'pdf'` instead of `item_type == 'pdf'`."""
    ops = await _staff(db)
    lms_program, cohort, _pdf_item = await _program_cohort_and_item(db, author=ops)
    guideline_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="manual", title="Do the thing", guideline_kind="pdf",
    )
    db.add(guideline_item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    upload = await client.post(
        f"/lms/admin/items/{guideline_item.id}/pdf", headers=_headers(ops),
        files={"file": ("guide.pdf", b"%PDF-1.4 guide", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["has_pdf"] is True

    admin_resolved = await client.get(f"/lms/admin/items/{guideline_item.id}/pdf-url", headers=_headers(ops))
    assert admin_resolved.status_code == 200, admin_resolved.text

    student_resolved = await client.get(
        f"/lms/programs/{assignment.id}/items/{guideline_item.id}/pdf-url", headers=_headers(student),
    )
    assert student_resolved.status_code == 200, student_resolved.text
    assert "url" in student_resolved.json()

    removed = await client.delete(f"/lms/admin/items/{guideline_item.id}/pdf", headers=_headers(ops))
    assert removed.status_code == 200 and removed.json()["has_pdf"] is False


# ── student: resolve ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_student_pdf_url_requires_ownership_and_an_uploaded_file(db, client):
    ops = await _staff(db)
    _, cohort, item = await _program_cohort_and_item(db, author=ops)
    await db.commit()

    student = await _student(db)
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    assert assignment is not None

    # nothing uploaded yet -> 404
    no_file = await client.get(
        f"/lms/programs/{assignment.id}/items/{item.id}/pdf-url", headers=_headers(student),
    )
    assert no_file.status_code == http_status.HTTP_404_NOT_FOUND

    upload = await client.post(
        f"/lms/admin/items/{item.id}/pdf", headers=_headers(ops),
        files={"file": ("handbook.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text

    resolved = await client.get(
        f"/lms/programs/{assignment.id}/items/{item.id}/pdf-url", headers=_headers(student),
    )
    assert resolved.status_code == 200, resolved.text
    assert "url" in resolved.json()

    # a different student's own assignment_id doesn't exist -> 404, never
    # someone else's document by guessing an item_id under a real assignment
    other_student = await _student(db)
    not_owner = await client.get(
        f"/lms/programs/{assignment.id}/items/{item.id}/pdf-url", headers=_headers(other_student),
    )
    assert not_owner.status_code == http_status.HTTP_404_NOT_FOUND


# ── fork: independent storage, not a shared reference ───────────────────────

@pytest.mark.asyncio
async def test_fork_cohort_override_duplicates_the_pdf_file(db, client):
    ops = await _staff(db)
    _, cohort, item = await _program_cohort_and_item(db, author=ops)
    await db.commit()

    upload = await client.post(
        f"/lms/admin/items/{item.id}/pdf", headers=_headers(ops),
        files={"file": ("handbook.pdf", b"%PDF-1.4 original", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text

    forked = await fork_cohort_override(db, cohort_id=cohort.id)
    assert forked is not None
    override, id_map = forked
    await db.commit()

    forked_item_id = id_map[item.id]
    forked_item = await db.get(LmsProgramItem, forked_item_id)
    original_item = await db.get(LmsProgramItem, item.id)
    assert forked_item.pdf_path is not None
    assert original_item.pdf_path is not None
    assert forked_item.pdf_path != original_item.pdf_path

    # Deleting the fork's PDF must not touch the program's original.
    removed = await client.delete(f"/lms/admin/items/{forked_item.id}/pdf", headers=_headers(ops))
    assert removed.status_code == 200, removed.text
    assert removed.json()["has_pdf"] is False

    still_there = await client.get(f"/lms/admin/items/{item.id}/pdf-url", headers=_headers(ops))
    assert still_there.status_code == 200, still_there.text
