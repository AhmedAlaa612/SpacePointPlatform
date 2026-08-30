"""The design component library's own datasheet upload (2026-08-27).

Most of the 36 real components were seeded pointing `datasheet_url` at a
Google Drive share or a manufacturer's own site — files SpacePoint doesn't
host and can't make "not downloadable" no matter what the frontend does.
This is the actual fix: upload the org's own copy once, and it's served
through the same no-download viewer the LMS/instructor-library attachments
use, resolved on demand rather than embedded in any list payload.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.design import DesignComponentLibrary
from app.models.user import User


async def _user(db, *roles: str) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Design Library User",
        email=f"design-lib-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash", roles=list(roles) or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _component(db, **kw) -> DesignComponentLibrary:
    row = DesignComponentLibrary(
        id=uuid.uuid4(), component_name=f"Part {uuid.uuid4().hex[:6]}", subsystem="ADCS", **kw,
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.asyncio
async def test_ops_can_upload_a_datasheet_and_it_supersedes_the_link(client, db):
    ops = await _user(db, "operations")
    component = await _component(db, datasheet_url="https://drive.google.com/file/d/abc/view")
    await db.commit()

    resp = await client.post(
        f"/missions/library/{component.id}/datasheet",
        headers=_headers(ops),
        files={"file": ("ds.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["has_datasheet_file"] is True
    assert body["datasheet_url"] is None, "an uploaded file supersedes the pasted link"


@pytest.mark.asyncio
async def test_a_non_pdf_is_rejected(client, db):
    ops = await _user(db, "operations")
    component = await _component(db)
    await db.commit()

    resp = await client.post(
        f"/missions/library/{component.id}/datasheet",
        headers=_headers(ops),
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_a_plain_student_cannot_upload_a_datasheet(client, db):
    student = await _user(db, "student")
    component = await _component(db)
    await db.commit()

    resp = await client.post(
        f"/missions/library/{component.id}/datasheet",
        headers=_headers(student),
        files={"file": ("ds.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_the_student_facing_list_never_carries_an_uploaded_datasheets_url(client, db):
    ops = await _user(db, "operations")
    student = await _user(db, "student")
    component = await _component(db)
    await db.commit()

    upload = await client.post(
        f"/missions/library/{component.id}/datasheet",
        headers=_headers(ops),
        files={"file": ("ds.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert upload.status_code == 200

    listed = await client.get("/missions/design/library", headers=_headers(student))
    assert listed.status_code == 200
    [row] = [r for r in listed.json() if r["id"] == str(component.id)]
    assert row["has_datasheet_file"] is True
    assert row["datasheet_url"] is None


@pytest.mark.asyncio
async def test_a_student_can_resolve_an_uploaded_datasheets_url_on_demand(client, db):
    ops = await _user(db, "operations")
    student = await _user(db, "student")
    component = await _component(db)
    await db.commit()

    upload = await client.post(
        f"/missions/library/{component.id}/datasheet",
        headers=_headers(ops),
        files={"file": ("ds.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert upload.status_code == 200

    resolved = await client.get(f"/missions/design/library/{component.id}/datasheet-url", headers=_headers(student))
    assert resolved.status_code == 200
    assert resolved.json()["url"]


@pytest.mark.asyncio
async def test_resolving_a_component_with_no_uploaded_file_is_a_404(client, db):
    student = await _user(db, "student")
    component = await _component(db, datasheet_url="https://drive.google.com/file/d/abc/view")
    await db.commit()

    resolved = await client.get(f"/missions/design/library/{component.id}/datasheet-url", headers=_headers(student))
    assert resolved.status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_datasheet_clears_it(client, db):
    ops = await _user(db, "operations")
    component = await _component(db)
    await db.commit()

    upload = await client.post(
        f"/missions/library/{component.id}/datasheet",
        headers=_headers(ops),
        files={"file": ("ds.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert upload.status_code == 200

    deleted = await client.delete(f"/missions/library/{component.id}/datasheet", headers=_headers(ops))
    assert deleted.status_code == 200
    assert deleted.json()["has_datasheet_file"] is False

    resolved = await client.get(f"/missions/design/library/{component.id}/datasheet-url", headers=_headers(ops))
    assert resolved.status_code == 404
