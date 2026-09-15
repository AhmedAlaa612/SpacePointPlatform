import uuid

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.lms import Course
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.sessions.registration import register
from app.services.teams import create_team
from scripts.backfill_registration_access import (
    backfill_lms_access, report_duplicate_registrations, report_team_gaps,
)


async def _author(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Author", email=f"author-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort_with_program(db, *, author) -> tuple[Cohort, LmsProgram]:
    program = Program(
        id=uuid.uuid4(), code=f"BR-{uuid.uuid4().hex[:8]}", name="Backfill Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Backfill Cohort", status="running")
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Backfill Checklist")
    db.add(lms_program)
    await db.flush()
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:8]}", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    )
    db.add(item)
    await db.flush()
    return cohort, lms_program


async def _contact(db, *, full_name: str, email: str | None) -> Contact:
    contact = Contact(id=uuid.uuid4(), full_name=full_name, email=email, contact_roles=["student"])
    db.add(contact)
    await db.flush()
    return contact


async def _user(db, *, full_name: str, email: str, contact_id=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name=full_name, email=email, password_hash=get_password_hash("dummy"),
        roles=["student"], status="active", contact_id=contact_id, must_change_password=False,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_grants_access_to_a_contact_stranded_on_a_different_users_email(db):
    """The exact production gap: a contact has no linked User, but the
    account that already owns its email belongs to a *different* contact —
    get_or_create_student_account skipped account creation, so
    sync_registration_lms never called assign_lms_program. The backfill
    must find that pre-existing account by email and grant it access."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_program(db, author=author)
    email = f"stranded-{uuid.uuid4().hex[:6]}@example.com"

    other_contact = await _contact(db, full_name="Same Person Earlier", email=email)
    existing_user = await _user(db, full_name="Same Person Earlier", email=email, contact_id=other_contact.id)

    stranded_contact = await _contact(db, full_name="Same Person Later", email=email)
    registration = await register(
        db, contact_id=stranded_contact.id, cohort_id=cohort.id, registered_via="import", payment_status="waived",
    )
    await db.commit()

    report = await backfill_lms_access(db)
    await db.commit()

    assert len(report.assigned) == 1
    assert report.assigned[0] == (registration.id, existing_user.id, email)

    assignment = (await db.execute(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == existing_user.id, LmsProgramAssignment.cohort_id == cohort.id,
        )
    )).scalars().first()
    assert assignment is not None
    assert assignment.registration_id == registration.id


@pytest.mark.asyncio
async def test_is_a_no_op_when_access_already_exists(db):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_program(db, author=author)
    email = f"already-ok-{uuid.uuid4().hex[:6]}@example.com"

    contact = await _contact(db, full_name="Already Fine", email=email)
    user = await _user(db, full_name="Already Fine", email=email, contact_id=contact.id)
    registration = await register(
        db, contact_id=contact.id, cohort_id=cohort.id, registered_via="import", payment_status="waived",
    )
    db.add(LmsProgramAssignment(
        id=uuid.uuid4(), user_id=user.id, lms_program_id=lms_program.id, cohort_id=cohort.id,
        registration_id=registration.id,
    ))
    await db.commit()

    report = await backfill_lms_access(db)
    await db.commit()

    assert report.assigned == []
    assert report.already_ok == 1


@pytest.mark.asyncio
async def test_reports_no_user_when_contact_has_no_email(db):
    author = await _author(db)
    cohort, _ = await _cohort_with_program(db, author=author)

    contact = await _contact(db, full_name="No Email At All", email=None)
    registration = await register(
        db, contact_id=contact.id, cohort_id=cohort.id, registered_via="import", payment_status="waived",
    )
    await db.commit()

    report = await backfill_lms_access(db)
    await db.commit()

    assert report.assigned == []
    assert registration.id in report.no_user


@pytest.mark.asyncio
async def test_team_gap_report_flags_a_registered_user_missing_from_every_team(db):
    author = await _author(db)
    cohort, _ = await _cohort_with_program(db, author=author)
    email = f"noteam-{uuid.uuid4().hex[:6]}@example.com"

    contact = await _contact(db, full_name="No Team", email=email)
    user = await _user(db, full_name="No Team", email=email, contact_id=contact.id)
    registration = await register(
        db, contact_id=contact.id, cohort_id=cohort.id, registered_via="import", payment_status="waived",
    )
    # Some other student IS on a team in this cohort, so it registers as
    # "a cohort with teams" — user above should show up as a gap.
    other_user = await _user(db, full_name="On Team", email=f"onteam-{uuid.uuid4().hex[:6]}@example.com")
    await create_team(db, name="Team A", created_by=other_user.id, cohort_id=cohort.id, roster_team_id="T1")
    await db.commit()

    gaps = await report_team_gaps(db)

    assert (registration.id, user.id) in gaps


@pytest.mark.asyncio
async def test_team_gap_report_is_empty_once_the_user_is_on_a_team(db):
    author = await _author(db)
    cohort, _ = await _cohort_with_program(db, author=author)
    email = f"onteam2-{uuid.uuid4().hex[:6]}@example.com"

    contact = await _contact(db, full_name="On A Team", email=email)
    user = await _user(db, full_name="On A Team", email=email, contact_id=contact.id)
    await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="import", payment_status="waived")
    await create_team(db, name="Team A", created_by=user.id, cohort_id=cohort.id, roster_team_id="T1")
    await db.commit()

    gaps = await report_team_gaps(db, cohort_id=cohort.id)

    assert gaps == []


@pytest.mark.asyncio
async def test_duplicate_registration_report_finds_same_email_two_contacts(db):
    author = await _author(db)
    cohort, _ = await _cohort_with_program(db, author=author)
    email = f"dupe-{uuid.uuid4().hex[:6]}@example.com"

    contact_a = await _contact(db, full_name="Dupe One", email=email)
    contact_b = await _contact(db, full_name="Dupe Two", email=email)
    reg_a = await register(db, contact_id=contact_a.id, cohort_id=cohort.id, registered_via="import", payment_status="waived")
    reg_b = await register(db, contact_id=contact_b.id, cohort_id=cohort.id, registered_via="import", payment_status="waived")
    await db.commit()

    dupes = await report_duplicate_registrations(db, cohort_id=cohort.id)

    assert len(dupes) == 1
    assert dupes[0]["email"] == email
    assert sorted(dupes[0]["registration_ids"]) == sorted([reg_a.id, reg_b.id])


@pytest.mark.asyncio
async def test_duplicate_registration_report_is_empty_for_a_single_registration(db):
    author = await _author(db)
    cohort, _ = await _cohort_with_program(db, author=author)
    email = f"single-{uuid.uuid4().hex[:6]}@example.com"

    contact = await _contact(db, full_name="Just One", email=email)
    await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="import", payment_status="waived")
    await db.commit()

    dupes = await report_duplicate_registrations(db, cohort_id=cohort.id)

    assert dupes == []
