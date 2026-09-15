"""Learning paths (LMS redesign, 2026-08-08) — self-paced ordered course
sequences. Covers: admin CRUD + step ordering (mirrors program_curriculum's
own test shape), the student catalog/detail 404-on-unpublished rule, "start"
bulk-enrolling every step's course, and the path_progress state rollup
(done/current/mission/locked) at the service layer.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, Enrollment, ModuleItem
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.user import User
from app.services.lms import enroll, item_progress, path_progress


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="LMS Path User",
        email=f"lms-path-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course(db, *, author, published=True, kind="course", **kw) -> Course:
    course = Course(
        id=uuid.uuid4(), title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"),
        created_by=author.id, is_published=published, kind=kind, **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _path(db, *, author, published=True, **kw) -> LearningPath:
    path = LearningPath(
        id=uuid.uuid4(), title=f"Path {uuid.uuid4().hex[:8]}", created_by=author.id, is_published=published,
        **kw,
    )
    db.add(path)
    await db.flush()
    return path


async def _course_with_one_module_one_item(db, *, author) -> tuple[Course, ModuleItem]:
    course = await _course(db, author=author)
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text", content={"body": "x"})
    db.add(item)
    await db.flush()
    return course, item


# ── admin CRUD + step ordering ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_learning_path_crud_and_publish(db, client):
    ops = await _user(db)
    await db.commit()

    create = await client.post(
        "/lms/admin/learning-paths", headers=_headers(ops),
        json={"title": "Space Science Foundations", "description": "Eight steps"},
    )
    assert create.status_code == 201
    path_id = create.json()["id"]
    assert create.json()["is_published"] is False

    published = await client.patch(
        f"/lms/admin/learning-paths/{path_id}", headers=_headers(ops), json={"is_published": True},
    )
    assert published.status_code == 200 and published.json()["is_published"] is True

    listed = await client.get("/lms/admin/learning-paths", headers=_headers(ops))
    assert any(p["id"] == path_id for p in listed.json())

    deleted = await client.delete(f"/lms/admin/learning-paths/{path_id}", headers=_headers(ops))
    assert deleted.status_code == 204
    missing = await client.get(f"/lms/admin/learning-paths/{path_id}", headers=_headers(ops))
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_admin_learning_path_bundle_pricing(db, client):
    """Bundle pricing (2026-08-21) — price_cents null by default (not
    purchasable), settable and clearable via PATCH, free-form (no enforced
    relationship to the sum of step prices, operator decision)."""
    ops = await _user(db)
    await db.commit()

    create = await client.post(
        "/lms/admin/learning-paths", headers=_headers(ops),
        json={"title": "Bundle Path"},
    )
    assert create.status_code == 201
    assert create.json()["price_cents"] is None
    assert create.json()["currency"] == "usd"
    path_id = create.json()["id"]

    priced = await client.patch(
        f"/lms/admin/learning-paths/{path_id}", headers=_headers(ops), json={"price_cents": 9900},
    )
    assert priced.status_code == 200
    assert priced.json()["price_cents"] == 9900

    cleared = await client.patch(
        f"/lms/admin/learning-paths/{path_id}", headers=_headers(ops), json={"price_cents": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["price_cents"] is None


@pytest.mark.asyncio
async def test_admin_learning_path_step_binding_add_list_remove(db, client):
    ops = await _user(db)
    path = await _path(db, author=ops)
    course_a = await _course(db, author=ops, title="A")
    course_b = await _course(db, author=ops, title="B")
    await db.commit()

    add_a = await client.post(
        f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops),
        json={"course_id": str(course_a.id)},
    )
    assert add_a.status_code == 201 and add_a.json()["position"] == 1

    add_b = await client.post(
        f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops),
        json={"course_id": str(course_b.id)},
    )
    assert add_b.status_code == 201 and add_b.json()["position"] == 2

    dup = await client.post(
        f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops),
        json={"course_id": str(course_a.id)},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT

    taken_position = await client.post(
        f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops),
        json={"course_id": str(course_a.id), "position": 1},
    )
    assert taken_position.status_code == http_status.HTTP_409_CONFLICT

    listed = await client.get(f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops))
    assert [s["course_id"] for s in listed.json()] == [str(course_a.id), str(course_b.id)]

    removed = await client.delete(
        f"/lms/admin/learning-paths/{path.id}/steps/{course_a.id}", headers=_headers(ops)
    )
    assert removed.status_code == 204
    remaining = (await db.execute(
        select(LearningPathStep).where(LearningPathStep.learning_path_id == path.id)
    )).scalars().all()
    assert len(remaining) == 1 and remaining[0].course_id == course_b.id


# ── student catalog / detail ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unpublished_path_404s_for_students(db, client):
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops, published=False)
    await db.commit()

    resp = await client.get(f"/lms/learning-paths/{path.id}", headers=_headers(student))
    assert resp.status_code == 404

    catalog = await client.get("/lms/learning-paths", headers=_headers(student))
    assert all(p["id"] != str(path.id) for p in catalog.json())


@pytest.mark.asyncio
async def test_start_path_bulk_enrolls_every_step_course(db, client):
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops)
    course_a, _item_a = await _course_with_one_module_one_item(db, author=ops)
    course_b, _item_b = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_a.id, position=1))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_b.id, position=2))
    await db.commit()

    resp = await client.post(f"/lms/learning-paths/{path.id}/start", headers=_headers(student))
    assert resp.status_code == 200
    body = resp.json()
    assert body["course_count"] == 2
    assert {s["course_id"] for s in body["steps"]} == {str(course_a.id), str(course_b.id)}

    enrollments = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id)
    )).scalars().all()
    assert {e.course_id for e in enrollments} == {course_a.id, course_b.id}
    assert all(e.status == "active" and e.source == "self" for e in enrollments)

    # idempotent — calling start again doesn't duplicate or error
    again = await client.post(f"/lms/learning-paths/{path.id}/start", headers=_headers(student))
    assert again.status_code == 200
    enrollments_again = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id)
    )).scalars().all()
    assert len(enrollments_again) == 2


@pytest.mark.asyncio
async def test_path_detail_and_catalog_expose_price_and_ownership(db, client):
    """Bundle pricing (2026-08-21) — `fully_owned` flips true only once every
    step's course has an active enrollment; a partial owner still sees it
    false (nothing blocks the buy button until *everything* is owned)."""
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops)
    path.price_cents = 4900
    course_a, _ = await _course_with_one_module_one_item(db, author=ops)
    course_b, _ = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_a.id, position=1))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_b.id, position=2))
    await db.commit()

    detail = await client.get(f"/lms/learning-paths/{path.id}", headers=_headers(student))
    assert detail.json()["price_cents"] == 4900
    assert detail.json()["fully_owned"] is False
    assert detail.json()["access_mode"] == "open"
    assert detail.json()["enrolled"] is False

    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course_a.id, source="ops", status="active"))
    await db.commit()
    partial = await client.get(f"/lms/learning-paths/{path.id}", headers=_headers(student))
    assert partial.json()["fully_owned"] is False
    assert partial.json()["enrolled"] is True

    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course_b.id, source="ops", status="active"))
    await db.commit()
    full = await client.get(f"/lms/learning-paths/{path.id}", headers=_headers(student))
    assert full.json()["fully_owned"] is True

    catalog = await client.get("/lms/learning-paths", headers=_headers(student))
    row = next(p for p in catalog.json() if p["id"] == str(path.id))
    assert row["price_cents"] == 4900 and row["fully_owned"] is True


@pytest.mark.asyncio
async def test_start_path_skips_invite_and_paid_steps(db, client):
    """P1-6: this bulk self-enrol is a shortcut for POST /lms/enroll and must
    respect the same access_mode gate (P1-4) — an invite-only or paid step
    inside a path can't be silently unlocked by starting the path."""
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops)
    open_course, _ = await _course_with_one_module_one_item(db, author=ops)
    invite_course, _ = await _course_with_one_module_one_item(db, author=ops)
    invite_course.access_mode = "invite"
    paid_course, _ = await _course_with_one_module_one_item(db, author=ops)
    paid_course.access_mode = "paid"
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=open_course.id, position=1))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=invite_course.id, position=2))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=paid_course.id, position=3))
    await db.commit()

    resp = await client.post(f"/lms/learning-paths/{path.id}/start", headers=_headers(student))
    assert resp.status_code == 200

    enrollments = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id)
    )).scalars().all()
    assert {e.course_id for e in enrollments} == {open_course.id}


