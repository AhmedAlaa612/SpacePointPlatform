"""Cohort-scoped instructor Missions surface (2026-08-17) —
`/missions/instructor/*`. Redis-free (uses the `client` fixture), mirrors
`test_missions_manager_router.py`'s fixture style.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Instructor Test User", email=f"instr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _mission(db, *, author, title="Instructor-Surface Mission") -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title=title, slug=f"{title.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=1, points=100)
    db.add(variant)
    await db.flush()
    return mission, variant


async def _cohort_with_session(db) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"INS-{uuid.uuid4().hex[:8]}", name="Instructor Surface Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Instructor Surface Cohort", status="running")
    db.add(cohort)
    await db.flush()
    from datetime import date
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1))
    db.add(session)
    await db.flush()
    return cohort, session


async def _assign_instructor(db, *, session: Session, user: User, role: str = "Lead Facilitator") -> None:
    role_id = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == role))
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=user.id, role_id=role_id))
    await db.flush()


# ── cohort listing + progress ────────────────────────────────────────────

async def test_unassigned_instructor_gets_404_on_a_cohort_they_dont_teach(db, client):
    author = await _user(db, roles=["operations"])
    cohort, _ = await _cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await db.commit()

    resp = await client.get(f"/missions/instructor/cohorts/{cohort.id}/progress", headers=_headers(instructor))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


async def test_assigned_instructor_sees_their_cohort_progress(db, client):
    author = await _user(db, roles=["operations"])
    cohort, session = await _cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await _assign_instructor(db, session=session, user=instructor)
    await db.commit()

    cohorts = await client.get("/missions/instructor/cohorts", headers=_headers(instructor))
    assert cohorts.status_code == 200, cohorts.text
    assert [c["id"] for c in cohorts.json()] == [str(cohort.id)]

    progress = await client.get(f"/missions/instructor/cohorts/{cohort.id}/progress", headers=_headers(instructor))
    assert progress.status_code == 200, progress.text
    assert progress.json()["cohort_id"] == str(cohort.id)


async def test_staff_reaches_any_cohort_without_a_session_assignment(db, client):
    author = await _user(db, roles=["operations"])
    cohort, _ = await _cohort_with_session(db)
    ops = await _user(db, roles=["operations"])
    await db.commit()

    cohorts = await client.get("/missions/instructor/cohorts", headers=_headers(ops))
    assert cohorts.status_code == 200
    assert any(c["id"] == str(cohort.id) for c in cohorts.json())

    progress = await client.get(f"/missions/instructor/cohorts/{cohort.id}/progress", headers=_headers(ops))
    assert progress.status_code == 200


async def test_plain_student_role_gets_403_from_the_route_dependency(db, client):
    cohort, _ = await _cohort_with_session(db)
    student = await _user(db)
    await db.commit()

    resp = await client.get(f"/missions/instructor/cohorts/{cohort.id}/progress", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


# ── gates ─────────────────────────────────────────────────────────────────

async def test_assigned_instructor_can_set_and_read_a_gate(db, client):
    author = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=author)
    cohort, session = await _cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await _assign_instructor(db, session=session, user=instructor)
    await db.commit()

    gates = await client.get(
        f"/missions/instructor/cohorts/{cohort.id}/missions/{mission.id}/gates", headers=_headers(instructor),
    )
    assert gates.status_code == 200, gates.text
    assert all(g["is_unlocked"] is False for g in gates.json())  # nothing set yet -> all locked-by-absence...

    put = await client.put(
        f"/missions/instructor/cohorts/{cohort.id}/missions/{mission.id}/gates/components",
        headers=_headers(instructor), json={"is_unlocked": True},
    )
    assert put.status_code == 200, put.text
    assert put.json()["is_unlocked"] is True
    assert put.json()["updated_by_name"] == instructor.full_name

    gates_after = await client.get(
        f"/missions/instructor/cohorts/{cohort.id}/missions/{mission.id}/gates", headers=_headers(instructor),
    )
    row = next(g for g in gates_after.json() if g["step_key"] == "components")
    assert row["is_unlocked"] is True


async def test_instructor_cannot_set_a_gate_on_a_cohort_they_dont_teach(db, client):
    author = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=author)
    cohort, _ = await _cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await db.commit()

    put = await client.put(
        f"/missions/instructor/cohorts/{cohort.id}/missions/{mission.id}/gates/components",
        headers=_headers(instructor), json={"is_unlocked": True},
    )
    assert put.status_code == http_status.HTTP_404_NOT_FOUND


# ── review ────────────────────────────────────────────────────────────────

async def test_assigned_instructor_sees_queue_and_can_review(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author)
    cohort, session = await _cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await _assign_instructor(db, session=session, user=instructor)
    student = await _user(db)
    attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=student.id,
        attempt_no=1, status="submitted", payload={"artifact_url": "https://example.com/x"}, cohort_id=cohort.id,
    )
    db.add(attempt)
    await db.commit()

    queue = await client.get(
        f"/missions/instructor/cohorts/{cohort.id}/missions/{mission.id}/queue", headers=_headers(instructor),
    )
    assert queue.status_code == 200, queue.text
    assert any(a["id"] == str(attempt.id) for a in queue.json())

    review = await client.post(
        f"/missions/instructor/attempts/{attempt.id}/review", headers=_headers(instructor),
        json={"passed": True, "score": 91, "review_comment": "Nice work"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "passed"


async def test_instructor_assigned_to_one_cohort_cannot_review_an_attempt_in_another(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author)
    my_cohort, my_session = await _cohort_with_session(db)
    other_cohort, _ = await _cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await _assign_instructor(db, session=my_session, user=instructor)
    student = await _user(db)
    attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=student.id,
        attempt_no=1, status="submitted", payload={}, cohort_id=other_cohort.id,
    )
    db.add(attempt)
    await db.commit()

    review = await client.post(
        f"/missions/instructor/attempts/{attempt.id}/review", headers=_headers(instructor),
        json={"passed": True, "score": 91},
    )
    assert review.status_code == http_status.HTTP_404_NOT_FOUND


async def test_only_staff_can_review_an_attempt_with_no_cohort_attribution(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author)
    _, session = await _cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await _assign_instructor(db, session=session, user=instructor)
    student = await _user(db)
    attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=student.id,
        attempt_no=1, status="submitted", payload={}, cohort_id=None,
    )
    db.add(attempt)
    await db.commit()

    instructor_attempt = await client.post(
        f"/missions/instructor/attempts/{attempt.id}/review", headers=_headers(instructor),
        json={"passed": True, "score": 91},
    )
    assert instructor_attempt.status_code == http_status.HTTP_404_NOT_FOUND

    ops = await _user(db, roles=["operations"])
    await db.commit()
    staff_attempt = await client.post(
        f"/missions/instructor/attempts/{attempt.id}/review", headers=_headers(ops),
        json={"passed": True, "score": 91},
    )
    assert staff_attempt.status_code == 200, staff_attempt.text
