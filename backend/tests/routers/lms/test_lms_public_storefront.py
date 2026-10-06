"""Tests for the public LMS storefront (/public/courses*, /public/learning-paths*).

Anonymous browsing: published + non-invite content is visible with prices,
drafts and invite-mode content 404, per-user fields degrade to logged-out
values. Enroll/checkout stay behind /lms/* auth (covered elsewhere).
Redis-free (uses the shared `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.models.lms import Course, CourseModule, ModuleItem
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.user import User


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Public Storefront Author",
        email=f"storefront-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=["admin"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _course(db, author, **kw) -> Course:
    course = Course(
        id=uuid.uuid4(),
        title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"),
        created_by=author.id,
        is_published=kw.pop("published", True),
        **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _module(db, course, position=1) -> CourseModule:
    module = CourseModule(
        id=uuid.uuid4(), course_id=course.id, title=f"Module {position}", position=position,
    )
    db.add(module)
    await db.flush()
    return module


async def _item(db, module, position=1) -> ModuleItem:
    item = ModuleItem(
        id=uuid.uuid4(), module_id=module.id, position=position, kind="text",
        title="Reading", content={"body": "hello"},
    )
    db.add(item)
    await db.flush()
    return item


async def _path(db, author, **kw):
    path = LearningPath(
        id=uuid.uuid4(),
        title=kw.pop("title", f"Path {uuid.uuid4().hex[:8]}"),
        created_by=author.id,
        is_published=kw.pop("published", True),
        **kw,
    )
    db.add(path)
    await db.flush()
    return path


async def _step(db, path, course, position=1) -> LearningPathStep:
    step = LearningPathStep(
        id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=position,
    )
    db.add(step)
    await db.flush()
    return step


# ── course list ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_public_courses_lists_published_with_prices(db, client):
    author = await _user(db)
    await _course(db, author, title="Open Course", access_mode="open")
    await _course(
        db, author, title="Paid Course", access_mode="paid",
        price_cents=5000, currency="aed",
    )
    await _course(db, author, title="Draft Course", published=False)
    await _course(db, author, title="Invite Course", access_mode="invite")

    resp = await client.get("/public/courses")
    assert resp.status_code == 200, resp.text
    titles = [c["title"] for c in resp.json()]
    assert "Open Course" in titles
    assert "Paid Course" in titles
    assert "Draft Course" not in titles
    assert "Invite Course" not in titles

    paid = next(c for c in resp.json() if c["title"] == "Paid Course")
    assert paid["price_cents"] == 5000
    assert paid["currency"] == "aed"
    assert paid["enrolled"] is False


@pytest.mark.asyncio
async def test_public_courses_search(db, client):
    author = await _user(db)
    await _course(db, author, title="CubeSat Basics")
    await _course(db, author, title="Drone Flying")

    resp = await client.get("/public/courses", params={"q": "cubesat"})
    assert resp.status_code == 200, resp.text
    assert [c["title"] for c in resp.json()] == ["CubeSat Basics"]


# ── course detail ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_public_course_detail_outline_locked_preview(db, client):
    author = await _user(db)
    course = await _course(
        db, author, title="Preview Course", access_mode="paid",
        price_cents=9900, currency="aed", description="Learn things",
    )
    m1 = await _module(db, course, position=1)
    await _item(db, m1)
    m2 = await _module(db, course, position=2)
    await _item(db, m2)

    resp = await client.get(f"/public/courses/{course.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Preview Course"
    assert body["enrolled"] is False
    assert body["completed"] is False
    assert body["price_cents"] == 9900
    assert [m["position"] for m in body["modules"]] == [1, 2]
    assert body["modules"][0]["locked"] is False
    assert body["modules"][1]["locked"] is True


@pytest.mark.asyncio
async def test_public_course_detail_hides_draft_and_invite(db, client):
    author = await _user(db)
    draft = await _course(db, author, published=False)
    invite = await _course(db, author, access_mode="invite")

    assert (await client.get(f"/public/courses/{draft.id}")).status_code == http_status.HTTP_404_NOT_FOUND
    assert (await client.get(f"/public/courses/{invite.id}")).status_code == http_status.HTTP_404_NOT_FOUND
    assert (await client.get(f"/public/courses/{uuid.uuid4()}")).status_code == http_status.HTTP_404_NOT_FOUND


# ── learning paths ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_public_paths_list_and_detail(db, client):
    author = await _user(db)
    course = await _course(db, author, title="Path Course")
    m1 = await _module(db, course, position=1)
    await _item(db, m1)
    path = await _path(
        db, author, title="Open Path", description="A path",
        price_cents=12000, currency="aed",
    )
    await _step(db, path, course)
    await _path(db, author, title="Hidden Invite Path", access_mode="invite")
    await _path(db, author, title="Hidden Draft Path", published=False)

    resp = await client.get("/public/learning-paths")
    assert resp.status_code == 200, resp.text
    titles = [p["title"] for p in resp.json()]
    assert titles == ["Open Path"]
    assert resp.json()[0]["price_cents"] == 12000
    assert resp.json()[0]["enrolled"] is False

    detail = await client.get(f"/public/learning-paths/{path.id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["title"] == "Open Path"
    assert body["pct"] == 0
    assert body["enrolled"] is False
    assert len(body["steps"]) == 1
    assert body["steps"][0]["state"] == "current"


@pytest.mark.asyncio
async def test_public_path_detail_hides_invite_and_draft(db, client):
    author = await _user(db)
    invite = await _path(db, author, access_mode="invite")
    draft = await _path(db, author, published=False)

    assert (await client.get(f"/public/learning-paths/{invite.id}")).status_code == http_status.HTTP_404_NOT_FOUND
    assert (await client.get(f"/public/learning-paths/{draft.id}")).status_code == http_status.HTTP_404_NOT_FOUND
