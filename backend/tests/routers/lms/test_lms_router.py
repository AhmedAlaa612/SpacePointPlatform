"""LM1-3 router tests — the /lms/* student surface.

Covering the plan's exact guarantees: catalog/course outline are login-only
(any authenticated role), the gated routes are `require_lms_student` AND the
student must actually be enrolled, and a not-enrolled student sees a flat 404 —
never a 403 — so course existence isn't leaked. Plus the §2 leak guarantee at
the HTTP boundary: the module-read payload (which is what students download
*before* they submit) must contain no `is_correct` and no `explanation`, at any
depth. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms import (
    Course,
    CourseModule,
    Enrollment,
    ItemProgress,
    ModuleItem,
    ModuleVideo,
    VideoCheckpoint,
)
from app.models.user import User
from app.services.lms import enroll


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="LMS Router User",
        email=f"lms-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=list(roles) if roles else ["student"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course(db, *, author=None, published=True, **kw) -> Course:
    course = Course(
        id=uuid.uuid4(),
        title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"),
        created_by=author.id,
        is_published=published,
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


async def _item(db, module, *, position, kind, **kw) -> ModuleItem:
    item = ModuleItem(
        id=uuid.uuid4(), module_id=module.id, position=position, kind=kind, **kw,
    )
    db.add(item)
    await db.flush()
    return item


def _drill_keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _drill_keys(v)
    elif isinstance(node, list):
        for value in node:
            yield from _drill_keys(value)


# ── login-only reads ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog_and_course_require_login(db, client):
    no_auth = await client.get("/lms/catalog")
    assert no_auth.status_code == http_status.HTTP_401_UNAUTHORIZED

    resp = await client.get(f"/lms/courses/{uuid.uuid4()}")
    assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_catalog_lists_only_published_courses(db, client):
    author = await _user(db, roles=["operations"])
    live = await _course(db, author=author)
    draft = await _course(db, author=author, published=False)
    student = await _user(db)

    resp = await client.get("/lms/catalog", headers=_headers(student))
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert str(live.id) in ids
    assert str(draft.id) not in ids


@pytest.mark.asyncio
async def test_catalog_lists_invite_courses_locked_not_hidden(db, client):
    """P1-7: invite courses stay in the catalog with access_mode='invite' —
    the lock is client-rendered, never a server-side hide."""
    author = await _user(db, roles=["operations"])
    invite_course = await _course(db, author=author, access_mode="invite")
    student = await _user(db)

    resp = await client.get("/lms/catalog", headers=_headers(student))
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()}
    assert str(invite_course.id) in by_id
    assert by_id[str(invite_course.id)]["access_mode"] == "invite"
    assert by_id[str(invite_course.id)]["enrolled"] is False


@pytest.mark.asyncio
async def test_catalog_reflects_the_callers_own_enrollment(db, client):
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author)
    student = await _user(db)
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    resp = await client.get("/lms/catalog", headers=_headers(student))
    by_id = {c["id"]: c for c in resp.json()}
    assert by_id[str(course.id)]["enrolled"] is True

    # a different, unenrolled caller sees the same course as not enrolled
    stranger = await _user(db)
    resp2 = await client.get("/lms/catalog", headers=_headers(stranger))
    by_id2 = {c["id"]: c for c in resp2.json()}
    assert by_id2[str(course.id)]["enrolled"] is False


@pytest.mark.asyncio
async def test_global_leaderboard_endpoint_ranks_by_points(db, client):
    from app.services.lms.points import award_points

    top = await _user(db)
    bottom = await _user(db)
    await award_points(db, user_id=top.id, source="quiz", points=50, idempotency_key="a")
    await award_points(db, user_id=bottom.id, source="quiz", points=10, idempotency_key="b")
    await db.commit()

    resp = await client.get("/lms/leaderboard", headers=_headers(top))
    assert resp.status_code == 200
    body = resp.json()
    ids_in_order = [row["user_id"] for row in body]
    assert ids_in_order.index(str(top.id)) < ids_in_order.index(str(bottom.id))
    assert all("display_name" in row for row in body)


@pytest.mark.asyncio
async def test_cohort_leaderboard_requires_cohort_id(db, client):
    student = await _user(db)
    resp = await client.get("/lms/leaderboard", headers=_headers(student), params={"scope": "cohort"})
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_catalog_search_matches_title_or_description_case_insensitively(db, client):
    author = await _user(db, roles=["operations"])
    orbits = await _course(db, author=author, title="Orbital Mechanics", description="periapsis and apoapsis")
    ground = await _course(db, author=author, title="Ground Station Basics", description="antennas")
    student = await _user(db)

    by_title = await client.get("/lms/catalog", headers=_headers(student), params={"q": "orbital"})
    ids = [c["id"] for c in by_title.json()]
    assert str(orbits.id) in ids and str(ground.id) not in ids

    by_description = await client.get("/lms/catalog", headers=_headers(student), params={"q": "ANTENNAS"})
    ids = [c["id"] for c in by_description.json()]
    assert str(ground.id) in ids and str(orbits.id) not in ids

    no_match = await client.get("/lms/catalog", headers=_headers(student), params={"q": "nonexistent term"})
    assert no_match.json() == []


@pytest.mark.asyncio
async def test_unpublished_course_is_404_to_an_authenticated_but_unenrolled_user(db, client):
    author = await _user(db, roles=["operations"])
    draft = await _course(db, author=author, published=False)
    student = await _user(db)
    resp = await client.get(f"/lms/courses/{draft.id}", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_unpublished_course_is_reachable_by_an_enrolled_student(db, client):
    """B5: ops can enrol a student into a course still pending a publish
    review (e.g. via a program's curriculum) — that access must not
    dead-end at a 404 once the *My Courses* card is clicked."""
    author = await _user(db, roles=["operations"])
    draft = await _course(db, author=author, published=False)
    student = await _user(db)
    await enroll(db, user_id=student.id, course_id=draft.id, source="registration")
    await db.commit()

    resp = await client.get(f"/lms/courses/{draft.id}", headers=_headers(student))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(draft.id)


@pytest.mark.asyncio
async def test_self_enroll_still_requires_a_published_course(db, client):
    """Enrollment implies visibility, not the other way round — self-enrol
    into a draft course must still 404, since nobody can already hold an
    enrollment in a course they haven't self-enrolled into yet."""
    author = await _user(db, roles=["operations"])
    draft = await _course(db, author=author, published=False)
    student = await _user(db)

    resp = await client.post("/lms/enroll", json={"course_id": str(draft.id)}, headers=_headers(student))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_expired_enrollment_reads_as_not_enrolled(db, client):
    """P1-3: expires_at is decorative unless the access check reads it
    (audit §9.3(c)) — an enrollment whose expiry has passed must gate
    exactly like never having enrolled at all: flat 404, not a distinct
    "your access expired" response (don't leak existence, LM1-3 spec,
    extended to *why* access is gone)."""
    from datetime import datetime, timedelta, timezone

    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author)
    m1 = await _module(db, course, position=1)
    await _item(db, m1, position=1, kind="text", content={"body": "A"})
    student = await _user(db)
    enrollment = await enroll(db, user_id=student.id, course_id=course.id)
    enrollment.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db.commit()

    resp = await client.get(f"/lms/courses/{course.id}", headers=_headers(student))
    assert resp.status_code == 200  # outline is login-only, not enrollment-gated
    assert resp.json()["enrolled"] is False

    module = await client.get(f"/lms/modules/{m1.id}", headers=_headers(student))
    assert module.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_not_yet_expired_enrollment_still_grants_access(db, client):
    from datetime import datetime, timedelta, timezone

    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author)
    m1 = await _module(db, course, position=1)
    await _item(db, m1, position=1, kind="text", content={"body": "A"})
    student = await _user(db)
    enrollment = await enroll(db, user_id=student.id, course_id=course.id)
    enrollment.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    await db.commit()

    resp = await client.get(f"/lms/courses/{course.id}", headers=_headers(student))
    assert resp.json()["enrolled"] is True

    module = await client.get(f"/lms/modules/{m1.id}", headers=_headers(student))
    assert module.status_code == 200


