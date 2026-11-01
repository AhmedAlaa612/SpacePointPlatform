import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.pre_session_quiz import (
    PreSessionQuizAssignment,
    PreSessionQuizAttempt,
    PreSessionQuizPhaseTrial,
    PreSessionQuizPreset,
    PreSessionQuizQuestion,
)
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.schemas.sessions.pre_session_quiz import PhaseTrialSubmitIn, PreSessionQuizAnswerIn
from app.services.sessions import delivery as delivery_svc
from app.services.sessions import pre_session_quiz as svc


@pytest.fixture
async def sample_user(db) -> User:
    u = User(
        id=uuid.uuid4(),
        full_name="Lead Instructor",
        email=f"inst_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="test",
        roles=["instructor"],
    )
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def sample_cohort_and_sessions(db, sample_user) -> tuple[Program, Cohort, Session, Session]:
    role = DeliveryRole(id=uuid.uuid4(), name="Lead Instructor")
    db.add(role)
    await db.flush()

    program = Program(
        id=uuid.uuid4(),
        code=f"PRG-{uuid.uuid4().hex[:6]}",
        name="Cubesat Flight Workshop",
        program_type="workshop",
        pricing_model="free",
        active=True,
    )
    db.add(program)
    await db.flush()

    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Flight Alpha",
        status="running",
    )
    db.add(cohort)
    await db.flush()

    s1 = Session(
        id=uuid.uuid4(),
        cohort_id=cohort.id,
        meeting_date=date.today(),
        title="Session 1: Power & Bus",
    )
    s2 = Session(
        id=uuid.uuid4(),
        cohort_id=cohort.id,
        meeting_date=date.today() + timedelta(days=7),
        title="Session 2: Payloads",
    )
    db.add_all([s1, s2])
    await db.flush()

    si1 = SessionInstructor(session_id=s1.id, user_id=sample_user.id, role_id=role.id)
    si2 = SessionInstructor(session_id=s2.id, user_id=sample_user.id, role_id=role.id)
    db.add_all([si1, si2])
    await db.flush()

    return program, cohort, s1, s2


@pytest.fixture
async def sample_pipeline_preset(db) -> tuple[PreSessionQuizPreset, PreSessionQuizQuestion, PreSessionQuizQuestion]:
    # Tricky question: is_other_correct = True
    q_tricky = PreSessionQuizQuestion(
        id=uuid.uuid4(),
        topic="CDHS",
        question_type="pinout_table",
        title="J6 MicroSD Discrepancy",
        prompt="Verify pinout connections for Connector J6. Note any datasheet errors.",
        table_config={
            "connector_name": "J6",
            "header_subtitle": "J61..J66",
            "columns": ["1", "2", "3"],
            "rows": [
                {"label": "Pin 1", "cells": [{"text": "3V3", "is_correct": False}, {"text": "GND", "is_correct": False}, {"text": "MOSI", "is_correct": False}]},
            ],
        },
        allow_other=True,
        is_other_correct=True,
        explanation="Datasheet reverses MOSI and MISO pins on schematic revision 1.2.",
        is_active=True,
    )

    q_mcq = PreSessionQuizQuestion(
        id=uuid.uuid4(),
        topic="Addressing",
        question_type="mcq",
        title="I2C Address Collision",
        prompt="What happens if two devices share the same 7-bit slave address?",
        options=[
            {"text": "Bus contention and corrupted reads", "is_correct": True},
            {"text": "Secondary device self-reassigns", "is_correct": False},
        ],
        allow_other=False,
        is_other_correct=False,
        is_active=True,
    )
    db.add_all([q_tricky, q_mcq])
    await db.flush()

    preset = PreSessionQuizPreset(
        id=uuid.uuid4(),
        name="Test 3-Phase Pipeline",
        description="Explore -> Matching -> Pinout",
        question_ids=[str(q_tricky.id), str(q_mcq.id)],
        reference_attachments=[
            {"id": "ds-esp32", "title": "ESP32", "url": "/files/esp32.pdf", "doc_type": "datasheet", "subsystem_tag": "CDHS"},
            {"id": "ds-ina219", "title": "INA219", "url": "/files/ina219.pdf", "doc_type": "datasheet", "subsystem_tag": "EPS"},
        ],
        phases=[
            {
                "id": "phase-explore",
                "phase_type": "explore_datasheets",
                "title": "Explore Data Sheets",
                "instructions": ["Review datasheets"],
                "pass_percentage": 100,
                "cooldown_seconds": 0,
                "show_correct_on_fail": False,
                "show_explanation_on_fail": False,
                "show_bucket_target_counts": True,
                "allow_datasheet_lookup": True,
                "question_ids": [],
            },
            {
                "id": "phase-matching",
                "phase_type": "subsystem_matching",
                "title": "Match Subsystems",
                "instructions": ["Drop into buckets"],
                "pass_percentage": 100,
                "cooldown_seconds": 900,  # 15 minutes
                "show_correct_on_fail": False,
                "show_explanation_on_fail": False,
                "show_bucket_target_counts": True,
                "allow_datasheet_lookup": True,
                "question_ids": [],
                "matching_config": {
                    "buckets": [
                        {"id": "CDHS", "label": "CDHS"},
                        {"id": "EPS", "label": "EPS"},
                    ],
                    "items": [
                        {"datasheet_id": "ds-esp32", "correct_bucket_id": "CDHS"},
                        {"datasheet_id": "ds-ina219", "correct_bucket_id": "EPS"},
                    ],
                },
            },
            {
                "id": "phase-quiz",
                "phase_type": "quiz",
                "title": "Hardware Quiz",
                "instructions": ["Answer pinout and addressing"],
                "pass_percentage": 100,
                "cooldown_seconds": 60,  # 1 minute
                "show_correct_on_fail": False,
                "show_explanation_on_fail": False,
                "show_bucket_target_counts": True,
                "allow_datasheet_lookup": True,
                "question_ids": [str(q_tricky.id), str(q_mcq.id)],
            },
        ],
        is_active=True,
    )
    db.add(preset)
    await db.flush()
    return preset, q_tricky, q_mcq


