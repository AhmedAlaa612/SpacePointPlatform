"""LMS Program checklist `quiz` item type (2026-09) — student-facing
start/submit/result endpoints, the checklist auto-tracking hook
(`refresh_item_progress`), and a smoke test of the admin authoring
endpoints. Redis-free (uses the `client` fixture)."""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.schemas.lms_cohort_quiz import CohortQuizQuestionIn, CohortQuizQuestionOptionIn, CohortQuizTemplateCreate
from app.services.lms import cohort_quiz as cohort_quiz_service
from app.services.lms.program import assign_lms_program


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _staff(db, roles=("operations",)) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Cohort Quiz Test Staff", email=f"cq-staff-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles), status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name="Cohort Quiz Test Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name="Cohort Quiz Test Student", email=f"cq-student-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort_with_checklist(db, *, author) -> tuple[Cohort, LmsProgram]:
    program = Program(
        id=uuid.uuid4(), code=f"CQR-{uuid.uuid4().hex[:8]}", name="Cohort Quiz Router Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort Quiz Router Test Cohort", status="running")
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Router Test Checklist")
    db.add(lms_program)
    await db.flush()
    return cohort, lms_program


async def _template_with_one_question(db, *, author) -> uuid.UUID:
    template = await cohort_quiz_service.create_template(
        db, body=CohortQuizTemplateCreate(name="Router Test Template"), created_by=author.id,
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
    return template.id


async def _quiz_item(db, *, lms_program: LmsProgram, template_id: uuid.UUID) -> LmsProgramItem:
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="quiz", title="Knowledge check", cohort_quiz_template_id=template_id,
    )
    db.add(item)
    await db.flush()
    return item


# ── student flow ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_returns_questions_without_the_correct_answer(db, client):
    author = await _staff(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    template_id = await _template_with_one_question(db, author=author)
    item = await _quiz_item(db, lms_program=lms_program, template_id=template_id)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/quiz/start", headers=_headers(student),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["total"] == 1
    assert len(body["questions"][0]["options"]) == 2
    assert "is_correct" not in body["questions"][0]["options"][0]


@pytest.mark.asyncio
async def test_submit_grades_and_marks_the_checklist_item_done(db, client):
    author = await _staff(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    template_id = await _template_with_one_question(db, author=author)
    item = await _quiz_item(db, lms_program=lms_program, template_id=template_id)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    start_resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/quiz/start", headers=_headers(student),
    )
    question = start_resp.json()["questions"][0]
    correct_position = question["options"].index("Solar panels")

    submit_resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/quiz/submit", headers=_headers(student),
        json={"answers": [{"question_id": question["question_id"], "selected_option_index": correct_position}]},
    )
    assert submit_resp.status_code == 200
    result = submit_resp.json()
    assert result["status"] == "submitted"
    assert result["score"] == 1
    assert result["topic_breakdown"]["EPS"] == {"correct": 1, "total": 1}

    checklist = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    quiz_item_out = next(i for i in checklist.json()["items"] if i["id"] == str(item.id))
    assert quiz_item_out["status"] == "done"


@pytest.mark.asyncio
async def test_cannot_self_check_a_quiz_item(db, client):
    author = await _staff(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    template_id = await _template_with_one_question(db, author=author)
    item = await _quiz_item(db, lms_program=lms_program, template_id=template_id)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(f"/lms/programs/{assignment.id}/items/{item.id}/complete", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_result_404s_before_the_quiz_is_submitted(db, client):
    author = await _staff(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    template_id = await _template_with_one_question(db, author=author)
    item = await _quiz_item(db, lms_program=lms_program, template_id=template_id)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.get(f"/lms/programs/{assignment.id}/items/{item.id}/quiz/result", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


# ── admin authoring smoke test ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_can_author_a_bank_question_and_build_a_template(db, client):
    facilitator = await _staff(db, roles=("facilitator",))
    await db.commit()

    create_resp = await client.post(
        "/lms/admin/cohort-quiz/questions", headers=_headers(facilitator),
        json={
            "topic": "ADCS", "difficulty": "Medium", "time_limit_seconds": 30,
            "prompt": "What does ADCS stand for?",
            "options": [
                {"text": "Attitude Determination and Control System", "is_correct": True},
                {"text": "Automated Data Compression System", "is_correct": False},
            ],
        },
    )
    assert create_resp.status_code == 201
    question_id = create_resp.json()["id"]

    template_resp = await client.post(
        "/lms/admin/cohort-quiz/templates", headers=_headers(facilitator), json={"name": "ADCS Basics"},
    )
    assert template_resp.status_code == 201
    template_id = template_resp.json()["id"]

    add_resp = await client.post(
        f"/lms/admin/cohort-quiz/templates/{template_id}/questions",
        headers=_headers(facilitator), json={"question_id": question_id},
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["question_count"] == 1

    list_resp = await client.get("/lms/admin/cohort-quiz/templates", headers=_headers(facilitator))
    assert any(t["id"] == template_id and t["question_count"] == 1 for t in list_resp.json())


@pytest.mark.asyncio
async def test_a_retired_template_cannot_be_assigned_to_a_new_item_but_stays_editable_on_an_existing_one(db, client):
    author = await _staff(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    template_id = await _template_with_one_question(db, author=author)
    item = await _quiz_item(db, lms_program=lms_program, template_id=template_id)
    await db.commit()

    retire_resp = await client.patch(
        f"/lms/admin/cohort-quiz/templates/{template_id}", headers=_headers(author), json={"is_active": False},
    )
    assert retire_resp.status_code == 200

    # A brand-new item can no longer be pointed at the now-retired template.
    create_resp = await client.post(
        f"/lms/admin/programs/{lms_program.id}/items", headers=_headers(author),
        json={"item_type": "quiz", "title": "Second quiz", "cohort_quiz_template_id": str(template_id)},
    )
    assert create_resp.status_code == 400

    # The existing item, already pointing at it, stays editable for its
    # other fields — retiring a template doesn't freeze what already has it.
    update_resp = await client.patch(
        f"/lms/admin/programs/{lms_program.id}/items/{item.id}", headers=_headers(author),
        json={"item_type": "quiz", "title": "Knowledge check (renamed)", "cohort_quiz_template_id": str(template_id), "optional": True},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["title"] == "Knowledge check (renamed)"


@pytest.mark.asyncio
async def test_student_quiz_breakdown_endpoint_reflects_a_submitted_attempt(db, client):
    author = await _staff(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    template_id = await _template_with_one_question(db, author=author)
    item = await _quiz_item(db, lms_program=lms_program, template_id=template_id)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    start_resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/quiz/start", headers=_headers(student),
    )
    question = start_resp.json()["questions"][0]
    correct_position = question["options"].index("Solar panels")
    await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/quiz/submit", headers=_headers(student),
        json={"answers": [{"question_id": question["question_id"], "selected_option_index": correct_position}]},
    )

    resp = await client.get(f"/lms/admin/students/{student.id}/quiz-breakdown", headers=_headers(author))
    assert resp.status_code == 200
    assert resp.json()["topic_breakdown"]["EPS"] == {"correct": 1, "total": 1}