@pytest.mark.asyncio
async def test_course_outline_shows_locks_and_completion(db, client):
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author)
    m1 = await _module(db, course, position=1)
    m2 = await _module(db, course, position=2)
    a = await _item(db, m1, position=1, kind="text", content={"body": "A"})
    opt = await _item(db, m1, position=2, kind="text", is_required=False, content={"body": "opt"})
    await _item(db, m2, position=1, kind="text", content={"body": "C"})
    student = await _user(db)
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    resp = await client.get(f"/lms/courses/{course.id}", headers=_headers(student))
    assert resp.status_code == 200
    body = resp.json()
    assert body["enrolled"] is True and body["completed"] is False
    assert body["access_mode"] == "open"
    locks = {m["position"]: m["locked"] for m in body["modules"]}
    assert locks == {1: False, 2: True}

    # completing module 1's only mandatory item unlocks module 2
    await client.post(
        f"/lms/items/{a.id}/progress", headers=_headers(student), json={"action": "text-viewed"}
    )
    resp = await client.get(f"/lms/courses/{course.id}", headers=_headers(student))
    locks = {m["position"]: m["locked"] for m in resp.json()["modules"]}
    assert locks == {1: False, 2: False}


# ── enrollment: student only, idempotent ────────────────────────────────────

@pytest.mark.asyncio
async def test_enroll_rejects_non_students_and_drafts(db, client):
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author)
    ops = await _user(db, roles=["operations"])

    denied = await client.post("/lms/enroll", headers=_headers(ops), json={"course_id": str(course.id)})
    assert denied.status_code == http_status.HTTP_403_FORBIDDEN

    draft = await _course(db, author=author, published=False)
    student = await _user(db)
    resp = await client.post("/lms/enroll", headers=_headers(student), json={"course_id": str(draft.id)})
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_student_self_enrolls_idempotently_despite_a_draft(db, client):
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author, published=True)
    student = await _user(db)

    first = await client.post("/lms/enroll", headers=_headers(student), json={"course_id": str(course.id)})
    assert first.status_code == 200
    assert first.json()["status"] == "active"

    again = await client.post("/lms/enroll", headers=_headers(student), json={"course_id": str(course.id)})
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]