@pytest.mark.asyncio
async def test_full_readiness_pipeline_and_session_gate(
    db, sample_user, sample_cohort_and_sessions, sample_pipeline_preset
):
    program, cohort, s1, s2 = sample_cohort_and_sessions
    preset, q_tricky, q_mcq = sample_pipeline_preset

    # Assign preset to cohort
    assign = PreSessionQuizAssignment(
        id=uuid.uuid4(),
        cohort_id=cohort.id,
        preset_id=preset.id,
    )
    db.add(assign)
    await db.commit()

    # 1. Verify session start is blocked before pipeline completion
    with pytest.raises(HTTPException) as exc_info:
        await delivery_svc.start_session(db, s1.id, sample_user)
    assert exc_info.value.status_code == 400
    assert "Cohort Readiness Quiz" in str(exc_info.value.detail)

    # 2. Phase 1: Explore Datasheets - start and submit
    await svc.start_cohort_phase(db, cohort.id, "phase-explore", sample_user)
    p1_res = await svc.submit_cohort_phase(
        db, cohort.id, "phase-explore", sample_user, PhaseTrialSubmitIn(client_duration_seconds=10)
    )
    assert p1_res["trial"]["passed"] is True
    assert p1_res["attempt"]["current_phase_index"] == 1

    # 3. Phase 2: Subsystem Matching - fail with incorrect placements -> 15 min cooldown
    await svc.start_cohort_phase(db, cohort.id, "phase-matching", sample_user)
    p2_fail_res = await svc.submit_cohort_phase(
        db,
        cohort.id,
        "phase-matching",
        sample_user,
        PhaseTrialSubmitIn(
            client_duration_seconds=25,
            matching_placements={"ds-esp32": "EPS", "ds-ina219": "CDHS"},  # Both wrong
        ),
    )
    assert p2_fail_res["trial"]["passed"] is False
    assert p2_fail_res["trial"]["score_pct"] == 0
    assert p2_fail_res["attempt"]["status"] == "cooldown_locked"
    assert p2_fail_res["attempt"]["locked_until"] is not None

    # Cooldown gate check: attempting to restart immediately raises HTTP 429
    with pytest.raises(HTTPException) as exc_429:
        await svc.start_cohort_phase(db, cohort.id, "phase-matching", sample_user)
    assert exc_429.value.status_code == 429

    # Ops escape hatch / manual unlock
    attempt_id = p2_fail_res["attempt"]["id"]
    unlocked = await svc.unlock_cooldown(db, attempt_id, sample_user)
    assert unlocked["locked_until"] is None
    assert unlocked["status"] == "in_progress"

    # Now pass Phase 2 with 100% correct matching
    p2_pass_res = await svc.submit_cohort_phase(
        db,
        cohort.id,
        "phase-matching",
        sample_user,
        PhaseTrialSubmitIn(
            client_duration_seconds=15,
            matching_placements={"ds-esp32": "CDHS", "ds-ina219": "EPS"},
        ),
    )
    assert p2_pass_res["trial"]["passed"] is True
    assert p2_pass_res["trial"]["score_pct"] == 100
    assert p2_pass_res["attempt"]["current_phase_index"] == 2

    # 4. Phase 3: Quiz with tricky "Other" question
    await svc.start_cohort_phase(db, cohort.id, "phase-quiz", sample_user)

    # Submitting with tricky question answered via "Other" + explanation auto-grades as 100%
    p3_pass_res = await svc.submit_cohort_phase(
        db,
        cohort.id,
        "phase-quiz",
        sample_user,
        PhaseTrialSubmitIn(
            client_duration_seconds=40,
            answers=[
                PreSessionQuizAnswerIn(
                    question_id=q_tricky.id,
                    chose_other=True,
                    other_text="MOSI and MISO pins are flipped on connector J6 schematic.",
                ),
                PreSessionQuizAnswerIn(
                    question_id=q_mcq.id,
                    selected_option_index=0,  # Correct MCQ option
                ),
            ],
        ),
    )
    assert p3_pass_res["trial"]["passed"] is True
    assert p3_pass_res["trial"]["score_pct"] == 100
    assert p3_pass_res["attempt"]["status"] == "completed"

    # 5. Verify Session 1 can now start
    started_s1 = await delivery_svc.start_session(db, s1.id, sample_user)
    assert started_s1.started_at is not None

    # 6. Verify Session 2 in the same cohort can also start without re-taking the quiz!
    started_s2 = await delivery_svc.start_session(db, s2.id, sample_user)
    assert started_s2.started_at is not None

    # 7. Verify revisiting an earlier phase does NOT regress progress or revert "completed" status
    revisit_start = await svc.start_cohort_phase(db, cohort.id, "phase-explore", sample_user)
    assert revisit_start["status"] == "completed"

    revisit_sub = await svc.submit_cohort_phase(
        db, cohort.id, "phase-explore", sample_user, PhaseTrialSubmitIn(client_duration_seconds=5)
    )
    assert revisit_sub["attempt"]["status"] == "completed"
    assert revisit_sub["attempt"]["current_phase_index"] >= 3


