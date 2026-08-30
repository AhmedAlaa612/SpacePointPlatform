"""The instructor Curriculum Library's inline PDF viewer (2026-08-27).

A hosted PDF resource's `file_url` used to be embedded directly in the list
response and rendered as a plain `<a href target=_blank>` — a one-click
download of material the org considers copyrighted. Now the list never
carries that URL for a hosted PDF; the frontend resolves it on demand via
`GET /resources/{id}/url` only once someone actually opens the document, the
same posture the LMS attachment viewer already uses for its own signed URL.

Everything that *isn't* a hosted PDF (a PPTX upload, a `link`-type resource
pointing off-site) is unaffected — there's no inline viewer for those, so
hiding their URL would just break them.
"""

import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.instructors.library import LibraryModule, LibraryResource
from app.models.user import User


async def _instructor(db) -> User:
    u = User(
        id=uuid.uuid4(), full_name="Library Test Instructor",
        email=f"lib-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["instructor"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _module(db) -> LibraryModule:
    m = LibraryModule(id=uuid.uuid4(), name=f"Module {uuid.uuid4().hex[:6]}")
    db.add(m)
    await db.flush()
    return m


@pytest.mark.asyncio
async def test_a_hosted_pdf_has_no_url_in_the_list(client, db):
    instructor = await _instructor(db)
    module = await _module(db)
    resource = LibraryResource(
        id=uuid.uuid4(), title="Copyrighted Datasheet", format="PDF", resource_type="file",
        file_url="library-resources/some/path.pdf", module_id=module.id,
    )
    db.add(resource)
    await db.commit()

    resp = await client.get("/instructors/library", headers=_headers(instructor))
    assert resp.status_code == 200
    [listed] = resp.json()[0]["resources"]
    assert listed["file_url"] == ""
    assert listed["format"] == "PDF"


@pytest.mark.asyncio
async def test_a_hosted_non_pdf_still_carries_its_url(client, db):
    """No inline viewer exists for a PPTX — hiding its URL would just make
    it unopenable, so the list keeps resolving it as before."""
    instructor = await _instructor(db)
    module = await _module(db)
    resource = LibraryResource(
        id=uuid.uuid4(), title="Slide Deck", format="PPTX", resource_type="file",
        file_url="library-resources/some/deck.pptx", module_id=module.id,
    )
    db.add(resource)
    await db.commit()

    resp = await client.get("/instructors/library", headers=_headers(instructor))
    [listed] = resp.json()[0]["resources"]
    assert listed["file_url"] != ""


@pytest.mark.asyncio
async def test_a_link_resource_still_carries_its_raw_url(client, db):
    instructor = await _instructor(db)
    module = await _module(db)
    resource = LibraryResource(
        id=uuid.uuid4(), title="External Reference", format="LINK", resource_type="link",
        file_url="https://example.com/reference", module_id=module.id,
    )
    db.add(resource)
    await db.commit()

    resp = await client.get("/instructors/library", headers=_headers(instructor))
    [listed] = resp.json()[0]["resources"]
    assert listed["file_url"] == "https://example.com/reference"


@pytest.mark.asyncio
async def test_resolving_a_hosted_pdfs_url_on_demand(client, db):
    instructor = await _instructor(db)
    module = await _module(db)
    resource = LibraryResource(
        id=uuid.uuid4(), title="Copyrighted Datasheet", format="PDF", resource_type="file",
        file_url="library-resources/some/path.pdf", module_id=module.id,
    )
    db.add(resource)
    await db.commit()

    resp = await client.get(f"/instructors/library/resources/{resource.id}/url", headers=_headers(instructor))
    assert resp.status_code == 200
    assert resp.json()["url"]


@pytest.mark.asyncio
async def test_resolving_a_link_resources_url_returns_the_raw_link(client, db):
    instructor = await _instructor(db)
    module = await _module(db)
    resource = LibraryResource(
        id=uuid.uuid4(), title="External Reference", format="LINK", resource_type="link",
        file_url="https://example.com/reference", module_id=module.id,
    )
    db.add(resource)
    await db.commit()

    resp = await client.get(f"/instructors/library/resources/{resource.id}/url", headers=_headers(instructor))
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://example.com/reference"


@pytest.mark.asyncio
async def test_resolving_an_unknown_resource_is_404(client, db):
    instructor = await _instructor(db)
    resp = await client.get(f"/instructors/library/resources/{uuid.uuid4()}/url", headers=_headers(instructor))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_a_student_cannot_reach_the_instructor_library(client, db):
    student = User(
        id=uuid.uuid4(), full_name="Student", email=f"stu-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["student"], status="active",
    )
    db.add(student)
    await db.commit()

    resp = await client.get("/instructors/library", headers=_headers(student))
    assert resp.status_code == 403