@pytest.mark.asyncio
async def test_self_enroll_rejects_an_invite_only_course(db, client):
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author, access_mode="invite")
    student = await _user(db)

    resp = await client.post("/lms/enroll", headers=_headers(student), json={"course_id": str(course.id)})
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_self_enroll_on_a_paid_course_is_402(db, client):
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author, access_mode="paid")
    student = await _user(db)

    resp = await client.post("/lms/enroll", headers=_headers(student), json={"course_id": str(course.id)})
    assert resp.status_code == http_status.HTTP_402_PAYMENT_REQUIRED

    # Neither rejection actually created an enrollment.
    from app.models.lms import Enrollment
    from sqlalchemy import select as sa_select
    row = (await db.execute(
        sa_select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert row is None


@pytest.mark.asyncio
async def test_course_detail_reports_access_mode_for_a_not_yet_enrolled_caller(db, client):
    """P1-7: the detail payload carries access_mode so the frontend CTA can
    render Enrol / Buy / a lock without a second round trip."""
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author, access_mode="paid")
    student = await _user(db)

    resp = await client.get(f"/lms/courses/{course.id}", headers=_headers(student))
    assert resp.status_code == 200
    assert resp.json()["access_mode"] == "paid"
    assert resp.json()["enrolled"] is False


@pytest.mark.asyncio
async def test_self_enroll_on_an_open_course_sets_expiry_from_access_days(db, client):
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author, access_mode="open", access_days=30)
    student = await _user(db)

    resp = await client.post("/lms/enroll", headers=_headers(student), json={"course_id": str(course.id)})
    assert resp.status_code == 200
    assert resp.json()["expires_at"] is not None


# ── module read: student AND enrolled, leak-free ────────────────────────────