# ── invite-mode paths (2026-09-01) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog_hides_invite_paths_for_non_enrolled_caller(db, client):
    """Invite paths are fully hidden from the catalog for anyone without an
    active enrollment in a step course — they only appear once assigned."""
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops, access_mode="invite")
    course, _item = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await db.commit()

    resp = await client.get("/lms/learning-paths", headers=_headers(student))
    assert resp.status_code == 200
    assert all(p["id"] != str(path.id) for p in resp.json())

    await enroll(db, user_id=student.id, course_id=course.id, source="ops")
    await db.commit()

    resp2 = await client.get("/lms/learning-paths", headers=_headers(student))
    row = next(p for p in resp2.json() if p["id"] == str(path.id))
    assert row["access_mode"] == "invite"
    assert row["enrolled"] is True


@pytest.mark.asyncio
async def test_invite_path_detail_404s_for_non_enrolled_caller(db, client):
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops, access_mode="invite")
    course, _item = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await db.commit()

    resp = await client.get(f"/lms/learning-paths/{path.id}", headers=_headers(student))
    assert resp.status_code == 404

    await enroll(db, user_id=student.id, course_id=course.id, source="ops")
    await db.commit()

    resp2 = await client.get(f"/lms/learning-paths/{path.id}", headers=_headers(student))
    assert resp2.status_code == 200
    assert resp2.json()["access_mode"] == "invite"
    assert resp2.json()["enrolled"] is True


