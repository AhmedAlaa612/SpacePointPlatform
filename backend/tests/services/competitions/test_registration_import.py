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
        program_type="competition", pricing_model="free", active=True,
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


@pytest.mark.asyncio
async def test_import_accepts_the_ops_selection_tracker_headers(db):
    """Ops's real "Eligible"/"Final Selection" tracker sheet uses "Student
    Name" and "School / University", not this module's canonical
    `member_name`/`school` — see `_HEADER_ALIASES`."""
    cohort = await _make_cohort(db)
    await db.commit()

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["Team Name", "Student Name", "Email", "Phone", "School / University"])
    sheet.append([
        "Falcon Eye", "Amir Salem", f"amir-{uuid.uuid4().hex[:6]}@example.com", "0501234567", "SABIS",
    ])
    buf = io.BytesIO()
    wb.save(buf)

    rows = parse_registration_sheet(buf.getvalue())
    results = await import_registrations(db, cohort_id=cohort.id, rows=rows)
    await db.commit()

    assert summarize(results) == {"total": 1, "created": 1, "matched": 0, "error": 0}
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert {t.name for t in teams} == {"Falcon Eye"}


@pytest.mark.asyncio
async def test_import_accepts_a_csv_export_of_the_same_tracker(db):
    """The upload widget advertises .csv as well as .xlsx — a Google Sheets
    "Download as CSV" of the same tracker tab must work identically,
    BOM and all (Excel/Sheets stamp a UTF-8 BOM on CSV exports)."""
    cohort = await _make_cohort(db)
    await db.commit()

    email = f"csvrow-{uuid.uuid4().hex[:6]}@example.com"
    csv_text = f"Team Name,Student Name,Email,Phone,School / University\r\nFalcon Eye,Amir Salem,{email},0501234567,SABIS\r\n"
    file_bytes = b"\xef\xbb\xbf" + csv_text.encode("utf-8")  # UTF-8 BOM, as Excel/Sheets stamp it

    rows = parse_registration_sheet(file_bytes, filename="eligible.csv")
    results = await import_registrations(db, cohort_id=cohort.id, rows=rows)
    await db.commit()

    assert summarize(results) == {"total": 1, "created": 1, "matched": 0, "error": 0}
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert {t.name for t in teams} == {"Falcon Eye"}


def test_parse_rejects_a_non_spreadsheet_file_cleanly():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        parse_registration_sheet(b"this is plainly not a zip file", filename="roster.xlsx")
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_import_finds_the_header_past_the_trackers_title_and_stage_rows(db):
    """Ops's real "Eligible" export (the one that actually broke): a title
    row, a stage-description row, THEN the header on row 3 — not row 1.
    Real shape, real columns, straight from the file that failed."""
    cohort = await _make_cohort(db)
    await db.commit()

    email = f"ed1-{uuid.uuid4().hex[:6]}@example.com"
    csv_text = (
        "Eligible Applicants — Before Qualifier,,,,,,,,,,,,,\r\n"
        "Stage 2: Confirm eligibility before the qualifier; eligible candidates are sent for NSA approval.,,,,,,,,,,,,,\r\n"
        "Application ID,Student Name,Email,Phone,School / University,Age / Grade,Emirate,Team Name,Team ID,"
        "Eligibility Status,Eligibility Check,Eligible?,Reason / Notes,Sent to NSA?\r\n"
        f"1,ed1,{email},,msa,12,yes,edos,1,,,,,\r\n"
    )
    file_bytes = csv_text.encode("utf-8")

    rows = parse_registration_sheet(file_bytes, filename="eligible.csv")
    results = await import_registrations(db, cohort_id=cohort.id, rows=rows)
    await db.commit()

    assert summarize(results) == {"total": 1, "created": 1, "matched": 0, "error": 0}
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert {t.name for t in teams} == {"edos"}


@pytest.mark.asyncio
async def test_import_adds_pre_existing_user_to_team(db):
    """A student who already has a User account (e.g. from a previous LMS
    enrolment) but whose User.contact_id doesn't match the freshly-resolved
    contact should still be added to the team — not silently dropped with
    an error row (the bug: `sync_registration_lms` returns None because the
    email is already on a different User, and _import_row used to bail
    before reaching the team-join code)."""
    from app.core.security import get_password_hash

    cohort = await _make_cohort(db)

    # Create a pre-existing User with no contact_id — simulates an account
    # that was provisioned through some other path (manual admin creation,
    # an older import pipeline, etc.)
    email = f"existing-{uuid.uuid4().hex[:6]}@example.com"
    existing_user = User(
        id=uuid.uuid4(), full_name="Existing Student", email=email,
        password_hash=get_password_hash("dummy"), roles=["student"],
        status="active",
    )
    db.add(existing_user)
    await db.commit()

    file_bytes = _workbook([
        {"team_name": "Falcon Eye", "member_name": "Existing Student", "email": email},
    ])
    rows = parse_registration_sheet(file_bytes)
    results = await import_registrations(db, cohort_id=cohort.id, rows=rows)
    await db.commit()

    # The row should succeed (not error) and the user should be on the team
    summary = summarize(results)
    assert summary["error"] == 0, f"Expected no errors, got: {[r for r in results if r.disposition == 'error']}"
    assert summary["created"] + summary["matched"] == 1

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1
    assert teams[0].name == "Falcon Eye"
    members = await team_member_ids(db, team_id=teams[0].id)
    assert existing_user.id in members