async def _tree_with_quiz(db):
    author = await _user(db, roles=["operations"])
    course = await _course(db, author=author)
    module = await _module(db, course)
    text = await _item(db, module, position=1, kind="text",
                       content={"body": "Ten minus four is six.", "explanation": "sneaky"})
    quiz = await _item(db, module, position=2, kind="quiz", content={
        "pass_threshold": 70,
        "questions": [
            {
                "prompt": "What is 2+2?",
                "explanation": "Because addition.",
                "options": [
                    {"text": "5", "is_correct": False},
                    {"text": "4", "is_correct": True},
                ],
            }
        ],
    })
    video = await _item(db, module, position=3, kind="video", content={})
    video_state = ModuleVideo(
        id=uuid.uuid4(), item_id=video.id, source_bucket="b", source_path="p.mp4",
        transcode_status="ready", duration_seconds=42,
    )
    db.add(video_state)
    await db.flush()
    return course, module, text, quiz


@pytest.mark.asyncio
async def test_module_read_gates_on_enrollment_not_role(db, client):
    """P1-6/D2 (2026-08-10): "yes, staff can take LMS courses" — content
    routes gate purely on enrollment now, not on holding the `student` role."""
    course, module, *_ = await _tree_with_quiz(db)

    # a not-yet-enrolled staff member gets 404, never a role-based 403 —
    # same don't-leak-existence treatment a student gets.
    ops = await _user(db, roles=["operations"])
    resp = await client.get(f"/lms/modules/{module.id}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

    # a student who is NOT enrolled gets 404, never 403 — don't leak existence
    stranger = await _user(db)
    resp = await client.get(f"/lms/modules/{module.id}", headers=_headers(stranger))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

    # enrolled -> 200, for a student...
    await enroll(db, user_id=stranger.id, course_id=course.id)
    await db.commit()
    resp = await client.get(f"/lms/modules/{module.id}", headers=_headers(stranger))
    assert resp.status_code == 200

    # ...and equally for enrolled staff (D2).
    await enroll(db, user_id=ops.id, course_id=course.id)
    await db.commit()
    resp = await client.get(f"/lms/modules/{module.id}", headers=_headers(ops))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_module_read_leaks_no_answers_and_enriches_video_state(db, client):
    """The §2 guarantee at the HTTP boundary: no is_correct / explanation in
    the *pre-submission* payload, at any depth, for every kind."""
    course, module, text, quiz = await _tree_with_quiz(db)
    student = await _user(db)
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    resp = await client.get(f"/lms/modules/{module.id}", headers=_headers(student))
    assert resp.status_code == 200
    body = resp.json()
    for key in _drill_keys(body):
        assert key not in {"is_correct", "explanation"}, f"leaked key {key}"

    by_kind = {i["kind"]: i for i in body["items"]}
    assert by_kind["text"]["content"] == {"body": "Ten minus four is six."}
    quiz_content = by_kind["quiz"]["content"]
    assert quiz_content["pass_threshold"] == 70
    assert quiz_content["questions"][0]["options"] == [{"text": "5"}, {"text": "4"}]
    assert "is_correct" not in quiz_content["questions"][0]["options"][0]
    assert by_kind["video"]["content"]["transcode_status"] == "ready"
    assert by_kind["video"]["content"]["duration_seconds"] == 42


# ── learner writes: quiz + progress ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_quiz_submit_grades_server_side_and_requires_enrollment(db, client):
    course, module, _, quiz = await _tree_with_quiz(db)
    stranger = await _user(db)
    # not enrolled -> 404
    resp = await client.post(
        f"/lms/items/{quiz.id}/quiz/submit", headers=_headers(stranger), json={"answers": [1]}
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

    await enroll(db, user_id=stranger.id, course_id=course.id)
    await db.commit()

    wrong = await client.post(
        f"/lms/items/{quiz.id}/quiz/submit", headers=_headers(stranger), json={"answers": [0]}
    )
    assert wrong.status_code == 200
    review = wrong.json()
    assert review["score"] == 0.0 and review["passed"] is False
    assert review["questions"][0]["correct"] is False
    assert review["questions"][0]["correct_text"] == "4"
    assert review["questions"][0]["explanation"] == "Because addition."

    right = await client.post(
        f"/lms/items/{quiz.id}/quiz/submit", headers=_headers(stranger), json={"answers": [1]}
    )
    assert right.status_code == 200
    assert right.json()["passed"] is True and right.json()["best_score"] == 100.0

    # progress row shows the quiz is completed, attempts counted
    rows = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == stranger.id, ItemProgress.item_id == quiz.id
        )
    )).scalars().all()
    assert rows[0].status == "completed" and rows[0].quiz_attempts == 2