@pytest.mark.asyncio
async def test_datasheet_library_crud_and_preset_attachment(db, sample_user):
    from app.schemas.sessions.pre_session_quiz import (
        PreSessionQuizDatasheetIn,
        PreSessionQuizDatasheetUpdateIn,
        PreSessionQuizPresetIn,
    )

    # 1. Create datasheets in the central library
    ds1 = await svc.create_datasheet(
        db,
        PreSessionQuizDatasheetIn(
            title="ESP32-WROOM-32D Technical Reference",
            url="/storage/esp32.pdf",
            doc_type="datasheet",
            subsystem_tag="CDHS",
            description="CDHS compute module datasheet",
        ),
        sample_user,
    )
    ds2 = await svc.create_datasheet(
        db,
        PreSessionQuizDatasheetIn(
            title="INA219 Power Monitor IC",
            url="/storage/ina219.pdf",
            doc_type="datasheet",
            subsystem_tag="EPS",
            description="EPS power and current sensor",
        ),
        sample_user,
    )

    assert ds1.id is not None
    assert ds1.subsystem_tag == "CDHS"

    # 2. List and filter datasheets
    cdhs_list = await svc.list_datasheets(db, subsystem="CDHS")
    assert any(d.id == ds1.id for d in cdhs_list)

    eps_list = await svc.list_datasheets(db, subsystem="EPS")
    assert any(d.id == ds2.id for d in eps_list)

    search_list = await svc.list_datasheets(db, search="WROOM")
    assert any(d.id == ds1.id for d in search_list)
    assert not any(d.id == ds2.id for d in search_list)

    # 3. Update a datasheet in the library
    updated = await svc.update_datasheet(
        db, ds1.id, PreSessionQuizDatasheetUpdateIn(title="ESP32-WROOM-32D Revised Datasheet")
    )
    assert updated.title == "ESP32-WROOM-32D Revised Datasheet"

    # 4. Attach library datasheets to a preset
    preset_data = PreSessionQuizPresetIn(
        name="Pipeline with Library Datasheets",
        reference_attachments=[
            {
                "id": str(ds1.id),
                "title": ds1.title,
                "url": ds1.url,
                "doc_type": ds1.doc_type,
                "subsystem_tag": ds1.subsystem_tag,
                "is_file": True,
            },
            {
                "id": str(ds2.id),
                "title": ds2.title,
                "url": ds2.url,
                "doc_type": ds2.doc_type,
                "subsystem_tag": ds2.subsystem_tag,
                "is_file": True,
            },
        ],
        phases=[],
    )
    preset = await svc.create_preset(db, preset_data, sample_user)
    assert len(preset["reference_attachments"]) == 2
    assert preset["reference_attachments"][0]["id"] == str(ds1.id)

    # 5. Delete / deactivate a datasheet
    await svc.delete_datasheet(db, ds1.id)
    active_datasheets = await svc.list_datasheets(db, active_only=True)
    assert not any(d.id == ds1.id for d in active_datasheets)
