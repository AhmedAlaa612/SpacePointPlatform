"""Competition registration import (2026-08-24, team_id grouping + deferred
naming 2026-09-14) — idempotent on email, teams grouped by team_id (not
name — the roster's own external team code), a bad row errors without
failing the batch.
"""

import io
import uuid

import openpyxl
import pytest
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team
from app.models.user import User
from app.services.competitions.registration_import import (
    REQUIRED_COLUMNS, assign_existing_students, import_registrations, parse_registration_sheet, summarize,
    summarize_assign_results,
)
from app.services.teams import create_team, team_member_ids


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
    """Column set is the union of every row's own keys, in first-seen
    order — lets each test only spell out the fields it actually cares
    about (real sheets vary in which optional columns they carry too)."""
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    wb = openpyxl.Workbook()
    sheet = wb.active
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
    wb.active.append(["team_id", "member_name"])  # missing email
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(HTTPException):
        parse_registration_sheet(buf.getvalue())
    assert "email" in REQUIRED_COLUMNS
    assert "team_id" in REQUIRED_COLUMNS
    assert "team_name" not in REQUIRED_COLUMNS  # optional now — see module docstring


@pytest.mark.asyncio
async def test_import_creates_teams_and_student_accounts(db):
    cohort = await _make_cohort(db)
    await db.commit()

    file_bytes = _workbook([
        {"team_id": "T1", "team_name": "Falcon Eye", "member_name": "Amir Salem", "email": f"amir-{uuid.uuid4().hex[:6]}@example.com"},
        {"team_id": "T1", "team_name": "Falcon Eye", "member_name": "Lina Nasser", "email": f"lina-{uuid.uuid4().hex[:6]}@example.com"},
        {"team_id": "T2", "team_name": "Silent Comet", "member_name": "Zaid Omar", "email": f"zaid-{uuid.uuid4().hex[:6]}@example.com"},
    ])
    rows = parse_registration_sheet(file_bytes)
    results = await import_registrations(db, cohort_id=cohort.id, rows=rows)
    await db.commit()

    summary = summarize(results)
    assert summary == {"total": 3, "created": 3, "matched": 0, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert {t.name for t in teams} == {"Falcon Eye", "Silent Comet"}
    assert {t.roster_team_id for t in teams} == {"T1", "T2"}
    falcon = next(t for t in teams if t.name == "Falcon Eye")
    assert len(await team_member_ids(db, team_id=falcon.id)) == 2

    users = (await db.execute(select(User).where(User.roles.any("student")))).scalars().all()
    assert len(users) >= 3


@pytest.mark.asyncio
async def test_import_falls_back_to_the_team_id_when_team_name_is_blank(db):
    """The roster's whole point (2026-09-14): a team can be onboarded with
    only its id, no name yet — students set the real one themselves later.
    `name` is seeded to `team_id` as a literal placeholder rather than left
    NULL — see app/models/team.py's module docstring."""
    cohort = await _make_cohort(db)
    await db.commit()

    file_bytes = _workbook([
        {"team_id": "T-014", "member_name": "Amir Salem", "email": f"amir-{uuid.uuid4().hex[:6]}@example.com"},
    ])
    results = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()

    assert summarize(results) == {"total": 1, "created": 1, "matched": 0, "error": 0}
    team = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalar_one()
    assert team.roster_team_id == "T-014"
    assert team.name == "T-014"  # still unnamed — name == roster_team_id


@pytest.mark.asyncio
async def test_reimport_never_clobbers_a_name_the_team_already_set(db):
    """A team that renamed itself (or that ops fixed) between two imports of
    the same sheet must keep that name — only ever apply the sheet's name
    while the team is still at its own placeholder."""
    cohort = await _make_cohort(db)
    await db.commit()

    email = f"amir-{uuid.uuid4().hex[:6]}@example.com"
    file_bytes = _workbook([{"team_id": "T-014", "member_name": "Amir Salem", "email": email}])
    await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()

    team = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalar_one()
    assert team.name == "T-014"
    team.name = "Falcon Eye"  # simulates the team's own rename
    await db.commit()

    # Re-import the exact same sheet (still no team_name column at all).
    results = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()
    assert summarize(results) == {"total": 1, "created": 0, "matched": 1, "error": 0}

    await db.refresh(team)
    assert team.name == "Falcon Eye"

    # Now the sheet DOES carry a name for this team_id — still must not
    # overwrite the real one already set.
    named_file = _workbook([{"team_id": "T-014", "team_name": "Something Else", "member_name": "Amir Salem", "email": email}])
    await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(named_file))
    await db.commit()
    await db.refresh(team)
    assert team.name == "Falcon Eye"


