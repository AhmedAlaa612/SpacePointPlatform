"""LMS Observer Mode (2026-10) — "a student with a label plus a reset".

Covers the full slice: 1-click staff onboarding (try-as-observer), student
endpoint parity without the `student` role, observer invite-code signup,
individual/team resets, unassign, and the operational partitions (roster,
quiz analysis, judging leaderboard/queue, certificates, card format).
Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.competitions.judging import CompetitionJudge
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.cohort_quiz import CohortQuizAttempt
from app.models.lms.course import Course, CourseModule, ModuleItem
from app.models.lms.enrollment import ItemProgress
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress,
    LmsProgramTeamItemProgress,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team, TeamMember
from app.models.user import User
from app.schemas.lms_cohort_quiz import CohortQuizQuestionIn, CohortQuizQuestionOptionIn, CohortQuizTemplateCreate
from app.services.documents.card_id import format_card_id
from app.services.lms import cohort_quiz as cohort_quiz_service
from app.services.lms.program import (
    assign_lms_program, certificate_gate_satisfied, cohort_program_roster,
    get_student_checklist,
)
from app.services.competitions.judging import leaderboard
from app.services.competitions.certificates import get_cohort_certificate_recipients
from app.services.sessions.registration import register
from app.services.teams import create_team


def _headers(user: User, roles: list[str] | None = None) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, roles if roles is not None else user.role_values)}"}


async def _ops(db, *, roles=("operations",)) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Observer Test Ops", email=f"obs-ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles), status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, *, name="Observer Test Student") -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name=name, contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort_with_checklist(db, *, author) -> tuple[Cohort, LmsProgram, dict]:
    program = Program(
        id=uuid.uuid4(), code=f"OBS-{uuid.uuid4().hex[:8]}", name="Observer Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Observer Test Cohort", status="running")
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Observer Test Checklist")
    db.add(lms_program)
    await db.flush()

    template = await cohort_quiz_service.create_template(
        db, body=CohortQuizTemplateCreate(name="Observer Quiz Template"), created_by=author.id,
    )
    question = await cohort_quiz_service.create_question(
        db, body=CohortQuizQuestionIn(
            topic="EPS", difficulty="Easy", time_limit_seconds=15, prompt="What powers a satellite?",
            options=[
                CohortQuizQuestionOptionIn(text="Solar panels", is_correct=True),
                CohortQuizQuestionOptionIn(text="Gasoline", is_correct=False),
            ],
        ),
        created_by=author.id,
    )
    await cohort_quiz_service.add_template_question(db, template_id=template.id, question_id=question.id)

    def _item(position, **kw):
        item = LmsProgramItem(
            id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=position, **kw,
        )
        db.add(item)
        return item

    items = {}
    items["manual"] = _item(1, item_type="manual", title="Read the handbook")
    items["submission"] = _item(2, item_type="submission", title="Paste your profile link")
    items["quiz"] = _item(
        3, item_type="quiz", title="Knowledge check", cohort_quiz_template_id=template.id,
    )
    items["team_setup"] = _item(4, item_type="team_setup", title="Name your team", scope="team")
    items["team_poster"] = _item(5, item_type="submission", title="Team poster", scope="team")
    course = Course(id=uuid.uuid4(), title="Observer Basics", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    items["course"] = _item(6, item_type="course", title=course.title, course_id=course.id)
    await db.flush()
    return cohort, lms_program, items


async def _observe(db, client, *, user, cohort) -> uuid.UUID:
    """Runs the real try-as-observer endpoint for `user`."""
    resp = await client.post(f"/lms/admin/cohorts/{cohort.id}/try-as-observer", headers=_headers(user))
    assert resp.status_code == 200, resp.text
    return uuid.UUID(resp.json()["assignment_id"])


# ── onboarding ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_try_as_observer_creates_observer_assignment_team_and_role(db, client):
    ops = await _ops(db)
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    await db.commit()

    assignment_id = await _observe(db, client, user=ops, cohort=cohort)

    assignment = await db.get(LmsProgramAssignment, assignment_id)
    assert assignment is not None
    assert assignment.mode == "observer"
    assert assignment.user_id == ops.id

    await db.refresh(ops)
    assert "observer" in ops.role_values

    checklist = (await client.get(f"/lms/programs/{assignment_id}", headers=_headers(ops))).json()
    assert checklist["mode"] == "observer"
    assert checklist["team_name"] is not None

    team = (await db.execute(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(
            TeamMember.user_id == ops.id, Team.cohort_id == cohort.id,
        )
    )).scalars().first()
    assert team is not None
    assert team.is_observer is True

    # Idempotent — a second click reuses the same assignment.
    again = await _observe(db, client, user=ops, cohort=cohort)
    assert again == assignment_id


@pytest.mark.asyncio
async def test_try_as_observer_rejects_students_and_checklist_less_cohorts(db, client):
    ops = await _ops(db)
    student = await _student(db)
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    program = Program(
        id=uuid.uuid4(), code=f"NOCHK-{uuid.uuid4().hex[:6]}", name="No Checklist Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    bare = Cohort(id=uuid.uuid4(), program_id=program.id, name="Bare Cohort", status="running")
    db.add(bare)
    await db.commit()

    resp = await client.post(f"/lms/admin/cohorts/{cohort.id}/try-as-observer", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN

    resp = await client.post(f"/lms/admin/cohorts/{bare.id}/try-as-observer", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST

    # A real participant assignment in the cohort conflicts instead of flipping.
    participant = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    assert participant.mode == "participant"
    # Grant the account a staff role in the DB itself (JWT roles are never
    # trusted — the endpoint reads roles off the user row), then retry.
    student.roles = [*student.roles, "operations"]
    await db.flush()
    await db.commit()
    resp = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/try-as-observer", headers=_headers(student),
    )
    assert resp.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_try_as_observer_allows_assigned_instructor(db, client):
    from datetime import date
    from app.models.sessions.delivery_role import DeliveryRole
    from app.models.sessions.session import Session as DeliverySession, SessionInstructor
    ops = await _ops(db)
    instructor = await _ops(db, roles=("instructor",))
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    session = DeliverySession(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1))
    db.add(session)
    await db.flush()
    role_id = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator"))
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role_id=role_id))
    await db.commit()

    assignment_id = await _observe(db, client, user=instructor, cohort=cohort)
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    assert assignment.mode == "observer"


# ── student parity without the student role ────────────────────────────────

@pytest.mark.asyncio
async def test_observer_runs_the_full_student_flow_without_student_role(db, client):
    ops = await _ops(db)
    cohort, _, items = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    assignment_id = await _observe(db, client, user=ops, cohort=cohort)
    h = _headers(ops)
    assert "student" not in ops.role_values

    # Self-check a manual item.
    resp = await client.post(
        f"/lms/programs/{assignment_id}/items/{items['manual'].id}/complete", headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"

    # Paste-back a submission.
    resp = await client.post(
        f"/lms/programs/{assignment_id}/items/{items['submission'].id}/submit",
        headers=h, json={"url": "https://example.com/me"},
    )
    assert resp.status_code == 200, resp.text

    # Real quiz grading (start → submit → result are all 200, never 403).
    start = await client.post(
        f"/lms/programs/{assignment_id}/items/{items['quiz'].id}/quiz/start", headers=h,
    )
    assert start.status_code == 200, start.text
    question = start.json()["questions"][0]
    correct = question["options"].index("Solar panels")
    submit = await client.post(
        f"/lms/programs/{assignment_id}/items/{items['quiz'].id}/quiz/submit", headers=h,
        json={"answers": [{"question_id": question["question_id"], "selected_option_index": correct}]},
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["score"] == 1
    result = await client.get(
        f"/lms/programs/{assignment_id}/items/{items['quiz'].id}/quiz/result", headers=h,
    )
    assert result.status_code == 200

    # Team formation + shared deliverables on the flagged observer team.
    resp = await client.post(
        f"/lms/programs/{assignment_id}/items/{items['team_setup'].id}/team-name",
        headers=h, json={"name": "Observer Pioneers"},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"/lms/programs/{assignment_id}/items/{items['team_poster'].id}/submit",
        headers=h, json={"url": "https://example.com/poster"},
    )
    assert resp.status_code == 200, resp.text

    # Final gate locking, exactly like a student team.
    resp = await client.post(f"/lms/programs/{assignment_id}/final-submit", headers=h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["team_final_locked_at"] is not None


@pytest.mark.asyncio
async def test_program_endpoints_still_enforce_ownership(db, client):
    ops = await _ops(db)
    other = await _ops(db)
    cohort, _, items = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    assignment_id = await _observe(db, client, user=ops, cohort=cohort)

    resp = await client.get(f"/lms/programs/{assignment_id}", headers=_headers(other))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND
    resp = await client.post(
        f"/lms/programs/{assignment_id}/items/{items['manual'].id}/complete", headers=_headers(other),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_participant_assignments_cannot_use_observer_resets(db, client):
    ops = await _ops(db)
    student = await _student(db)
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    for method, path in [
        ("post", f"/lms/programs/{assignment.id}/observer-reset"),
        ("post", f"/lms/programs/{assignment.id}/observer-team-reset"),
        ("delete", f"/lms/programs/{assignment.id}/observer-unassign"),
    ]:
        resp = await getattr(client, method)(path, headers=_headers(student))
        assert resp.status_code == http_status.HTTP_403_FORBIDDEN, (method, path, resp.text)


# ── resets & unassign ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_observer_reset_wipes_individual_but_keeps_team(db, client):
    ops = await _ops(db)
    cohort, _, items = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    assignment_id = await _observe(db, client, user=ops, cohort=cohort)
    h = _headers(ops)

    # Simulate course-player progress on the checklist's attached course.
    module = CourseModule(
        id=uuid.uuid4(), course_id=items["course"].course_id, title="Intro", position=1,
    )
    db.add(module)
    await db.flush()
    module_item = ModuleItem(
        id=uuid.uuid4(), module_id=module.id, position=1, kind="text", title="Welcome",
        content={"body": "hi"},
    )
    db.add(module_item)
    await db.flush()
    db.add(ItemProgress(id=uuid.uuid4(), user_id=ops.id, item_id=module_item.id, status="completed"))
    await db.flush()

    await client.post(
        f"/lms/programs/{assignment_id}/items/{items['submission'].id}/submit",
        headers=h, json={"url": "https://example.com/me"},
    )
    start = await client.post(
        f"/lms/programs/{assignment_id}/items/{items['quiz'].id}/quiz/start", headers=h,
    )
    question = start.json()["questions"][0]
    await client.post(
        f"/lms/programs/{assignment_id}/items/{items['quiz'].id}/quiz/submit", headers=h,
        json={"answers": [{"question_id": question["question_id"], "selected_option_index": 0}]},
    )
    await client.post(
        f"/lms/programs/{assignment_id}/items/{items['team_setup'].id}/team-name",
        headers=h, json={"name": "Keep Me"},
    )
    await client.post(
        f"/lms/programs/{assignment_id}/items/{items['team_poster'].id}/submit",
        headers=h, json={"url": "https://example.com/team"},
    )

    resp = await client.post(f"/lms/programs/{assignment_id}/observer-reset", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_id = {i["id"]: i for i in body["items"]}
    assert by_id[str(items["submission"].id)]["status"] == "pending"
    assert by_id[str(items["submission"].id)]["submitted_url"] is None
    assert by_id[str(items["quiz"].id)]["status"] == "pending"
    # Team deliverables survive the individual reset.
    assert by_id[str(items["team_poster"].id)]["status"] == "done"
    assert by_id[str(items["team_poster"].id)]["submitted_url"] == "https://example.com/team"

    remaining = (await db.execute(
        select(CohortQuizAttempt).where(CohortQuizAttempt.user_id == ops.id)
    )).scalars().all()
    assert remaining == []

    remaining_progress = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == ops.id)
    )).scalars().all()
    assert remaining_progress == []


@pytest.mark.asyncio
async def test_observer_team_reset_unlocks_and_keeps_individual(db, client):
    ops = await _ops(db)
    cohort, _, items = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    assignment_id = await _observe(db, client, user=ops, cohort=cohort)
    h = _headers(ops)
    submission_id = str(items["submission"].id)
    team_setup_id = str(items["team_setup"].id)
    team_poster_id = str(items["team_poster"].id)

    await client.post(
        f"/lms/programs/{assignment_id}/items/{submission_id}/submit",
        headers=h, json={"url": "https://example.com/me"},
    )
    await client.post(
        f"/lms/programs/{assignment_id}/items/{team_setup_id}/team-name",
        headers=h, json={"name": "Resettable"},
    )
    await client.post(
        f"/lms/programs/{assignment_id}/items/{team_poster_id}/submit",
        headers=h, json={"url": "https://example.com/team"},
    )
    locked = await client.post(f"/lms/programs/{assignment_id}/final-submit", headers=h)
    assert locked.status_code == 200

    resp = await client.post(f"/lms/programs/{assignment_id}/observer-team-reset", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["team_final_locked_at"] is None
    by_id = {i["id"]: i for i in body["items"]}
    assert by_id[team_poster_id]["status"] == "pending"
    assert by_id[team_poster_id]["submitted_url"] is None
    # The individual slice survives the team reset.
    assert by_id[submission_id]["status"] == "done"


@pytest.mark.asyncio
async def test_observer_unassign_removes_assignment_and_emptied_team(db, client):
    ops = await _ops(db)
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    assignment_id = await _observe(db, client, user=ops, cohort=cohort)

    team_id = (await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == ops.id)
    )).scalars().first()
    assert team_id is not None

    resp = await client.delete(f"/lms/programs/{assignment_id}/observer-unassign", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    assert resp.json()["unassigned"] is True

    assert await db.get(LmsProgramAssignment, assignment_id) is None
    assert await db.get(Team, team_id) is None, "the emptied observer team is cleaned up"
    resp = await client.get(f"/lms/programs/{assignment_id}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


# ── operational partitions ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_roster_partitions_students_and_observers(db, client):
    ops = await _ops(db)
    student = await _student(db)
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    await _observe(db, client, user=ops, cohort=cohort)

    default = await cohort_program_roster(db, cohort_id=cohort.id)
    assert {r["user_id"] for r in default} == {student.id}

    observers = await cohort_program_roster(db, cohort_id=cohort.id, mode="observer")
    assert {r["user_id"] for r in observers} == {ops.id}

    everyone = await cohort_program_roster(db, cohort_id=cohort.id, mode="all")
    assert {r["user_id"] for r in everyone} == {student.id, ops.id}

    # And over HTTP with the toggle's query param.
    resp = await client.get(
        f"/lms/instructor/cohorts/{cohort.id}/program-progress",
        headers=_headers(ops), params={"mode": "observer"},
    )
    assert resp.status_code == 200, resp.text
    assert [r["user_id"] for r in resp.json()] == [str(ops.id)]


@pytest.mark.asyncio
async def test_quiz_analysis_excludes_observers_by_default(db, client):
    ops = await _ops(db)
    student = await _student(db)
    cohort, _, items = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    student_assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    observer_id = await _observe(db, client, user=ops, cohort=cohort)

    async def _submit(user, assignment_id, option_text):
        h = _headers(user)
        start = await client.post(
            f"/lms/programs/{assignment_id}/items/{items['quiz'].id}/quiz/start", headers=h,
        )
        assert start.status_code == 200, start.text
        q = start.json()["questions"][0]
        sub = await client.post(
            f"/lms/programs/{assignment_id}/items/{items['quiz'].id}/quiz/submit", headers=h,
            json={"answers": [{"question_id": q["question_id"], "selected_option_index": q["options"].index(option_text)}]},
        )
        assert sub.status_code == 200, sub.text

    await _submit(student, student_assignment.id, "Solar panels")  # correct
    await _submit(ops, observer_id, "Gasoline")  # wrong on purpose

    default = await cohort_quiz_service.get_cohort_quiz_analysis(db, cohort_id=cohort.id)
    assert default["quizzes"][0]["total_attempts"] == 1

    with_observers = await cohort_quiz_service.get_cohort_quiz_analysis(
        db, cohort_id=cohort.id, include_observers=True,
    )
    assert with_observers["quizzes"][0]["total_attempts"] == 2

    resp = await client.get(
        f"/lms/admin/cohorts/{cohort.id}/quiz-analysis", headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_judging_excludes_observer_teams(db, client):
    ops = await _ops(db)
    judge = await _ops(db, roles=("judge",))
    student = await _student(db)
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    await db.commit()
    await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    await _observe(db, client, user=ops, cohort=cohort)

    real_team = await create_team(db, name="Real Team", created_by=student.id, cohort_id=cohort.id)
    db.add(CompetitionJudge(id=uuid.uuid4(), cohort_id=cohort.id, user_id=judge.id))
    await db.commit()

    rows = await leaderboard(db, cohort_id=cohort.id)
    assert {r["team_name"] for r in rows} == {"Real Team"}

    resp = await client.get(
        "/competitions/judge/teams", headers=_headers(judge), params={"cohort_id": str(cohort.id)},
    )
    assert resp.status_code == 200, resp.text
    assert [t["name"] for t in resp.json()] == ["Real Team"]


@pytest.mark.asyncio
async def test_observers_are_suppressed_from_certificates(db, client):
    ops = await _ops(db)
    student = await _student(db)
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    observer_contact = Contact(
        id=uuid.uuid4(), full_name="Observer Tester", email=f"obs-tester-{uuid.uuid4().hex[:6]}@example.com",
        contact_roles=["student"], secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(observer_contact)
    await db.flush()
    observer = User(
        id=uuid.uuid4(), full_name="Observer Tester", email=observer_contact.email,
        password_hash="x", roles=["observer"], status="active", contact_id=observer_contact.id,
    )
    db.add(observer)
    await db.flush()
    await db.commit()

    student_reg = await register(
        db, contact_id=student.contact_id, cohort_id=cohort.id,
        registered_via="desk", payment_status="waived",
    )
    observer_reg = await register(
        db, contact_id=observer_contact.id, cohort_id=cohort.id,
        registered_via="invite_code", payment_status="waived",
    )
    await db.flush()
    await assign_lms_program(
        db, user_id=observer.id, cohort_id=cohort.id, registration_id=observer_reg.id, mode="observer",
    )
    await db.commit()

    # The observer gate never satisfies, even with a finished checklist.
    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=observer.id) is False

    data = await get_cohort_certificate_recipients(db, cohort_id=cohort.id, filter_type="all")
    assert student_reg.id in {r["registration_id"] for r in data["recipients"]}
    assert observer_reg.id not in {r["registration_id"] for r in data["recipients"]}


# ── invite-code onboarding + card format ───────────────────────────────────

def test_format_card_id_observer_prefix():
    assert format_card_id(7, ["observer"]) == "SP-OB-0007-UAE"
    assert format_card_id(7, ["student"]) == "SP-ST-0007-UAE"
    assert format_card_id(7, ["operations"]) == "SP-0007-UAE"
    # Multi-role staff testing as observers keep their staff card.
    assert format_card_id(7, ["operations", "observer"]) == "SP-0007-UAE"


@pytest.mark.asyncio
async def test_observer_invite_code_signup_gets_observer_role_card_and_mode(db, client):
    ops = await _ops(db)
    cohort, _, _ = await _cohort_with_checklist(db, author=ops)
    code = InvitationCode(
        id=uuid.uuid4(), code="OBSERVER-BATCH", kind="observer", label="External testers",
        is_active=True, max_uses=100, used_count=0,
    )
    db.add(code)
    await db.flush()
    db.add(InvitationCodeGrant(
        id=uuid.uuid4(), invitation_code_id=code.id, product_type="lms_program", cohort_id=cohort.id,
    ))
    await db.commit()

    email = f"external-tester-{uuid.uuid4().hex[:6]}@example.com"
    resp = await client.post("/auth/signup", json={
        "invite_code": "observer-batch",
        "full_name": "External Tester",
        "email": email,
        "phone": "+971501234567",
        "password": "s3cret-pass",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    assert resp.json()["user"]["roles"] == ["observer"]

    user = (await db.execute(select(User).where(User.email == email))).scalars().first()
    assert user is not None
    assert format_card_id(user.card_number, user.role_values) == f"SP-OB-{user.card_number:04d}-UAE"

    assignment = (await db.execute(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == user.id, LmsProgramAssignment.cohort_id == cohort.id,
        )
    )).scalars().first()
    assert assignment is not None
    assert assignment.mode == "observer"

    checklist = await get_student_checklist(db, assignment_id=assignment.id, user_id=user.id)
    assert checklist is not None
    assert checklist["mode"] == "observer"

    reg = (await db.execute(
        select(Registration).where(Registration.contact_id == user.contact_id, Registration.cohort_id == cohort.id)
    )).scalars().first()
    assert reg is not None


@pytest.mark.asyncio
async def test_student_codes_still_sign_up_students(db, client):
    ops = await _ops(db)
    await _cohort_with_checklist(db, author=ops)
    db.add(InvitationCode(
        id=uuid.uuid4(), code="STUDENT-BATCH", kind="student", is_active=True, max_uses=100, used_count=0,
    ))
    await db.commit()

    email = f"regular-{uuid.uuid4().hex[:6]}@example.com"
    resp = await client.post("/auth/signup", json={
        "invite_code": "STUDENT-BATCH",
        "full_name": "Regular Student",
        "email": email,
        "phone": "+971501234567",
        "password": "s3cret-pass",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    assert resp.json()["user"]["roles"] == ["student"]
