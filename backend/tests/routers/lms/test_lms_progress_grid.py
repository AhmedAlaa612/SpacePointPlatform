"""7B-1 (Missions Phase 2B) — GET /lms/admin/progress-grid: every active
student in a cohort x every course in its curriculum x every mission the
roster has attempted. Redis-free.
"""

import uuid
from datetime import date

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms import CohortCurriculum, Course, CourseModule, ModuleItem
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember, MissionVariant
from app.models.team import Team
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms import enroll, item_progress


async def _staff(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Grid Staff", email=f"gs-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _student(db, *, cohort_id: uuid.UUID, name: str, status: str = "registered") -> User:
    contact = Contact(id=uuid.uuid4(), full_name=name, contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name=name, email=f"{name.lower().replace(' ', '')}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.flush()
    db.add(Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort_id, status=status,
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    ))
    await db.flush()
    return student


async def _cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"PG-{uuid.uuid4().hex[:8]}", name="Grid Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Grid Cohort", status="running",
        starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 5),
    )
    db.add(cohort)
    await db.flush()
    return program, cohort


@pytest.mark.asyncio
async def test_progress_grid_requires_content_role(db, client):
    student = await _staff(db, roles=["student"])
    _, cohort = await _cohort(db)
    await db.commit()
    resp = await client.get(f"/lms/admin/progress-grid?cohort_id={cohort.id}", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_progress_grid_404s_for_unknown_cohort(db, client):
    ops = await _staff(db)
    await db.commit()
    resp = await client.get(f"/lms/admin/progress-grid?cohort_id={uuid.uuid4()}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_progress_grid_composes_course_and_mission_columns(db, client):
    ops = await _staff(db)
    _, cohort = await _cohort(db)

    course = Course(id=uuid.uuid4(), title="Grid Course", created_by=ops.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text", content={"body": "x"})
    db.add(item)
    db.add(CohortCurriculum(id=uuid.uuid4(), cohort_id=cohort.id, course_id=course.id, position=1))
    await db.flush()

    finisher = await _student(db, cohort_id=cohort.id, name="Finisher Fran")
    untouched = await _student(db, cohort_id=cohort.id, name="Untouched Uma")
    dropped = await _student(db, cohort_id=cohort.id, name="Dropped Dan", status="cancelled")

    await enroll(db, user_id=finisher.id, course_id=course.id, source="registration")
    await item_progress(db, user_id=finisher.id, item_id=item.id, action="text-viewed")

    mission = Mission(
        id=uuid.uuid4(), title="Grid Mission", slug=f"grid-mission-{uuid.uuid4().hex[:8]}",
        kind="submission", status="published", authored_by=ops.id,
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=25)
    db.add(variant)
    await db.flush()
    failed_attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=finisher.id,
        attempt_no=1, status="failed", payload={},
    )
    db.add(failed_attempt)
    await db.flush()
    passed_attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=finisher.id,
        attempt_no=2, status="passed", score=90, payload={},
    )
    db.add(passed_attempt)
    await db.commit()

    resp = await client.get(f"/lms/admin/progress-grid?cohort_id={cohort.id}", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["cohort_id"] == str(cohort.id)
    assert [c["title"] for c in body["courses"]] == ["Grid Course"]
    assert [m["title"] for m in body["missions"]] == ["Grid Mission"]

    names = {row["user_id"]: row for row in body["rows"]}
    assert {row["full_name"] for row in body["rows"]} == {"Finisher Fran", "Untouched Uma"}
    assert not any(row["full_name"] == "Dropped Dan" for row in body["rows"])

    fran = next(row for row in body["rows"] if row["full_name"] == "Finisher Fran")
    fran_course = fran["courses"][str(course.id)]
    assert fran_course == {"enrolled": True, "pct": 100}
    fran_mission = fran["missions"][str(mission.id)]
    # a later passed attempt outranks an earlier failed one, even though
    # attempt_no is higher on the passed attempt too — passed always wins
    assert fran_mission["status"] == "passed"
    assert fran_mission["score"] == 90.0
    assert fran_mission["attempt_no"] == 2

    uma = next(row for row in body["rows"] if row["full_name"] == "Untouched Uma")
    assert uma["courses"][str(course.id)] == {"enrolled": False, "pct": 0}
    assert uma["missions"] == {}


@pytest.mark.asyncio
async def test_progress_grid_resolves_team_attempts_via_frozen_roster(db, client):
    ops = await _staff(db)
    _, cohort = await _cohort(db)
    member = await _student(db, cohort_id=cohort.id, name="Team Tara")

    mission = Mission(
        id=uuid.uuid4(), title="Crew Mission", slug=f"crew-mission-{uuid.uuid4().hex[:8]}",
        kind="submission", status="published", team_policy="team", authored_by=ops.id,
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=25)
    db.add(variant)
    await db.flush()
    team = Team(id=uuid.uuid4(), name="Team Alpha", cohort_id=cohort.id)
    db.add(team)
    await db.flush()
    attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, team_id=team.id,
        attempt_no=1, status="submitted", payload={},
    )
    db.add(attempt)
    await db.flush()
    db.add(MissionAttemptMember(attempt_id=attempt.id, user_id=member.id))
    await db.commit()

    resp = await client.get(f"/lms/admin/progress-grid?cohort_id={cohort.id}", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    tara = next(row for row in body["rows"] if row["full_name"] == "Team Tara")
    assert tara["missions"][str(mission.id)]["status"] == "submitted"
