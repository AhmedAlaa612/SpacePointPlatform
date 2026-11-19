"""Regression tests for the Pre-Session Quiz / Question Bank bulk importer."""

import io
import uuid

import openpyxl
import pytest
from sqlalchemy import select

from app.models.instructor_assessment.config import AssessmentConfig, AssessmentQuestion
from app.models.sessions.pre_session_quiz import PreSessionQuizQuestion
from app.models.user import User
from app.services.sessions import pre_session_quiz as svc
from app.services.sessions.pre_session_quiz_importer import (
    generate_question_template_xlsx,
    parse_question_import_bytes,
)


def _xlsx_from_rows(rows: list[list[object]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_official_template_round_trip_preserves_prompt_not_question_id():
    """The generated template puts 'Question ID' before 'Scenario / Question'.
    Previously, 'prompt' matched 'Question ID' via the 'question ' prefix,
    replacing the scenario text with the ID code (e.g. 'S01' / 'A06')."""
    template_bytes = generate_question_template_xlsx()

    items, errors = parse_question_import_bytes(template_bytes, "spacepoint_question_bank_template.xlsx")

    assert errors == []
    assert len(items) == 3

    s01 = items[0]
    assert s01.code == "S01"
    assert s01.topic == "Safety & PPE"
    assert s01.prompt.startswith("Students are excited to begin integration")
    assert s01.prompt != s01.code
    assert s01.title.startswith("[S01] Students are excited")
    assert s01.critical is True
    assert [o["is_correct"] for o in s01.options] == [False, False, False, True]


def test_custom_prefix_question_header_does_not_steal_question_id():
    xlsx = _xlsx_from_rows([
        ["Question ID", "Category", "Question Text", "Option A", "Option B", "Correct Answer"],
        ["A06", "A – Instructor Readiness", "What should you do when one team finishes early?", "Stop all teams", "Provide an extension task", "B"],
    ])

    items, errors = parse_question_import_bytes(xlsx, "readiness.xlsx")

    assert errors == []
    assert len(items) == 1
    assert items[0].code == "A06"
    assert items[0].topic == "A – Instructor Readiness"
    assert items[0].prompt == "What should you do when one team finishes early?"
    assert items[0].options[1] == {"text": "Provide an extension task", "is_correct": True}


def test_snake_case_csv_headers_supported():
    csv_bytes = (
        "question_id,category,question_text,option_a,option_b,correct_answer,is_critical\n"
        "A07,Instructor Readiness,What must be reviewed before session start?,End time only,Daily flow and checkpoints,B,Yes\n"
    ).encode("utf-8")

    items, errors = parse_question_import_bytes(csv_bytes, "questions.csv")

    assert errors == []
    assert len(items) == 1
    assert items[0].code == "A07"
    assert items[0].prompt == "What must be reviewed before session start?"
    assert items[0].critical is True


@pytest.mark.asyncio
async def test_reimport_repairs_broken_prompt_and_mirrored_assessment_question(db):
    user = User(
        id=uuid.uuid4(),
        full_name="Facilitator",
        email=f"fac_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        roles=["facilitator"],
    )
    db.add(user)
    await db.flush()

    q_id = uuid.uuid4()
    broken_q = PreSessionQuizQuestion(
        id=q_id,
        code="A06",
        topic="A – Instructor Readiness",
        question_type="mcq",
        title="[A06] A06...",
        prompt="A06",
        options=[
            {"text": "Stop all teams immediately", "is_correct": False},
            {"text": "Provide an extension task", "is_correct": True},
        ],
        critical=False,
        points=1,
        is_active=True,
        created_by=user.id,
    )
    ac = AssessmentConfig(id=uuid.uuid4(), name="Test Bank", created_by=user.id)
    aq = AssessmentQuestion(
        id=q_id,
        config_id=ac.id,
        category="A – Instructor Readiness",
        prompt="A06",
        options=broken_q.options,
        critical=False,
        is_active=True,
    )
    db.add_all([broken_q, ac, aq])
    await db.commit()

    xlsx = _xlsx_from_rows([
        ["Question ID", "Category / Topic", "Scenario / Question", "Option A", "Option B", "Option C", "Option D", "Correct Answer"],
        [
            "A06",
            "A – Instructor Readiness",
            "One team finishes early while another is struggling. What should you do?",
            "Stop all teams immediately",
            "Let the early team leave",
            "Provide an extension task while supporting the struggling team",
            "Complete the struggling team's assembly for them",
            "C",
        ],
    ])

    count, errors, questions = await svc.import_questions_from_file(db, xlsx, "fixed.xlsx", user)

    assert count == 1
    assert errors == []
    assert len(questions) == 1
    assert questions[0].id == q_id
    assert questions[0].prompt == "One team finishes early while another is struggling. What should you do?"
    assert questions[0].title == "[A06] One team finishes early while another is strugglin..."

    refreshed_aq = await db.get(AssessmentQuestion, q_id)
    assert refreshed_aq is not None
    assert refreshed_aq.prompt == "One team finishes early while another is struggling. What should you do?"

    total_rows = (await db.execute(select(PreSessionQuizQuestion).where(PreSessionQuizQuestion.code == "A06"))).scalars().all()
    assert len(total_rows) == 1