@pytest.mark.asyncio
async def test_start_path_rejects_invite_access_mode(db, client):
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops, access_mode="invite")
    course, _item = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await db.commit()

    # not enrolled — detail is 404, so /start on it is unreachable/404 too
    resp = await client.post(f"/lms/learning-paths/{path.id}/start", headers=_headers(student))
    assert resp.status_code == 404

    # even once granted, self-`/start` still refuses an invite-mode path —
    # the grant is what gives access, not a switch to self-service
    await enroll(db, user_id=student.id, course_id=course.id, source="ops")
    await db.commit()
    resp2 = await client.post(f"/lms/learning-paths/{path.id}/start", headers=_headers(student))
    assert resp2.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_start_path_rejects_paid_access_mode(db, client):
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops, access_mode="paid")
    course, _item = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await db.commit()

    resp = await client.post(f"/lms/learning-paths/{path.id}/start", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_402_PAYMENT_REQUIRED

    enrollments = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id)
    )).scalars().all()
    assert enrollments == []


@pytest.mark.asyncio
async def test_admin_grant_enrolls_into_invite_path_regardless_of_access_mode(db, client):
    """access_mode only gates self-`/start` — an ops bulk grant is always
    allowed, same posture as the course-level equivalent."""
    ops = await _user(db)
    path = await _path(db, author=ops, access_mode="invite")
    course_a, _ = await _course_with_one_module_one_item(db, author=ops)
    course_b, _ = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_a.id, position=1))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_b.id, position=2))
    facilitator = await _user(db, roles=["facilitator"])
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments/bulk", headers=_headers(ops),
        json={"role": "facilitator"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted"] == 1

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == facilitator.id)
    )).scalars().all()
    assert {r.course_id for r in rows} == {course_a.id, course_b.id}


# ── named-individual grant/roster/revoke (2026-09-15) ───────────────────────
# The path equivalent of grant_enrollment/course_roster/revoke_enrollment —
# courses have had a "put this specific staff account in" surface since
# P1-5; paths only had the cohort/role bulk grant until now.