@pytest.mark.asyncio
async def test_quiz_check_gives_live_feedback_without_recording_an_attempt(db, client):
    """quiz/check (2026-08-09) — the live, one-question-at-a-time feedback
    the submit test above doesn't cover: no attempt counted, no grading/
    completion state touched, same correct/explanation/correct_text shape
    as a submit review's per-question entry. It DOES record hints_used
    (P2-3, 2026-08-10) — that's the one thing it's allowed to touch."""
    course, module, _, quiz = await _tree_with_quiz(db)
    stranger = await _user(db)

    not_enrolled = await client.post(
        f"/lms/items/{quiz.id}/quiz/check", headers=_headers(stranger),
        json={"question_index": 0, "answer": 1},
    )
    assert not_enrolled.status_code == http_status.HTTP_404_NOT_FOUND

    await enroll(db, user_id=stranger.id, course_id=course.id)
    await db.commit()

    wrong = await client.post(
        f"/lms/items/{quiz.id}/quiz/check", headers=_headers(stranger),
        json={"question_index": 0, "answer": 0},
    )
    assert wrong.status_code == 200
    body = wrong.json()
    assert body["correct"] is False
    assert body["correct_text"] == "4"
    assert body["explanation"] == "Because addition."

    right = await client.post(
        f"/lms/items/{quiz.id}/quiz/check", headers=_headers(stranger),
        json={"question_index": 0, "answer": 1},
    )
    assert right.status_code == 200
    assert right.json()["correct"] is True

    out_of_range = await client.post(
        f"/lms/items/{quiz.id}/quiz/check", headers=_headers(stranger),
        json={"question_index": 5, "answer": 0},
    )
    assert out_of_range.status_code == http_status.HTTP_400_BAD_REQUEST

    # No grading/completion state touched — but hints_used counted the two
    # successful checks (the out-of-range one 400d before reaching it).
    row = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == stranger.id, ItemProgress.item_id == quiz.id
        )
    )).scalars().first()
    assert row is not None
    assert row.hints_used == 2
    assert row.status == "not_started"
    assert row.quiz_attempts == 0
    assert row.first_score is None