@pytest.mark.asyncio
async def test_import_flags_a_team_name_collision_without_failing_the_batch(db):
    """Case-insensitive (models/team.py) — an existing real team name
    collides with another team's fallback-to-team_id placeholder just as
    easily as with an explicit team_name, so this covers both directions."""
    from app.core.security import get_password_hash

    cohort = await _make_cohort(db)
    creator = User(
        id=uuid.uuid4(), full_name="Team Creator", email=f"creator-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("dummy"), roles=["student"], status="active",
    )
    db.add(creator)
    await db.flush()
    existing = await create_team(db, name="Falcon", created_by=creator.id, cohort_id=cohort.id)
    await db.commit()

    file_bytes = _workbook([
        {"team_id": "FALCON", "member_name": "Amir Salem", "email": f"amir-{uuid.uuid4().hex[:6]}@example.com"},
    ])
    results = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()

    summary = summarize(results)
    assert summary == {"total": 1, "created": 0, "matched": 0, "error": 1}
    assert "already exists" in results[0].reason

    # The other team is untouched, and no second team got created.
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1
    assert teams[0].id == existing.id


@pytest.mark.asyncio
async def test_import_captures_nationality_on_the_contact(db):
    cohort = await _make_cohort(db)
    await db.commit()
    email = f"amir-{uuid.uuid4().hex[:6]}@example.com"
    file_bytes = _workbook([
        {"team_id": "T1", "member_name": "Amir Salem", "email": email, "nationality": "Emirati"},
    ])
    await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()

    contact = (await db.execute(select(Contact).where(Contact.email == email))).scalar_one()
    assert contact.nationality == "Emirati"


@pytest.mark.asyncio
async def test_import_is_idempotent_on_email(db):
    cohort = await _make_cohort(db)
    await db.commit()
    email = f"repeat-{uuid.uuid4().hex[:6]}@example.com"
    file_bytes = _workbook([{"team_id": "T1", "team_name": "Falcon Eye", "member_name": "Amir Salem", "email": email}])

    first = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()
    assert summarize(first)["created"] == 1

    second = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()
    assert summarize(second) == {"total": 1, "created": 0, "matched": 1, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1


@pytest.mark.asyncio
async def test_reimport_reuses_an_already_registered_contact_even_without_a_matching_alias(db):
    """Production bug (2026-09-15): an email got re-uploaded onto a cohort
    where it was already fully registered and on a team, but landed on a
    *second*, alias-less Contact instead of being recognized as the same
    person — `resolve_or_create_contact`'s alias matching never got a
    chance to find the first one. Simulated here by creating the first
    Contact/User/Registration/team-membership directly (bypassing
    `resolve_or_create_contact` entirely, exactly like the corrupted
    production state), then re-importing the same email: the row must
    reuse that existing contact via `_find_existing_contact_by_email`
    (contacts already registered in this cohort, by email) rather than
    minting a second Contact and a second Registration."""
    from app.core.security import get_password_hash

    from app.services.sessions.registration import register
    from app.services.teams import create_team

    cohort = await _make_cohort(db)
    email = f"dup-{uuid.uuid4().hex[:6]}@example.com"

    contact = Contact(id=uuid.uuid4(), full_name="Mohammad Sultan", email=email, contact_roles=["student"])
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name="Mohammad Sultan", email=email, password_hash=get_password_hash("dummy"),
        roles=["student"], status="active", contact_id=contact.id, must_change_password=False,
    )
    db.add(user)
    await db.flush()
    registration = await register(
        db, contact_id=contact.id, cohort_id=cohort.id, registered_via="import", payment_status="waived",
    )
    team = await create_team(
        db, name="Falcon Eye", created_by=user.id, cohort_id=cohort.id, member_ids=[user.id], roster_team_id="T1",
    )
    await db.commit()

    file_bytes = _workbook([
        {"team_id": "T1", "team_name": "Falcon Eye", "member_name": "Mohammad Sultan", "email": email},
    ])
    results = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()

    assert summarize(results) == {"total": 1, "created": 0, "matched": 1, "error": 0}
    assert results[0].registration_id == registration.id

    contacts = (await db.execute(select(Contact).where(Contact.email == email))).scalars().all()
    assert len(contacts) == 1, "a re-upload of an already-registered email must not mint a second Contact"

    registrations = (
        await db.execute(select(Registration).where(Registration.cohort_id == cohort.id))
    ).scalars().all()
    assert len(registrations) == 1, "a re-upload of an already-registered email must not create a second Registration"

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1
    members = await team_member_ids(db, team_id=team.id)
    assert members == [user.id]


@pytest.mark.asyncio
async def test_a_row_missing_a_required_field_errors_without_failing_the_batch(db):
    cohort = await _make_cohort(db)
    await db.commit()
    file_bytes = _workbook([
        {"team_id": "T1", "member_name": "", "email": f"noname-{uuid.uuid4().hex[:6]}@example.com"},
        {"team_id": "T1", "member_name": "Lina Nasser", "email": f"lina2-{uuid.uuid4().hex[:6]}@example.com"},
    ])
    results = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()

    summary = summarize(results)
    assert summary["error"] == 1 and summary["created"] == 1