@pytest.mark.asyncio
async def test_path_grant_enrolls_every_step_and_appears_on_the_roster(db, client):
    ops = await _user(db)
    staff = await _user(db, roles=["facilitator"])
    path = await _path(db, author=ops)
    course_a, _ = await _course_with_one_module_one_item(db, author=ops)
    course_b, _ = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_a.id, position=1))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_b.id, position=2))
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments", headers=_headers(ops),
        json={"user_id": str(staff.id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_id"] == str(staff.id)
    assert body["steps_owned"] == 2 and body["steps_total"] == 2

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == staff.id, Enrollment.source == "ops")
    )).scalars().all()
    assert {r.course_id for r in rows} == {course_a.id, course_b.id}

    roster = await client.get(f"/lms/admin/learning-paths/{path.id}/roster", headers=_headers(ops))
    assert roster.status_code == 200, roster.text
    row = next(r for r in roster.json() if r["user_id"] == str(staff.id))
    assert row["steps_owned"] == 2 and row["steps_total"] == 2
    assert row["status"] == "active"


@pytest.mark.asyncio
async def test_path_grant_works_on_an_invite_only_path(db, client):
    """access_mode only gates self-`/start` (P1-4 posture) — a named-
    individual grant is always allowed, same as the course version."""
    ops = await _user(db)
    staff = await _user(db, roles=["facilitator"])
    path = await _path(db, author=ops, access_mode="invite")
    course, _ = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments", headers=_headers(ops),
        json={"user_id": str(staff.id)},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_path_grant_404s_for_unknown_user(db, client):
    ops = await _user(db)
    path = await _path(db, author=ops)
    course, _ = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments", headers=_headers(ops),
        json={"user_id": str(uuid.uuid4())},
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_path_grant_404s_for_a_path_with_no_steps_yet(db, client):
    ops = await _user(db)
    staff = await _user(db, roles=["facilitator"])
    path = await _path(db, author=ops)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments", headers=_headers(ops),
        json={"user_id": str(staff.id)},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_path_roster_only_counts_ops_sourced_enrollments(db, client):
    """A student who self-enrolled in one of the path's courses on their own
    must not show up on the ops assignment roster — same "named-individual
    surface, not self-enrol" rule search_staff enforces on the picker side."""
    ops = await _user(db)
    self_enrolled = await _user(db, roles=["student"])
    path = await _path(db, author=ops)
    course, _ = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await db.flush()
    await enroll(db, user_id=self_enrolled.id, course_id=course.id, source="self")
    await db.commit()

    resp = await client.get(f"/lms/admin/learning-paths/{path.id}/roster", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


@pytest.mark.asyncio
async def test_path_roster_reports_partial_ownership(db, client):
    ops = await _user(db)
    staff = await _user(db, roles=["facilitator"])
    path = await _path(db, author=ops)
    course_a, _ = await _course_with_one_module_one_item(db, author=ops)
    course_b, _ = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_a.id, position=1))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_b.id, position=2))
    await db.flush()
    await enroll(db, user_id=staff.id, course_id=course_a.id, source="ops", granted_by=ops.id)
    await db.commit()

    resp = await client.get(f"/lms/admin/learning-paths/{path.id}/roster", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["user_id"] == str(staff.id))
    assert row["steps_owned"] == 1 and row["steps_total"] == 2


@pytest.mark.asyncio
async def test_path_revoke_deactivates_every_step_and_drops_off_the_roster(db, client):
    ops = await _user(db)
    staff = await _user(db, roles=["facilitator"])
    path = await _path(db, author=ops)
    course_a, _ = await _course_with_one_module_one_item(db, author=ops)
    course_b, _ = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_a.id, position=1))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_b.id, position=2))
    await db.commit()

    grant = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments", headers=_headers(ops),
        json={"user_id": str(staff.id)},
    )
    assert grant.status_code == 201, grant.text

    revoke = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments/{staff.id}/revoke", headers=_headers(ops),
    )
    assert revoke.status_code == http_status.HTTP_204_NO_CONTENT

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == staff.id, Enrollment.source == "ops")
    )).scalars().all()
    assert rows and all(r.status == "inactive" for r in rows), "rows survive, just deactivated"

    roster = await client.get(f"/lms/admin/learning-paths/{path.id}/roster", headers=_headers(ops))
    assert roster.json() == []


