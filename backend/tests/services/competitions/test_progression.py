"""Competition progression — advance_teams (2026-08-24): moves every team
member's Registration + LMS checklist + a same-named Team into the target
cohort, idempotent, refuses a team that isn't in the stated source cohort.
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team
from app.models.user import User
from app.services.competitions.progression import advance_teams
from app.services.sessions.registration import register
from app.services.teams import create_team, team_member_ids


async def _competition_program(db) -> Program:
    program = Program(
        id=uuid.uuid4(), code=f"ADV-{uuid.uuid4().hex[:8]}", name="Ru'ya Space Race",
        program_type="competition", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    return program


async def _cohort(db, program: Program, name: str) -> Cohort:
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name=name, status="registration_open")
    db.add(cohort)
    await db.flush()
    return cohort


async def _checklist(db, program: Program) -> LmsProgram:
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Stage Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Attend orientation",
    ))
    await db.flush()
    return lms_program


async def _student_with_contact(db, *, name: str) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name=name, contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{name.split()[0].lower()}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_advance_teams_moves_registrations_checklist_and_team(db):
    program = await _competition_program(db)
    qualifier = await _cohort(db, program, "Qualifier")
    finalists = await _cohort(db, program, "Finalists")
    await _checklist(db, program)
    student_a = await _student_with_contact(db, name="Amir Salem")
    student_b = await _student_with_contact(db, name="Lina Nasser")
    await db.commit()

    await register(db, contact_id=student_a.contact_id, cohort_id=qualifier.id, registered_via="import", payment_status="waived")
    await register(db, contact_id=student_b.contact_id, cohort_id=qualifier.id, registered_via="import", payment_status="waived")
    team = await create_team(db, name="Falcon Eye", created_by=student_a.id, cohort_id=qualifier.id, member_ids=[student_b.id])
    await db.commit()

    results = await advance_teams(db, team_ids=[team.id], from_cohort_id=qualifier.id, to_cohort_id=finalists.id)
    await db.commit()

    assert len(results) == 1
    assert results[0].team_name == "Falcon Eye" and results[0].members_advanced == 2

    finalists_team = (await db.execute(
        select(Team).where(Team.cohort_id == finalists.id, Team.name == "Falcon Eye")
    )).scalars().first()
    assert finalists_team is not None
    assert set(await team_member_ids(db, team_id=finalists_team.id)) == {student_a.id, student_b.id}

    for student in (student_a, student_b):
        reg = (await db.execute(
            select(Registration).where(Registration.contact_id == student.contact_id, Registration.cohort_id == finalists.id)
        )).scalars().first()
        assert reg is not None
        assignment = (await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.user_id == student.id, LmsProgramAssignment.cohort_id == finalists.id,
            )
        )).scalars().first()
        assert assignment is not None


@pytest.mark.asyncio
async def test_advance_teams_is_idempotent(db):
    program = await _competition_program(db)
    qualifier = await _cohort(db, program, "Qualifier")
    finalists = await _cohort(db, program, "Finalists")
    await _checklist(db, program)
    student = await _student_with_contact(db, name="Amir Salem")
    await db.commit()
    await register(db, contact_id=student.contact_id, cohort_id=qualifier.id, registered_via="import", payment_status="waived")
    team = await create_team(db, name="Falcon Eye", created_by=student.id, cohort_id=qualifier.id)
    await db.commit()

    await advance_teams(db, team_ids=[team.id], from_cohort_id=qualifier.id, to_cohort_id=finalists.id)
    await db.commit()
    second = await advance_teams(db, team_ids=[team.id], from_cohort_id=qualifier.id, to_cohort_id=finalists.id)
    await db.commit()

    assert second[0].members_advanced == 1
    teams = (await db.execute(select(Team).where(Team.cohort_id == finalists.id))).scalars().all()
    assert len(teams) == 1


@pytest.mark.asyncio
async def test_advance_teams_refuses_a_team_not_in_the_source_cohort(db):
    program = await _competition_program(db)
    qualifier = await _cohort(db, program, "Qualifier")
    finalists = await _cohort(db, program, "Finalists")
    other_cohort = await _cohort(db, program, "Some Other Cohort")
    student = await _student_with_contact(db, name="Amir Salem")
    await db.commit()
    team = await create_team(db, name="Falcon Eye", created_by=student.id, cohort_id=other_cohort.id)
    await db.commit()

    with pytest.raises(HTTPException):
        await advance_teams(db, team_ids=[team.id], from_cohort_id=qualifier.id, to_cohort_id=finalists.id)