@pytest.mark.asyncio
async def test_progress_write_requires_enrollment_and_valid_action(db, client):
    course, module, text, _quiz = await _tree_with_quiz(db)
    stranger = await _user(db)
    resp = await client.post(
        f"/lms/items/{text.id}/progress", headers=_headers(stranger), json={"action": "text-viewed"}
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

    await enroll(db, user_id=stranger.id, course_id=course.id)
    await db.commit()

    resp = await client.post(
        f"/lms/items/{text.id}/progress", headers=_headers(stranger), json={"action": "text-viewed"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # an unknown action never reaches the service — the schema literal rejects
    # it with 422, the service-level 400 stays as the backstop for direct calls
    bad = await client.post(
        f"/lms/items/{text.id}/progress", headers=_headers(stranger), json={"action": "fidget"}
    )
    assert bad.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY


# ── video checkpoints (timeline notes + mid-video quizzes, 2026-08-07) ───────

async def _video_with_checkpoints(db):
    course, module, *_ = await _tree_with_quiz(db)
    video = await _item(db, module, position=4, kind="video", content={})
    note = VideoCheckpoint(
        id=uuid.uuid4(), item_id=video.id, start_seconds=3, end_seconds=6,
        kind="note", content={"body": "Watch this part"},
    )
    quiz_cp = VideoCheckpoint(
        id=uuid.uuid4(), item_id=video.id, start_seconds=10, end_seconds=None, kind="quiz",
        content={
            "question_type": "mcq", "prompt": "Which one?", "explanation": "It's gravity.",
            "options": [{"text": "Gravity", "is_correct": True}, {"text": "Magnetism", "is_correct": False}],
        },
    )
    multi_cp = VideoCheckpoint(
        id=uuid.uuid4(), item_id=video.id, start_seconds=15, end_seconds=None, kind="quiz",
        content={
            "question_type": "multiselect", "prompt": "Pick the planets", "explanation": None,
            "options": [
                {"text": "Mars", "is_correct": True}, {"text": "Sun", "is_correct": False},
                {"text": "Venus", "is_correct": True},
            ],
        },
    )
    open_cp = VideoCheckpoint(
        id=uuid.uuid4(), item_id=video.id, start_seconds=18, end_seconds=None, kind="quiz",
        content={"question_type": "open", "prompt": "What surprised you?", "explanation": None},
    )
    db.add_all([note, quiz_cp, multi_cp, open_cp])
    await db.flush()
    return course, video, note, quiz_cp, multi_cp, open_cp


@pytest.mark.asyncio
async def test_checkpoints_list_is_sanitized_and_requires_enrollment(db, client):
    course, video, note, quiz_cp, *_ = await _video_with_checkpoints(db)
    stranger = await _user(db)
    await db.commit()

    not_enrolled = await client.get(f"/lms/items/{video.id}/checkpoints", headers=_headers(stranger))
    assert not_enrolled.status_code == http_status.HTTP_404_NOT_FOUND

    await enroll(db, user_id=stranger.id, course_id=course.id)
    await db.commit()

    resp = await client.get(f"/lms/items/{video.id}/checkpoints", headers=_headers(stranger))
    assert resp.status_code == 200
    body = resp.json()
    for key in _drill_keys(body):
        assert key not in {"is_correct", "explanation"}, f"leaked key {key}"

    by_id = {c["id"]: c for c in body}
    assert by_id[str(note.id)]["content"] == {"body": "Watch this part"}
    assert by_id[str(quiz_cp.id)]["content"] == {
        "question_type": "mcq", "prompt": "Which one?",
        "options": [{"text": "Gravity"}, {"text": "Magnetism"}],
    }


@pytest.mark.asyncio
async def test_checkpoint_answer_grades_mcq_multiselect_open(db, client):
    course, video, _note, quiz_cp, multi_cp, open_cp = await _video_with_checkpoints(db)
    stranger = await _user(db)
    await db.commit()

    # not enrolled -> 404
    denied = await client.post(
        f"/lms/items/{video.id}/checkpoints/{quiz_cp.id}/answer", headers=_headers(stranger), json={"answer": 0},
    )
    assert denied.status_code == http_status.HTTP_404_NOT_FOUND

    await enroll(db, user_id=stranger.id, course_id=course.id)
    await db.commit()

    mcq_wrong = await client.post(
        f"/lms/items/{video.id}/checkpoints/{quiz_cp.id}/answer", headers=_headers(stranger), json={"answer": 1},
    )
    assert mcq_wrong.status_code == 200
    assert mcq_wrong.json() == {"correct": False, "explanation": "It's gravity."}

    mcq_right = await client.post(
        f"/lms/items/{video.id}/checkpoints/{quiz_cp.id}/answer", headers=_headers(stranger), json={"answer": 0},
    )
    assert mcq_right.json()["correct"] is True

    multi_partial = await client.post(
        f"/lms/items/{video.id}/checkpoints/{multi_cp.id}/answer", headers=_headers(stranger), json={"answer": [0]},
    )
    assert multi_partial.json()["correct"] is False

    multi_exact = await client.post(
        f"/lms/items/{video.id}/checkpoints/{multi_cp.id}/answer",
        headers=_headers(stranger), json={"answer": [0, 2]},
    )
    assert multi_exact.json()["correct"] is True

    open_answer = await client.post(
        f"/lms/items/{video.id}/checkpoints/{open_cp.id}/answer",
        headers=_headers(stranger), json={"answer": "The eccentricity."},
    )
    assert open_answer.status_code == 200
    assert open_answer.json() == {"correct": None, "explanation": None}