# ── path_progress state rollup (service layer) ──────────────────────────────

@pytest.mark.asyncio
async def test_path_progress_state_rollup_done_current_mission_locked(db):
    ops = await _user(db)
    student = await _user(db, roles=["student"])

    done_course, done_item = await _course_with_one_module_one_item(db, author=ops)
    current_course, _current_item = await _course_with_one_module_one_item(db, author=ops)
    mission_course = await _course(db, author=ops, kind="mission")
    locked_course, _locked_item = await _course_with_one_module_one_item(db, author=ops)
    path = await _path(db, author=ops)
    steps = [
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=done_course.id, position=1),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=current_course.id, position=2),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=mission_course.id, position=3),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=locked_course.id, position=4),
    ]
    db.add_all(steps)
    await db.commit()

    await enroll(db, user_id=student.id, course_id=done_course.id)
    await enroll(db, user_id=student.id, course_id=current_course.id)
    await enroll(db, user_id=student.id, course_id=locked_course.id)
    await item_progress(db, user_id=student.id, item_id=done_item.id, action="text-viewed")
    await db.commit()

    result = await path_progress(db, user_id=student.id, steps=steps)
    states = {row["course_id"]: row["state"] for row in result["steps"]}
    assert states[done_course.id] == "done"
    assert states[current_course.id] == "current"
    assert states[mission_course.id] == "mission"
    assert states[locked_course.id] == "locked"
    # mission step never counts toward course_count / pct denominator
    assert result["course_count"] == 3
    assert result["mission_count"] == 1
    assert result["pct"] == 33  # 1 of 3 course-kind steps fully done


# ── catalog `enrolled` flag (2026-08-12) ────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog_enrolled_flag_splits_your_paths_from_the_rest(db, client):
    """The landing page's "your paths" vs "explore" split keys on this. It
    must be true for a path the student has only *started* (0% progress),
    which is exactly the case `pct` alone can't distinguish."""
    ops = await _user(db)
    student = await _user(db, roles=["student"])

    mine, mine_item = await _course_with_one_module_one_item(db, author=ops)
    theirs = await _course(db, author=ops)

    my_path = await _path(db, author=ops)
    other_path = await _path(db, author=ops)
    db.add_all([
        LearningPathStep(id=uuid.uuid4(), learning_path_id=my_path.id, course_id=mine.id, position=1),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=other_path.id, course_id=theirs.id, position=1),
    ])
    await db.flush()

    # Enrolled but zero progress — still "mine".
    await enroll(db, user_id=student.id, course_id=mine.id)
    await db.commit()

    resp = await client.get("/lms/learning-paths", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    by_id = {row["id"]: row for row in resp.json()}

    assert by_id[str(my_path.id)]["enrolled"] is True
    assert by_id[str(my_path.id)]["pct"] == 0, "the 0%-but-enrolled case is the point of this flag"
    assert by_id[str(other_path.id)]["enrolled"] is False


@pytest.mark.asyncio
async def test_catalog_enrolled_flag_is_false_once_access_is_revoked(db, client):
    """Uses the same active-enrollment predicate as every other access
    check, so a revoked enrollment drops the path out of "yours"."""
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    course = await _course(db, author=ops)
    path = await _path(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await db.flush()

    enrollment = await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    resp = await client.get("/lms/learning-paths", headers=_headers(student))
    assert next(r for r in resp.json() if r["id"] == str(path.id))["enrolled"] is True

    enrollment.status = "inactive"
    await db.commit()

    resp = await client.get("/lms/learning-paths", headers=_headers(student))
    assert next(r for r in resp.json() if r["id"] == str(path.id))["enrolled"] is False