@pytest.mark.asyncio
async def test_a_row_missing_team_id_errors_even_with_a_team_name_present(db):
    """team_id, not team_name, is the required grouping key now — a row with
    a name but a blank id still errors (the column exists, so this is the
    per-row blocking-issue path, not the missing-column 422 above it)."""
    cohort = await _make_cohort(db)
    await db.commit()
    file_bytes = _workbook([
        {"team_id": None, "team_name": "Falcon Eye", "member_name": "Amir Salem", "email": f"amir-{uuid.uuid4().hex[:6]}@example.com"},
        {"team_id": "T1", "team_name": "Falcon Eye", "member_name": "Lina Nasser", "email": f"lina-{uuid.uuid4().hex[:6]}@example.com"},
    ])
    results = await import_registrations(db, cohort_id=cohort.id, rows=parse_registration_sheet(file_bytes))
    await db.commit()
    summary = summarize(results)
    assert summary["error"] == 1 and summary["created"] == 1
    error_row = next(r for r in results if r.disposition == "error")
    assert "Team ID" in error_row.reason


@pytest.mark.asyncio
async def test_import_accepts_the_ops_selection_tracker_headers(db):
    """Ops's real "Eligible"/"Final Selection" tracker sheet uses "Student
    Name" and "School / University", not this module's canonical
    `member_name`/`school` — see `_HEADER_ALIASES`."""
    cohort = await _make_cohort(db)
    await db.commit()

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["Team Name", "Team ID", "Student Name", "Email", "Phone", "School / University"])
    sheet.append([
        "Falcon Eye", "T1", "Amir Salem", f"amir-{uuid.uuid4().hex[:6]}@example.com", "0501234567", "SABIS",
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
    csv_text = f"Team Name,Team ID,Student Name,Email,Phone,School / University\r\nFalcon Eye,T1,Amir Salem,{email},0501234567,SABIS\r\n"
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
    Real shape, real columns, straight from the file that failed. This
    sheet carries both Team Name and Team ID — the real, common case."""
    cohort = await _make_cohort(db)
    await db.commit()

    email = f"ed1-{uuid.uuid4().hex[:6]}@example.com"
    csv_text = (
        "Eligible Applicants — Before Qualifier,,,,,,,,,,,,,\r\n"
        "Stage 2: Confirm eligibility before the qualifier; eligible candidates are sent for NSA approval.,,,,,,,,,,,,,\r\n"
        "Application ID,Student Name,Nationality,Email,Phone,School / University,Age / Grade,Emirate,Team Name,Team ID,"
        "Eligibility Status,Eligibility Check,Eligible?,Reason / Notes,Sent to NSA?\r\n"
        f"1,ed1,Emirati,{email},,msa,12,yes,edos,1,,,,,\r\n"
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
        {"team_id": "T1", "team_name": "Falcon Eye", "member_name": "Existing Student", "email": email},
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


# ── Assign existing (self-registered) students (2026-09-14) ─────────────

async def _make_self_registered_student(db, *, full_name: str = "Self Registered", email: str | None = None) -> User:
    """Mirrors what routers/auth.py::student_signup actually leaves behind:
    a Contact + a User with `contact_id` set — no Registration in any
    cohort yet. That's exactly the gap `assign_existing_students` closes."""
    from app.core.security import get_password_hash

    email = email or f"self-{uuid.uuid4().hex[:6]}@example.com"
    contact = Contact(id=uuid.uuid4(), full_name=full_name, email=email, contact_roles=["student"])
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name=full_name, email=email, password_hash=get_password_hash("dummy"),
        roles=["student"], status="active", contact_id=contact.id, must_change_password=False,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_assign_registers_a_self_registered_student_into_a_new_team(db):
    cohort = await _make_cohort(db)
    student = await _make_self_registered_student(db)
    await db.commit()

    results = await assign_existing_students(
        db, cohort_id=cohort.id, rows=[{"row_number": 1, "user_id": student.id, "team_id": "T1"}],
    )
    await db.commit()

    assert summarize_assign_results(results) == {"total": 1, "created": 1, "matched": 0, "error": 0}
    assert results[0].registration_id is not None

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1
    assert teams[0].roster_team_id == "T1"
    assert teams[0].name == "T1"  # unnamed placeholder — student names it later
    assert student.id in await team_member_ids(db, team_id=teams[0].id)

    reg = (await db.execute(
        select(Registration).where(Registration.contact_id == student.contact_id, Registration.cohort_id == cohort.id)
    )).scalar_one()
    assert reg.id == results[0].registration_id


@pytest.mark.asyncio
async def test_assign_joins_an_existing_team_by_id_and_is_idempotent(db):
    cohort = await _make_cohort(db)
    a = await _make_self_registered_student(db, full_name="Student A")
    b = await _make_self_registered_student(db, full_name="Student B")
    await db.commit()

    first = await assign_existing_students(
        db, cohort_id=cohort.id, rows=[{"row_number": 1, "user_id": a.id, "team_id": "T1"}],
    )
    await db.commit()
    assert summarize_assign_results(first)["created"] == 1

    second = await assign_existing_students(
        db, cohort_id=cohort.id, rows=[{"row_number": 1, "user_id": b.id, "team_id": "T1"}],
    )
    await db.commit()
    assert summarize_assign_results(second) == {"total": 1, "created": 1, "matched": 0, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1
    members = set(await team_member_ids(db, team_id=teams[0].id))
    assert {a.id, b.id} <= members

    # Re-running the exact same (student, team) pair reports `matched`, not
    # a duplicate registration or a second join.
    third = await assign_existing_students(
        db, cohort_id=cohort.id, rows=[{"row_number": 1, "user_id": a.id, "team_id": "T1"}],
    )
    await db.commit()
    assert summarize_assign_results(third) == {"total": 1, "created": 0, "matched": 1, "error": 0}
    teams_again = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams_again) == 1


@pytest.mark.asyncio
async def test_assign_a_row_with_no_team_id_errors_without_failing_the_batch(db):
    cohort = await _make_cohort(db)
    a = await _make_self_registered_student(db)
    b = await _make_self_registered_student(db)
    await db.commit()

    results = await assign_existing_students(
        db, cohort_id=cohort.id,
        rows=[
            {"row_number": 1, "user_id": a.id, "team_id": ""},
            {"row_number": 2, "user_id": b.id, "team_id": "T1"},
        ],
    )
    await db.commit()

    summary = summarize_assign_results(results)
    assert summary["error"] == 1 and summary["created"] == 1
    error_row = next(r for r in results if r.disposition == "error")
    assert "Team ID" in error_row.reason


@pytest.mark.asyncio
async def test_assign_an_unknown_user_id_errors_without_failing_the_batch(db):
    cohort = await _make_cohort(db)
    real = await _make_self_registered_student(db)
    await db.commit()

    results = await assign_existing_students(
        db, cohort_id=cohort.id,
        rows=[
            {"row_number": 1, "user_id": uuid.uuid4(), "team_id": "T1"},
            {"row_number": 2, "user_id": real.id, "team_id": "T1"},
        ],
    )
    await db.commit()

    summary = summarize_assign_results(results)
    assert summary["error"] == 1 and summary["created"] == 1
    error_row = next(r for r in results if r.disposition == "error")
    assert "not found" in error_row.reason.lower()


@pytest.mark.asyncio
async def test_assign_flags_a_team_name_collision_without_failing_the_batch(db):
    """A student assigned into a fresh team_id whose fallback placeholder
    name (the team_id itself) collides case-insensitively with an existing
    real team name — same class of conflict the CSV path guards against."""
    from app.core.security import get_password_hash

    cohort = await _make_cohort(db)
    creator = User(
        id=uuid.uuid4(), full_name="Team Creator", email=f"creator-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("dummy"), roles=["student"], status="active",
    )
    db.add(creator)
    await db.flush()
    existing = await create_team(db, name="Falcon", created_by=creator.id, cohort_id=cohort.id)
    student = await _make_self_registered_student(db)
    await db.commit()

    results = await assign_existing_students(
        db, cohort_id=cohort.id, rows=[{"row_number": 1, "user_id": student.id, "team_id": "FALCON"}],
    )
    await db.commit()

    assert summarize_assign_results(results) == {"total": 1, "created": 0, "matched": 0, "error": 1}
    assert "already exists" in results[0].reason
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1
    assert teams[0].id == existing.id


@pytest.mark.asyncio
async def test_assign_does_not_touch_a_student_with_no_contact(db):
    """Structurally shouldn't happen for a self-registered account (signup
    always sets contact_id), but a User with no contact_id must still error
    cleanly rather than blow up on `resolve_or_create_contact`-free logic
    downstream that assumes one."""
    from app.core.security import get_password_hash

    cohort = await _make_cohort(db)
    orphan = User(
        id=uuid.uuid4(), full_name="No Contact", email=f"orphan-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("dummy"), roles=["student"], status="active",
    )
    db.add(orphan)
    await db.commit()

    results = await assign_existing_students(
        db, cohort_id=cohort.id, rows=[{"row_number": 1, "user_id": orphan.id, "team_id": "T1"}],
    )
    await db.commit()
    assert summarize_assign_results(results) == {"total": 1, "created": 0, "matched": 0, "error": 1}
