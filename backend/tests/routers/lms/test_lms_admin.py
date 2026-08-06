"""LM1-5 router tests — the `/lms/admin/*` authoring surface.

Covers: role guard (operations/facilitator pass, student/instructor don't),
courses/modules/items CRUD with position auto-append and conflict handling,
the delete-course-with-enrollments guard, per-kind content validation
(including the mid-video-quiz-needs-exactly-one-video rule), and
program_curriculum binding. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, Enrollment, ModuleItem, ModuleVideo, ProgramCurriculum
from app.models.sessions.program import Program
from app.models.user import User
from app.services.lms import enroll
from app.services.lms.video import EncodeResult, run_transcode
from app.services import storage


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="LMS Admin User",
        email=f"lms-admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=list(roles) if roles else ["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course(db, *, author, published=False, **kw) -> Course:
    course = Course(
        id=uuid.uuid4(), title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"),
        created_by=author.id, is_published=published, **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _program(db) -> Program:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    return program


# ── role guard ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_routes_require_content_role(db, client):
    ops = await _user(db, roles=["operations"])
    facilitator = await _user(db, roles=["facilitator"])
    student = await _user(db, roles=["student"])
    instructor = await _user(db, roles=["instructor"])

    for user, ok in [(ops, True), (facilitator, True), (student, False), (instructor, False)]:
        resp = await client.get("/lms/admin/courses", headers=_headers(user))
        assert resp.status_code == (200 if ok else http_status.HTTP_403_FORBIDDEN)

    no_auth = await client.get("/lms/admin/courses")
    assert no_auth.status_code == http_status.HTTP_401_UNAUTHORIZED


# ── courses ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_course_crud_and_publish_cycle(db, client):
    ops = await _user(db)
    create = await client.post(
        "/lms/admin/courses", headers=_headers(ops),
        json={"title": "CubeSat Basics", "description": "intro", "kind": "course"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["is_published"] is False
    course_id = body["id"]

    listed = await client.get("/lms/admin/courses", headers=_headers(ops))
    assert any(c["id"] == course_id for c in listed.json())

    published = await client.post(f"/lms/admin/courses/{course_id}/publish", headers=_headers(ops))
    assert published.status_code == 200 and published.json()["is_published"] is True

    unpublished = await client.post(f"/lms/admin/courses/{course_id}/unpublish", headers=_headers(ops))
    assert unpublished.status_code == 200 and unpublished.json()["is_published"] is False

    updated = await client.patch(
        f"/lms/admin/courses/{course_id}", headers=_headers(ops), json={"title": "CubeSat 101"}
    )
    assert updated.status_code == 200 and updated.json()["title"] == "CubeSat 101"


@pytest.mark.asyncio
async def test_delete_course_refuses_with_enrollments_but_allows_when_empty(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops, published=True)
    student = await _user(db, roles=["student"])
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    blocked = await client.delete(f"/lms/admin/courses/{course.id}", headers=_headers(ops))
    assert blocked.status_code == http_status.HTTP_409_CONFLICT

    empty_course = await _course(db, author=ops, published=False)
    await db.commit()
    ok = await client.delete(f"/lms/admin/courses/{empty_course.id}", headers=_headers(ops))
    assert ok.status_code == http_status.HTTP_204_NO_CONTENT
    assert await db.get(Course, empty_course.id) is None


@pytest.mark.asyncio
async def test_get_and_update_unknown_course_404s(db, client):
    ops = await _user(db)
    missing = uuid.uuid4()
    resp = await client.get(f"/lms/admin/courses/{missing}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND
    resp = await client.patch(f"/lms/admin/courses/{missing}", headers=_headers(ops), json={"title": "x"})
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


# ── modules ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_module_create_auto_appends_position_and_rejects_conflicts(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    await db.commit()

    m1 = await client.post(f"/lms/admin/courses/{course.id}/modules", headers=_headers(ops), json={"title": "M1"})
    assert m1.status_code == 201 and m1.json()["position"] == 1
    m2 = await client.post(f"/lms/admin/courses/{course.id}/modules", headers=_headers(ops), json={"title": "M2"})
    assert m2.status_code == 201 and m2.json()["position"] == 2

    conflict = await client.post(
        f"/lms/admin/courses/{course.id}/modules", headers=_headers(ops),
        json={"title": "M1-dup", "position": 1},
    )
    assert conflict.status_code == http_status.HTTP_409_CONFLICT

    renamed = await client.patch(
        f"/lms/admin/modules/{m1.json()['id']}", headers=_headers(ops), json={"title": "Renamed"}
    )
    assert renamed.status_code == 200 and renamed.json()["title"] == "Renamed"

    deleted = await client.delete(f"/lms/admin/modules/{m2.json()['id']}", headers=_headers(ops))
    assert deleted.status_code == 204


# ── items ────────────────────────────────────────────────────────────────────

async def _module(db, course, position=1) -> CourseModule:
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title=f"M{position}", position=position)
    db.add(module)
    await db.flush()
    return module


@pytest.mark.asyncio
async def test_text_item_create_and_update(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    await db.commit()

    created = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
        json={"kind": "text", "title": "Intro", "content": {"body": "Hello"}},
    )
    assert created.status_code == 201
    assert created.json()["content"] == {"body": "Hello"}
    item_id = created.json()["id"]

    updated = await client.patch(
        f"/lms/admin/items/{item_id}", headers=_headers(ops), json={"content": {"body": "Updated"}}
    )
    assert updated.status_code == 200 and updated.json()["content"] == {"body": "Updated"}

    deleted = await client.delete(f"/lms/admin/items/{item_id}", headers=_headers(ops))
    assert deleted.status_code == 204
    assert await db.get(ModuleItem, uuid.UUID(item_id)) is None


@pytest.mark.asyncio
async def test_quiz_item_validates_shape_and_strips_nothing_from_the_author(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    await db.commit()

    bad = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
        json={"kind": "quiz", "content": {"pass_threshold": 70, "questions": []}},
    )
    assert bad.status_code == http_status.HTTP_400_BAD_REQUEST

    good = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
        json={"kind": "quiz", "content": {
            "pass_threshold": 70,
            "questions": [{
                "prompt": "2+2?", "explanation": "math",
                "options": [{"text": "4", "is_correct": True}, {"text": "5", "is_correct": False}],
            }],
        }},
    )
    assert good.status_code == 201
    # the author's view keeps is_correct/explanation — only student_view strips them
    q = good.json()["content"]["questions"][0]
    assert q["explanation"] == "math"
    assert q["options"][0]["is_correct"] is True


# ── video checkpoints ────────────────────────────────────────────────────────

async def _video_item(db, module) -> ModuleItem:
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="video", content={})
    db.add(item)
    await db.flush()
    return item


@pytest.mark.asyncio
async def test_checkpoint_note_crud(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    video = await _video_item(db, module)
    await db.commit()

    created = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={"start_seconds": 30, "end_seconds": 45, "kind": "note", "content": {"body": "Watch the coil here"}},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["end_seconds"] == 45 and body["content"] == {"body": "Watch the coil here"}
    checkpoint_id = body["id"]

    listed = await client.get(f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops))
    assert [c["id"] for c in listed.json()] == [checkpoint_id]

    updated = await client.patch(
        f"/lms/admin/checkpoints/{checkpoint_id}", headers=_headers(ops), json={"start_seconds": 35},
    )
    assert updated.status_code == 200 and updated.json()["start_seconds"] == 35

    deleted = await client.delete(f"/lms/admin/checkpoints/{checkpoint_id}", headers=_headers(ops))
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_checkpoint_note_requires_end_after_start(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    video = await _video_item(db, module)
    await db.commit()

    missing_end = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={"start_seconds": 30, "kind": "note", "content": {"body": "x"}},
    )
    assert missing_end.status_code == http_status.HTTP_400_BAD_REQUEST

    end_before_start = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={"start_seconds": 30, "end_seconds": 20, "kind": "note", "content": {"body": "x"}},
    )
    assert end_before_start.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_checkpoint_quiz_mcq_multiselect_open(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    video = await _video_item(db, module)
    await db.commit()

    mcq_bad = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={
            "start_seconds": 10, "kind": "quiz",
            "content": {
                "question_type": "mcq", "prompt": "Which one?",
                "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}],
            },
        },
    )
    assert mcq_bad.status_code == http_status.HTTP_400_BAD_REQUEST

    mcq_good = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={
            "start_seconds": 10, "kind": "quiz",
            "content": {
                "question_type": "mcq", "prompt": "Which one?",
                "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": False}],
            },
        },
    )
    assert mcq_good.status_code == 201, mcq_good.text
    assert mcq_good.json()["end_seconds"] is None  # a quiz has no window

    multiselect_bad = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={
            "start_seconds": 20, "kind": "quiz",
            "content": {
                "question_type": "multiselect", "prompt": "Pick all that apply",
                "options": [{"text": "a", "is_correct": False}, {"text": "b", "is_correct": False}],
            },
        },
    )
    assert multiselect_bad.status_code == http_status.HTTP_400_BAD_REQUEST

    multiselect_good = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={
            "start_seconds": 20, "kind": "quiz",
            "content": {
                "question_type": "multiselect", "prompt": "Pick all that apply",
                "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}],
            },
        },
    )
    assert multiselect_good.status_code == 201

    open_with_options = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={
            "start_seconds": 30, "kind": "quiz",
            "content": {"question_type": "open", "prompt": "Reflect", "options": [{"text": "a"}]},
        },
    )
    assert open_with_options.status_code == http_status.HTTP_400_BAD_REQUEST

    open_good = await client.post(
        f"/lms/admin/items/{video.id}/checkpoints", headers=_headers(ops),
        json={"start_seconds": 30, "kind": "quiz", "content": {"question_type": "open", "prompt": "Reflect"}},
    )
    assert open_good.status_code == 201


@pytest.mark.asyncio
async def test_checkpoints_require_a_video_item(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    text_item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text", content={"body": "x"})
    db.add(text_item)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/items/{text_item.id}/checkpoints", headers=_headers(ops),
        json={"start_seconds": 10, "end_seconds": 20, "kind": "note", "content": {"body": "x"}},
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_item_position_auto_appends_and_conflicts_are_409(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    await db.commit()

    first = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
        json={"kind": "text", "content": {"body": "a"}},
    )
    second = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
        json={"kind": "text", "content": {"body": "b"}},
    )
    assert first.json()["position"] == 1 and second.json()["position"] == 2

    conflict = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
        json={"kind": "text", "position": 1, "content": {"body": "c"}},
    )
    assert conflict.status_code == http_status.HTTP_409_CONFLICT


async def _fake_encoder(source_path):
    return EncodeResult(
        playlist=b"#EXTM3U\nsegment_000.ts\n", segments={"segment_000.ts": b"ts-bytes"},
        key=b"0" * 16, duration_seconds=42,
    )


@pytest.mark.asyncio
async def test_video_item_exposes_transcode_status_through_admin_api(db, client):
    """The `content` column on a video ModuleItem is always `{}` — the real
    state lives on ModuleVideo, written by the async worker. An author has no
    other way to tell an upload is still processing vs. actually ready."""
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    await db.commit()

    created = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops), json={"kind": "video", "content": {}},
    )
    item_id = created.json()["id"]
    # No upload yet — nothing to report.
    assert created.json()["content"] == {"transcode_status": None, "transcode_error": None, "duration_seconds": None}

    video = ModuleVideo(
        id=uuid.uuid4(), item_id=uuid.UUID(item_id), source_bucket="lms-video-sources",
        source_path=f"{item_id}/source.mp4", transcode_status="pending",
    )
    db.add(video)
    await db.commit()
    await storage.upload_to_path("lms-video-sources", video.source_path, b"source-bytes", "video/mp4")

    pending = await client.get(f"/lms/admin/modules/{module.id}/items", headers=_headers(ops))
    assert pending.json()[0]["content"]["transcode_status"] == "pending"

    await run_transcode(db, uuid.UUID(item_id), encoder=_fake_encoder)

    ready = await client.get(f"/lms/admin/modules/{module.id}/items", headers=_headers(ops))
    ready_content = ready.json()[0]["content"]
    assert ready_content["transcode_status"] == "ready"
    assert ready_content["duration_seconds"] == 42


# ── reordering ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reorder_modules_rewrites_positions_in_new_order(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    m1 = await _module(db, course, position=1)
    m2 = await _module(db, course, position=2)
    m3 = await _module(db, course, position=3)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/modules/reorder", headers=_headers(ops),
        json={"module_ids": [str(m3.id), str(m1.id), str(m2.id)]},
    )
    assert resp.status_code == 200, resp.text
    body = {row["id"]: row["position"] for row in resp.json()}
    assert body[str(m3.id)] == 1
    assert body[str(m1.id)] == 2
    assert body[str(m2.id)] == 3

    listed = await client.get(f"/lms/admin/courses/{course.id}/modules", headers=_headers(ops))
    assert [row["id"] for row in listed.json()] == [str(m3.id), str(m1.id), str(m2.id)]


@pytest.mark.asyncio
async def test_reorder_modules_rejects_mismatched_id_set(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    m1 = await _module(db, course, position=1)
    await _module(db, course, position=2)
    await db.commit()

    missing = await client.post(
        f"/lms/admin/courses/{course.id}/modules/reorder", headers=_headers(ops),
        json={"module_ids": [str(m1.id)]},
    )
    assert missing.status_code == http_status.HTTP_400_BAD_REQUEST

    foreign = await client.post(
        f"/lms/admin/courses/{course.id}/modules/reorder", headers=_headers(ops),
        json={"module_ids": [str(uuid.uuid4()), str(m1.id)]},
    )
    assert foreign.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_reorder_items_rewrites_positions_in_new_order(db, client):
    ops = await _user(db)
    course = await _course(db, author=ops)
    module = await _module(db, course)
    await db.commit()

    ids = []
    for body in ({"body": "a"}, {"body": "b"}, {"body": "c"}):
        created = await client.post(
            f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
            json={"kind": "text", "content": body},
        )
        ids.append(created.json()["id"])

    resp = await client.post(
        f"/lms/admin/modules/{module.id}/items/reorder", headers=_headers(ops),
        json={"item_ids": [ids[2], ids[0], ids[1]]},
    )
    assert resp.status_code == 200, resp.text
    assert [row["id"] for row in resp.json()] == [ids[2], ids[0], ids[1]]
    assert [row["position"] for row in resp.json()] == [1, 2, 3]


# ── program curriculum ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_curriculum_binding_add_list_remove(db, client):
    ops = await _user(db)
    program = await _program(db)
    course_a = await _course(db, author=ops, title="A")
    course_b = await _course(db, author=ops, title="B")
    await db.commit()

    add_a = await client.post(
        f"/lms/admin/programs/{program.id}/curriculum", headers=_headers(ops),
        json={"course_id": str(course_a.id)},
    )
    assert add_a.status_code == 201 and add_a.json()["position"] == 1

    add_b = await client.post(
        f"/lms/admin/programs/{program.id}/curriculum", headers=_headers(ops),
        json={"course_id": str(course_b.id)},
    )
    assert add_b.status_code == 201 and add_b.json()["position"] == 2

    dup = await client.post(
        f"/lms/admin/programs/{program.id}/curriculum", headers=_headers(ops),
        json={"course_id": str(course_a.id)},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT

    listed = await client.get(f"/lms/admin/programs/{program.id}/curriculum", headers=_headers(ops))
    assert [c["course_id"] for c in listed.json()] == [str(course_a.id), str(course_b.id)]

    removed = await client.delete(
        f"/lms/admin/programs/{program.id}/curriculum/{course_a.id}", headers=_headers(ops)
    )
    assert removed.status_code == 204
    remaining = (await db.execute(
        select(ProgramCurriculum).where(ProgramCurriculum.program_id == program.id)
    )).scalars().all()
    assert len(remaining) == 1 and remaining[0].course_id == course_b.id
