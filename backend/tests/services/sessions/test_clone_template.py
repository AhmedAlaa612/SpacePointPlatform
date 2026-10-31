"""Create-from-template clones for Programs & Cohorts.

Covers POST /sessions/programs/{id}/clone and POST /sessions/cohorts/{id}/clone,
including cross-program cohort cloning and the silent-judge invariant
(CompetitionJudge rows copied with onboarding_sent_at=None and zero emails).
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.competitions.judging import (
    CompetitionJudge,
    CompetitionRubric,
    CompetitionRubricCriterion,
)
from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.config import AssessmentConfig
from app.models.lms.program import LmsProgram, LmsProgramCohortOverride, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.material import Material
from app.models.sessions.program import Program
from app.models.sessions.program_opening import ProgramOpening
from app.models.user import User


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Clone Test Ops", email=f"clone-ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _role(db, name: str = "Lead") -> DeliveryRole:
    role = DeliveryRole(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:4]}", sort_order=1)
    db.add(role)
    await db.flush()
    return role


async def _assessment_config(db) -> AssessmentConfig:
    cfg = AssessmentConfig(
        id=uuid.uuid4(), name=f"Cfg {uuid.uuid4().hex[:4]}",
    )
    db.add(cfg)
    await db.flush()
    return cfg


async def _program(db, *, code: str | None = None, program_type: str = "workshop") -> Program:
    program = Program(
        id=uuid.uuid4(), code=code or f"CL-{uuid.uuid4().hex[:8]}", name="Source Program",
        program_type=program_type, pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    return program


async def _cohort(db, program_id, *, name: str = "Source Cohort") -> Cohort:
    cohort = Cohort(id=uuid.uuid4(), program_id=program_id, name=name, status="planned")
    db.add(cohort)
    await db.flush()
    return cohort


@pytest.mark.asyncio
async def test_clone_program_success(db, client):
    """New program created with unique code; openings, materials and
    checklist items duplicated with new owner IDs."""
    ops = await _ops(db)
    role = await _role(db)
    cfg = await _assessment_config(db)
    source = await _program(db)
    source.default_assessment_config_id = cfg.id
    await db.flush()

    db.add(ProgramOpening(
        id=uuid.uuid4(), program_id=source.id, role_id=role.id,
        slots=2, amount_aed=100, notes="n", created_by=ops.id,
    ))
    db.add(Material(
        id=uuid.uuid4(), program_id=source.id, title="Handbook",
        url="https://example.com/handbook.pdf", sort_order=1, uploaded_by=ops.id,
    ))
    lms = LmsProgram(id=uuid.uuid4(), program_id=source.id, name="Checklist")
    db.add(lms)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms.id, position=1,
        item_type="manual", title="Step 1",
    ))
    await db.flush()

    new_code = f"CL-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        f"/sessions/programs/{source.id}/clone",
        json={"name": "Cloned Program", "code": new_code},
        headers=_headers(ops),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == new_code
    assert body["name"] == "Cloned Program"
    assert body["default_assessment_config_id"] == str(cfg.id)
    new_id = uuid.UUID(body["id"])

    openings = (await db.execute(
        select(ProgramOpening).where(ProgramOpening.program_id == new_id)
    )).scalars().all()
    assert len(openings) == 1
    assert openings[0].role_id == role.id
    assert openings[0].slots == 2
    assert openings[0].id is not None

    materials = (await db.execute(
        select(Material).where(Material.program_id == new_id)
    )).scalars().all()
    assert len(materials) == 1
    assert materials[0].title == "Handbook"

    new_lms = await db.scalar(select(LmsProgram).where(LmsProgram.program_id == new_id))
    assert new_lms is not None
    items = (await db.execute(
        select(LmsProgramItem).where(
            LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == new_lms.id,
        )
    )).scalars().all()
    assert len(items) == 1
    assert items[0].title == "Step 1"


@pytest.mark.asyncio
async def test_clone_program_code_collision_409(db, client):
    """Cloning with an already-used code throws 409 Conflict."""
    ops = await _ops(db)
    source = await _program(db, code=f"SRC-{uuid.uuid4().hex[:6]}")
    await _program(db, code="TAKEN-CODE-1")

    resp = await client.post(
        f"/sessions/programs/{source.id}/clone",
        json={"name": "Copy", "code": "TAKEN-CODE-1"},
        headers=_headers(ops),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_clone_cohort_intra_program(db, client):
    """Clone a cohort into the same program — basics and openings duplicated."""
    ops = await _ops(db)
    role = await _role(db)
    program = await _program(db)
    source = await _cohort(db, program.id)
    source.capacity = 25
    source.visibility = "private"
    source.submission_windows = [{"id": "early", "name": "Early Bird"}]
    await db.flush()
    db.add(CohortOpening(
        id=uuid.uuid4(), cohort_id=source.id, role_id=role.id, slots=3, created_by=ops.id,
    ))
    db.add(Material(
        id=uuid.uuid4(), cohort_id=source.id, title="Slides",
        url="https://example.com/slides", sort_order=1, uploaded_by=ops.id,
    ))
    await db.flush()

    resp = await client.post(
        f"/sessions/cohorts/{source.id}/clone",
        json={"name": "Copy Cohort", "program_id": str(program.id)},
        headers=_headers(ops),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["program_id"] == str(program.id)
    assert body["status"] == "planned"
    new_id = uuid.UUID(body["id"])

    new_cohort = await db.get(Cohort, new_id)
    assert new_cohort.capacity == 25
    assert new_cohort.visibility == "private"
    assert new_cohort.submission_windows == [{"id": "early", "name": "Early Bird"}]

    openings = (await db.execute(
        select(CohortOpening).where(CohortOpening.cohort_id == new_id)
    )).scalars().all()
    assert len(openings) == 1
    assert openings[0].role_id == role.id

    materials = (await db.execute(
        select(Material).where(Material.cohort_id == new_id)
    )).scalars().all()
    assert len(materials) == 1


@pytest.mark.asyncio
async def test_clone_cohort_cross_program(db, client):
    """Clone a cohort from Program Y into Program X — program_id points at X
    and the LMS override is cleanly attached to the new cohort."""
    ops = await _ops(db)
    program_x = await _program(db)
    program_y = await _program(db)
    # Target program gets its own default checklist so the override has a parent.
    target_lms = LmsProgram(id=uuid.uuid4(), program_id=program_x.id, name="X Checklist")
    db.add(target_lms)
    await db.flush()
    # Source program checklist with one item.
    source_lms = LmsProgram(id=uuid.uuid4(), program_id=program_y.id, name="Y Checklist")
    db.add(source_lms)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=source_lms.id, position=1,
        item_type="manual", title="Y Step",
    ))
    source = await _cohort(db, program_y.id)
    await db.flush()

    resp = await client.post(
        f"/sessions/cohorts/{source.id}/clone",
        json={"name": "X Copy", "program_id": str(program_x.id), "carry": ["checklist"]},
        headers=_headers(ops),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["program_id"] == str(program_x.id)
    new_id = uuid.UUID(body["id"])

    override = await db.scalar(
        select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id == new_id)
    )
    assert override is not None
    assert override.lms_program_id == target_lms.id
    items = (await db.execute(
        select(LmsProgramItem).where(
            LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id,
        )
    )).scalars().all()
    assert len(items) == 1
    assert items[0].title == "Y Step"


@pytest.mark.asyncio
async def test_clone_competition_cohort_silent_judges(db, client, monkeypatch):
    """Competition judges are copied 100% silently: rows inserted with
    onboarding_sent_at=None and NO emails sent."""
    ops = await _ops(db)
    program = await _program(db, program_type="competition")
    source = await _cohort(db, program.id)

    rubric = CompetitionRubric(
        id=uuid.uuid4(), program_id=program.id, cohort_id=source.id, name="Final Rubric",
    )
    db.add(rubric)
    await db.flush()
    db.add(CompetitionRubricCriterion(
        id=uuid.uuid4(), rubric_id=rubric.id, key="design",
        label="Design", max_points=30, position=0,
    ))
    judge_user = User(
        id=uuid.uuid4(), full_name="Judge", email=f"judge-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["judge"], status="active",
    )
    db.add(judge_user)
    await db.flush()
    db.add(CompetitionJudge(id=uuid.uuid4(), cohort_id=source.id, user_id=judge_user.id))
    await db.flush()

    # If ANY onboarding email path is hit, fail loudly.
    async def _fail_email(*args, **kwargs):
        raise AssertionError("judge onboarding email must not be sent during clone")

    import app.services.competitions.judges as judges_svc

    monkeypatch.setattr(judges_svc, "send_judge_onboarding_email", _fail_email)

    resp = await client.post(
        f"/sessions/cohorts/{source.id}/clone",
        json={"name": "Final Copy", "program_id": str(program.id)},
        headers=_headers(ops),
    )
    assert resp.status_code == 201, resp.text
    new_id = uuid.UUID(resp.json()["id"])

    judges = (await db.execute(
        select(CompetitionJudge).where(CompetitionJudge.cohort_id == new_id)
    )).scalars().all()
    assert len(judges) == 1
    assert judges[0].user_id == judge_user.id
    assert judges[0].onboarding_sent_at is None

    new_rubric = await db.scalar(
        select(CompetitionRubric).where(CompetitionRubric.cohort_id == new_id)
    )
    assert new_rubric is not None
    criteria = (await db.execute(
        select(CompetitionRubricCriterion).where(CompetitionRubricCriterion.rubric_id == new_rubric.id)
    )).scalars().all()
    assert len(criteria) == 1
    assert criteria[0].key == "design"

    # No assessment rows should have been invented for this clone.
    assignments = (await db.execute(
        select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == new_id)
    )).scalars().all()
    assert assignments == []


@pytest.mark.asyncio
async def test_clone_cohort_competition_to_workshop(db, client):
    """Cloning a competition cohort into a standard workshop clones standard
    items, but strictly omits competition-specific features (rubric, judges,
    submission windows)."""
    ops = await _ops(db)
    comp_program = await _program(db, program_type="competition")
    workshop_program = await _program(db, program_type="workshop")

    source = await _cohort(db, comp_program.id, name="Comp Cohort")
    source.submission_windows = [{"id": "window-1", "name": "Early Bird"}]
    await db.flush()

    rubric = CompetitionRubric(
        id=uuid.uuid4(), program_id=comp_program.id, cohort_id=source.id, name="Comp Rubric",
    )
    db.add(rubric)
    await db.flush()
    db.add(CompetitionRubricCriterion(
        id=uuid.uuid4(), rubric_id=rubric.id, key="creativity",
        label="Creativity", max_points=20, position=0,
    ))
    judge_user = User(
        id=uuid.uuid4(), full_name="Judge Comp", email=f"judge-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["judge"], status="active",
    )
    db.add(judge_user)
    await db.flush()
    db.add(CompetitionJudge(id=uuid.uuid4(), cohort_id=source.id, user_id=judge_user.id))
    await db.flush()

    resp = await client.post(
        f"/sessions/cohorts/{source.id}/clone",
        json={
            "name": "Workshop Cloned from Comp",
            "program_id": str(workshop_program.id),
            "carry": ["basics", "windows", "roles", "materials", "assessment", "checklist", "rubric", "judges"],
        },
        headers=_headers(ops),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["program_id"] == str(workshop_program.id)
    new_id = uuid.UUID(body["id"])

    # Submission windows must be empty for standard workshop
    cloned_cohort = await db.get(Cohort, new_id)
    assert cloned_cohort.submission_windows == []

    # Rubric must NOT be created
    new_rubric = await db.scalar(
        select(CompetitionRubric).where(CompetitionRubric.cohort_id == new_id)
    )
    assert new_rubric is None

    # Judges must NOT be created
    judges = (await db.execute(
        select(CompetitionJudge).where(CompetitionJudge.cohort_id == new_id)
    )).scalars().all()
    assert judges == []


@pytest.mark.asyncio
async def test_clone_cohort_workshop_to_competition(db, client):
    """Cloning a workshop cohort into a competition succeeds, carrying standard
    cohort features without inventing competition data."""
    ops = await _ops(db)
    workshop_program = await _program(db, program_type="workshop")
    comp_program = await _program(db, program_type="competition")

    source = await _cohort(db, workshop_program.id, name="Workshop Cohort")
    source.capacity = 25
    await db.flush()

    resp = await client.post(
        f"/sessions/cohorts/{source.id}/clone",
        json={
            "name": "Comp Cloned from Workshop",
            "program_id": str(comp_program.id),
            "carry": ["basics", "windows", "roles", "materials", "assessment", "checklist", "rubric", "judges"],
        },
        headers=_headers(ops),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["program_id"] == str(comp_program.id)
    assert body["capacity"] == 25
    new_id = uuid.UUID(body["id"])

    # Cloned cohort has empty windows since source had none
    cloned_cohort = await db.get(Cohort, new_id)
    assert cloned_cohort.submission_windows == []

    # Rubric is None since source had none
    new_rubric = await db.scalar(
        select(CompetitionRubric).where(CompetitionRubric.cohort_id == new_id)
    )
    assert new_rubric is None

    # Judges are empty
    judges = (await db.execute(
        select(CompetitionJudge).where(CompetitionJudge.cohort_id == new_id)
    )).scalars().all()
    assert judges == []
