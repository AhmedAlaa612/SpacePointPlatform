"""Competition registration import (2026-08-24) — idempotent on email,
teams grouped by team_name, a bad row errors without failing the batch.
"""

import io
import uuid

import openpyxl
import pytest
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.team import Team
from app.models.user import User
from app.services.competitions.registration_import import (
    REQUIRED_COLUMNS, import_registrations, parse_registration_sheet, summarize,
)
from app.services.teams import team_member_ids


async def _make_cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"REG-{uuid.uuid4().hex[:8]}", name="Ru'ya Space Race",
        program_type="workshop", pricing_model="free", active=True, is_competition=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Qualifier", status="registration_open")
    db.add(cohort)
    await db.flush()
    return cohort


def _workbook(rows: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    sheet = wb.active
    columns = ["team_name", "member_name", "email", "phone", "school"]
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(c) for c in columns])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_parse_requires_columns():
    from fastapi import HTTPException
    wb = openpyxl.Workbook()
    wb.active.append(["team_name", "member_name"])  # missing email
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(HTTPException):
        parse_registration_sheet(buf.getvalue())
    assert "email" in REQUIRED_COLUMNS


@pytest.mark.asyncio
async def test_import_creates_teams_and_student_accounts(db):
    cohort = await _make_cohort(db)
    await db.commit()

    file_bytes = _workbook([
        {"team_name": "Falcon Eye", "member_name": "Amir Salem", "email": f"amir-{uuid.uuid4().hex[:6]}@example.com"},
        {"team_name": "Falcon Eye", "member_name": "Lina Nasser", "email": f"lina-{uuid.uuid4().hex[:6]}@example.com"},
        {"team_name": "Silent Comet", "member_name": "Zaid Omar", "email": f"zaid-{uuid.uuid4().hex[:6]}@example.com"},
    ])
    rows = parse_registration_sheet(file_bytes)
    results = await import_registrations(db, cohort_id=cohort.id, rows=rows)
    await db.commit()

    summary = summarize(results)
    assert summary == {"total": 3, "created": 3, "matched": 0, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert {t.name for t in teams} == {"Falcon Eye", "Silent Comet"}
    falcon = next(t for t in teams if t.name == "Falcon Eye")
    assert len(await team_member_ids(db, team_id=falcon.id)) == 2

    users = (await db.execute(select(User).where(User.roles.any("student")))).scalars().all()
    assert len(users) >= 3


@pytest.mark.asyncio
async def test_import_is_idempotent_on_email(db):
    cohort = await _make_cohort(db)
    await db.commit()
    email = f"repeat-{uuid.uuid4().hex[:6]}@example.com"
    file_bytes = _workbook([{"team_name": "Falcon Eye", "member_name": "Amir Salem", "email": email}])

    first = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()
    assert summarize(first)["created"] == 1

    second = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()
    assert summarize(second) == {"total": 1, "created": 0, "matched": 1, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1


@pytest.mark.asyncio
async def test_a_row_missing_a_required_field_errors_without_failing_the_batch(db):
    cohort = await _make_cohort(db)
    await db.commit()
    file_bytes = _workbook([
        {"team_name": "Falcon Eye", "member_name": "", "email": f"noname-{uuid.uuid4().hex[:6]}@example.com"},
        {"team_name": "Falcon Eye", "member_name": "Lina Nasser", "email": f"lina2-{uuid.uuid4().hex[:6]}@example.com"},
    ])
    results = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()

    summary = summarize(results)
    assert summary["error"] == 1 and summary["created"] == 1
