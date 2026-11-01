import io
import uuid
import pytest
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.instructor_assessment.config import AssessmentConfig
from app.models.sessions.pre_session_quiz import PreSessionQuizPreset, PreSessionQuizQuestion
from app.models.user import User


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Importer Ops",
        email=f"imp-ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_download_question_import_template(db: AsyncSession, client):
    ops = await _ops(db)
    await db.commit()

    resp = await client.get(
        "/sessions/pre-quiz/questions/import/template",
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_200_OK
    assert "spreadsheetml" in resp.headers["content-type"]
    assert len(resp.content) > 1000


@pytest.mark.asyncio
async def test_import_questions_from_csv(db: AsyncSession, client):
    ops = await _ops(db)
    await db.commit()

    csv_content = """SPACEPOINT | INSTRUCTOR PRE-WORKSHOP MCQ ASSESSMENT,,,,,,,,,
31 questions • 8 Instructor Readiness • 18 SatKit Inspection • 5 Practical Scenarios | Answer key included,,,,,,,,,
,,,,,,,,,
Question ID,Section,Question,Option A,Option B,Option C,Option D,Correct Letter,Correct Answer,Points
A01,A – Instructor Readiness,A student struggles with a concept that the slides assume they already know. What should the instructor do?,Continue because the concept is not in the slides,Explain the foundational concept before continuing,Ask the student to skip the activity,Tell the student to study it after the workshop,B,Explain the foundational concept before continuing,1
B01,B – SatKit Inspection,Which sequence of standoff heights is specified from the bottom?,"10, 20, 10, 20","10, 10, 9, 20, 10, 20, 10","20, 20, 10, 10, 9, 9",All standoffs must be equal,B,"10, 10, 9, 20, 10, 20, 10",1
C01,C – Practical Scenarios,A completed SatKit does not power on. What should the instructor check first?,Replace the ESP32 without testing,Change the code immediately,Disconnect every sensor and guess the cause,"Inspect power connections, polarity and the power supply before further troubleshooting",D,"Inspect power connections, polarity and the power supply before further troubleshooting",1
"""
    files = {"file": ("test_questions.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = await client.post(
        "/sessions/pre-quiz/questions/import",
        files=files,
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    data = resp.json()
    assert data["created"] == 3
    assert len(data["errors"]) == 0
    assert len(data["questions"]) == 3

    # Verify fields
    q_map = {q["code"]: q for q in data["questions"]}
    assert "A01" in q_map
    assert q_map["A01"]["topic"] == "A – Instructor Readiness"
    assert q_map["A01"]["options"][1]["is_correct"] is True

    assert "B01" in q_map
    assert q_map["B01"]["topic"] == "B – SatKit Inspection"
    assert q_map["B01"]["options"][1]["is_correct"] is True

    assert "C01" in q_map
    assert q_map["C01"]["topic"] == "C – Practical Scenarios"
    assert q_map["C01"]["options"][3]["is_correct"] is True


@pytest.mark.asyncio
async def test_create_pre_assessment_preset_syncs_to_assessment_config(db: AsyncSession, client):
    ops = await _ops(db)
    await db.commit()

    payload = {
        "name": "Applicant Screening Preset Alpha",
        "description": "Applicant screening test for new instructors",
        "preset_type": "pre_assessment",
        "draw_size": 15,
        "critical_floor": 4,
        "passing_score_percent": 85,
        "question_ids": [],
        "phases": [],
        "reference_attachments": [],
    }
    resp = await client.post(
        "/sessions/pre-quiz/presets",
        json=payload,
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    data = resp.json()
    preset_id = uuid.UUID(data["id"])

    assert data["preset_type"] == "pre_assessment"
    assert data["draw_size"] == 15
    assert data["critical_floor"] == 4
    assert data["passing_score_percent"] == 85

    # Verify synced AssessmentConfig exists
    ac = await db.get(AssessmentConfig, preset_id)
    assert ac is not None
    assert ac.name == "Applicant Screening Preset Alpha"
    assert ac.draw_size == 15
    assert ac.critical_floor == 4
