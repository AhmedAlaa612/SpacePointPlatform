"""LMS PDF attachments (2026-08-09) — the reader the operator asked for.
Two-step shape like video (create the empty item, then upload the file),
but synchronous: no transcode, no ARQ job, no ModuleVideo-style state table.
Covers both the admin upload leg and the student signed-URL leg (same
enrolled-only posture every other student route has).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.user import User
from app.services.lms import enroll


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="LMS Attachment User",
        email=f"lms-attach-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=list(roles) if roles else ["student"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course_module_item(db, *, author, kind="attachment") -> tuple[Course, CourseModule, ModuleItem]:
    course = Course(id=uuid.uuid4(), title="C", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind=kind, content={})
    db.add(item)
    await db.flush()
    return course, module, item


# ── admin: upload ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_requires_content_role_pdf_content_type_and_an_attachment_item(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    student = await _user(db, roles=["student"])
    denied = await client.post(
        f"/lms/admin/items/{item.id}/attachment", headers=_headers(student),
        files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert denied.status_code == http_status.HTTP_403_FORBIDDEN

    not_pdf = await client.post(
        f"/lms/admin/items/{item.id}/attachment", headers=_headers(ops),
        files={"file": ("doc.txt", b"not a pdf", "text/plain")},
    )
    assert not_pdf.status_code == http_status.HTTP_400_BAD_REQUEST

    text_item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=2, kind="text", content={"body": "x"})
    db.add(text_item)
    await db.commit()
    wrong_kind = await client.post(
        f"/lms/admin/items/{text_item.id}/attachment", headers=_headers(ops),
        files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert wrong_kind.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_upload_rejects_oversized_pdf(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    too_big = b"x" * (25 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/lms/admin/items/{item.id}/attachment", headers=_headers(ops),
        files={"file": ("big.pdf", too_big, "application/pdf")},
    )
    assert resp.status_code == http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


@pytest.mark.asyncio
async def test_upload_stores_file_reference_on_the_item(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/items/{item.id}/attachment", headers=_headers(ops),
        files={"file": ("Syllabus.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content"]["filename"] == "Syllabus.pdf"
    assert body["content"]["bucket"] == "lms-attachments"
    assert body["content"]["size_bytes"] == len(b"%PDF-1.4 fake bytes")


# ── student: signed URL ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_attachment_url_requires_enrollment_a_real_kind_and_an_uploaded_file(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    student = await _user(db)
    # not enrolled -> 404
    not_enrolled = await client.get(f"/lms/items/{item.id}/attachment/url", headers=_headers(student))
    assert not_enrolled.status_code == http_status.HTTP_404_NOT_FOUND

    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    # enrolled, but nothing uploaded yet -> 404
    no_file = await client.get(f"/lms/items/{item.id}/attachment/url", headers=_headers(student))
    assert no_file.status_code == http_status.HTTP_404_NOT_FOUND

    # wrong kind -> 404 (a different, enrolled course so it's genuinely the
    # kind check failing, not enrollment)
    video_course, _, video_item = await _course_module_item(db, author=ops, kind="video")
    await enroll(db, user_id=student.id, course_id=video_course.id)
    await db.commit()
    wrong_kind = await client.get(f"/lms/items/{video_item.id}/attachment/url", headers=_headers(student))
    assert wrong_kind.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_attachment_url_resolves_once_uploaded(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    upload = await client.post(
        f"/lms/admin/items/{item.id}/attachment", headers=_headers(ops),
        files={"file": ("notes.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text

    student = await _user(db)
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    resp = await client.get(f"/lms/items/{item.id}/attachment/url", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filename"] == "notes.pdf"
    assert "/files/lms-attachments/" in body["url"]


# ── leak posture: student_view never exposes bucket/path ────────────────────

@pytest.mark.asyncio
async def test_module_read_hides_storage_details_for_attachments(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    item.content = {"bucket": "lms-attachments", "path": "secret/path.pdf", "filename": "notes.pdf", "size_bytes": 42}
    await db.commit()

    student = await _user(db)
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    resp = await client.get(f"/lms/modules/{module.id}", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    item_out = next(i for i in resp.json()["items"] if i["id"] == str(item.id))
    assert item_out["content"] == {"filename": "notes.pdf", "size_bytes": 42}
