"""Mandatory tests for V2 R2-2 (see MASTER_EXECUTION_PLAN_V2.md R2-2):
dry-run == commit counts; idempotent re-run zero-change; a row matching an
existing contact links instead of duplicating; malformed row -> error entry,
batch still processes rest. Plus the acceptance scenario: a 50-row sheet with
3 planted duplicates -> 3 links/reviews, zero duplicate contacts.
"""

import hashlib
import io
import uuid

import openpyxl
import pytest
from sqlalchemy import func, select

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.spine.identity_alias import IdentityAlias
from app.models.spine.organization import Organization
from app.models.user import User
from app.services.sessions.importer import TEMPLATE_COLUMNS, commit_batch, dry_run, generate_template_xlsx
from app.services.sessions.registration import register


async def _make_uploader(db) -> User:
    """import_batches.uploaded_by is a real FK to users.id — a random UUID
    won't satisfy it."""
    user = User(
        id=uuid.uuid4(), full_name="Import Uploader", email=f"uploader-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"],
    )
    db.add(user)
    await db.flush()
    return user


async def _make_cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"IMP-{uuid.uuid4().hex[:8]}", name="Import Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Import Test Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    return cohort


def _build_workbook(rows: list[dict], header_offset: int = 0) -> bytes:
    """header_offset lets a test put the header row somewhere other than row
    1 (to exercise the "tolerate header in first 5 rows" rule)."""
    wb = openpyxl.Workbook()
    sheet = wb.active
    for _ in range(header_offset):
        sheet.append(["ignore this row"])
    sheet.append([name for name, _ in TEMPLATE_COLUMNS])
    for row in rows:
        sheet.append([row.get(name) for name, _ in TEMPLATE_COLUMNS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _student_row(**overrides) -> dict:
    row = dict(
        student_name="Test Student", email="student@example.com",
        phone="050 111 2222", city="Dubai",
        parent_name=None, parent_phone=None, parent_email=None,
    )
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_dry_run_never_writes_to_the_database(db):
    """Dry-run must be non-destructive — no Contact/Registration rows should
    exist afterward, only the ImportBatch itself."""
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    wb_bytes = _build_workbook([_student_row(email="dryrun.only@example.com")])

    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")

    assert batch.status == "dry_run"
    assert batch.counts["summary"]["create"] == 1
    contact = (await db.execute(select(Contact).where(Contact.email == "dryrun.only@example.com"))).scalars().first()
    assert contact is None  # rolled back, never persisted


@pytest.mark.asyncio
async def test_dry_run_counts_equal_commit_counts(db):
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    rows = [_student_row(email=f"student{i}@example.com", phone=f"050{i:07d}") for i in range(5)]
    wb_bytes = _build_workbook(rows)

    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")
    dry_run_summary = dict(batch.counts["summary"])

    committed = await commit_batch(db, batch.id)

    assert committed.counts["summary"] == dry_run_summary
    assert dry_run_summary["create"] == 5

    registrations = (await db.execute(
        select(func.count()).select_from(Registration).where(Registration.cohort_id == cohort.id)
    )).scalar_one()
    assert registrations == 5


@pytest.mark.asyncio
async def test_idempotent_recommit_creates_nothing_new(db):
    """Re-running dry_run + commit_batch against the SAME cohort with the
    SAME sheet a second time must produce zero new contacts/registrations."""
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    rows = [_student_row(email=f"repeat{i}@example.com", phone=f"0501{i:06d}") for i in range(4)]
    wb_bytes = _build_workbook(rows)

    batch1 = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")
    await commit_batch(db, batch1.id)

    contact_count_after_first = (await db.execute(select(func.count()).select_from(Contact))).scalar_one()
    registration_count_after_first = (await db.execute(select(func.count()).select_from(Registration))).scalar_one()

    batch2 = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")
    assert batch2.counts["summary"]["already_registered"] == 4
    assert batch2.counts["summary"]["create"] == 0
    committed2 = await commit_batch(db, batch2.id)
    assert committed2.counts["summary"]["already_registered"] == 4

    contact_count_after_second = (await db.execute(select(func.count()).select_from(Contact))).scalar_one()
    registration_count_after_second = (await db.execute(select(func.count()).select_from(Registration))).scalar_one()
    assert contact_count_after_second == contact_count_after_first
    assert registration_count_after_second == registration_count_after_first


@pytest.mark.asyncio
async def test_row_matching_existing_contact_links_instead_of_duplicating(db):
    """A row whose email matches a contact already on file (e.g. registered
    earlier via the public form for a DIFFERENT cohort) must link to that
    contact, not create a second one."""
    cohort_a = await _make_cohort(db)
    cohort_b = await _make_cohort(db)
    uploader = await _make_uploader(db)

    existing = Contact(
        id=uuid.uuid4(), full_name="Already Exists", contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
        email="already.exists@example.com",
    )
    db.add(existing)
    await db.flush()
    db.add(IdentityAlias(
        id=uuid.uuid4(), contact_id=existing.id, alias_type="email",
        alias_value_hash=hashlib.sha256(b"already.exists@example.com").hexdigest(),
        matched_by="import",
    ))
    await db.flush()
    # register them for cohort_a already, to prove cohort_b's import doesn't collide
    await register(db, contact_id=existing.id, cohort_id=cohort_a.id, registered_via="import")

    wb_bytes = _build_workbook([_student_row(email="already.exists@example.com", phone="050 999 8888")])
    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort_b.id, uploaded_by=uploader.id, source="b2b_sheet")
    assert batch.counts["summary"]["link"] == 1
    assert batch.counts["summary"]["create"] == 0

    await commit_batch(db, batch.id)

    total_contacts_named_exists = (await db.execute(
        select(func.count()).select_from(Contact).where(Contact.email == "already.exists@example.com")
    )).scalar_one()
    assert total_contacts_named_exists == 1  # not duplicated

    reg_b = (await db.execute(
        select(Registration).where(Registration.contact_id == existing.id, Registration.cohort_id == cohort_b.id)
    )).scalars().first()
    assert reg_b is not None


@pytest.mark.asyncio
async def test_malformed_row_becomes_error_batch_still_processes_rest(db):
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    rows = [
        _student_row(email="good1@example.com", phone="050 111 0001"),
        _student_row(email="", phone="050 111 0002"),  # missing required email
        _student_row(email="good2@example.com", phone="050 111 0003"),
    ]
    wb_bytes = _build_workbook(rows)

    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")

    assert batch.counts["summary"]["error"] == 1
    assert batch.counts["summary"]["create"] == 2
    error_rows = [r for r in batch.counts["rows"] if r["disposition"] == "error"]
    assert len(error_rows) == 1
    assert error_rows[0]["reason"]

    committed = await commit_batch(db, batch.id)
    assert committed.counts["summary"]["error"] == 1
    assert committed.counts["summary"]["create"] == 2


@pytest.mark.asyncio
async def test_header_row_tolerated_anywhere_in_first_five_rows(db):
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    wb_bytes = _build_workbook([_student_row(email="offset.header@example.com")], header_offset=3)

    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")
    assert batch.counts["summary"]["create"] == 1


@pytest.mark.asyncio
async def test_row_with_parent_info_creates_guardian_and_relationship(db):
    """Parent info is always optional (no age tracking or minor enforcement
    anywhere in this system) — if given, it creates/links a guardian contact
    and sets them as payer regardless of anything else in the row."""
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    wb_bytes = _build_workbook([_student_row(
        email="student.with.parent@example.com",
        parent_name="Import Parent", parent_phone="050 222 3333",
    )])

    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")
    assert batch.counts["summary"]["create"] == 1
    await commit_batch(db, batch.id)

    student = (await db.execute(select(Contact).where(Contact.email == "student.with.parent@example.com"))).scalars().first()
    registration = (await db.execute(
        select(Registration).where(Registration.contact_id == student.id, Registration.cohort_id == cohort.id)
    )).scalars().first()
    guardian = (await db.execute(
        select(Contact).where(Contact.full_name == "Import Parent")
    )).scalars().first()
    assert guardian is not None
    assert registration.payer_contact_id == guardian.id


@pytest.mark.asyncio
async def test_row_with_dob_grade_organization_sets_them_on_the_contact(db):
    """2026-07-24, CEO request: date_of_birth/grade/organization are purely
    informational columns, optional, no enforcement derived from them."""
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    wb_bytes = _build_workbook([_student_row(
        email="student.with.school@example.com",
        date_of_birth="2012-05-14", grade="Grade 7", organization="Dubai International School",
    )])

    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")
    assert batch.counts["summary"]["create"] == 1
    await commit_batch(db, batch.id)

    student = (await db.execute(
        select(Contact).where(Contact.email == "student.with.school@example.com")
    )).scalars().first()
    assert student.grade == "Grade 7"
    assert str(student.date_of_birth) == "2012-05-14"

    org = (await db.execute(
        select(Organization).where(Organization.id == student.organization_id)
    )).scalars().first()
    assert org is not None
    assert org.name_latin == "Dubai International School"
    assert org.org_type == "school"


@pytest.mark.asyncio
async def test_two_rows_same_school_different_case_resolve_to_one_organization(db):
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    wb_bytes = _build_workbook([
        _student_row(email="sibling.one@example.com", phone="0501112222", organization="Greenwood Academy"),
        _student_row(email="sibling.two@example.com", phone="0503334444", organization="  greenwood academy  "),
    ])

    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")
    await commit_batch(db, batch.id)

    org_count = await db.scalar(
        select(func.count()).select_from(Organization).where(Organization.name_latin == "Greenwood Academy")
    )
    assert org_count == 1


@pytest.mark.asyncio
async def test_unparseable_date_of_birth_is_silently_dropped_not_an_error(db):
    """date_of_birth is optional and best-effort — a messy value must not
    fail the whole row."""
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    wb_bytes = _build_workbook([_student_row(email="messy.dob@example.com", date_of_birth="not a date")])

    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")
    assert batch.counts["summary"]["create"] == 1
    await commit_batch(db, batch.id)

    student = (await db.execute(select(Contact).where(Contact.email == "messy.dob@example.com"))).scalars().first()
    assert student.date_of_birth is None


@pytest.mark.asyncio
async def test_acceptance_fifty_row_sheet_with_three_planted_duplicates(db):
    """Acceptance scenario from the spec: a realistic 50-row sheet including
    3 planted duplicates -> zero duplicate contacts created. The spec's own
    wording says "3 links or reviews", but a duplicate row for the SAME
    cohort as its earlier occurrence is more precisely "already_registered"
    (an idempotent no-op) rather than "link" (which creates a NEW
    registration for an existing contact) — "link" is what happens when the
    existing contact isn't yet registered for *this* cohort (e.g. they came
    from a different program earlier). Both are covered by dedicated tests;
    this one exercises the exact scenario the spec describes."""
    cohort = await _make_cohort(db)
    uploader = await _make_uploader(db)
    rows = [_student_row(email=f"bulk{i}@example.com", phone=f"050{i:07d}") for i in range(47)]
    # Plant 3 duplicates of earlier rows, same cohort -> already_registered.
    rows.append(_student_row(email="bulk0@example.com", phone="0500000000"))
    rows.append(_student_row(email="bulk10@example.com", phone="0500000010"))
    rows.append(_student_row(email="bulk20@example.com", phone="0500000020"))
    assert len(rows) == 50

    wb_bytes = _build_workbook(rows)
    batch = await dry_run(db, file_bytes=wb_bytes, cohort_id=cohort.id, uploaded_by=uploader.id, source="b2b_sheet")

    summary = batch.counts["summary"]
    assert summary["total"] == 50
    assert summary["create"] == 47
    assert summary["link"] + summary["review"] + summary["already_registered"] == 3
    assert summary["error"] == 0

    await commit_batch(db, batch.id)

    distinct_emails = (await db.execute(
        select(func.count(func.distinct(Contact.email))).where(Contact.email.like("bulk%@example.com"))
    )).scalar_one()
    total_bulk_contacts = (await db.execute(
        select(func.count()).select_from(Contact).where(Contact.email.like("bulk%@example.com"))
    )).scalar_one()
    assert distinct_emails == total_bulk_contacts == 47  # no duplicates


@pytest.mark.asyncio
async def test_template_download_has_expected_headers():
    wb = openpyxl.load_workbook(io.BytesIO(generate_template_xlsx()))
    headers = [c.value for c in wb.active[1]]
    assert headers == [name for name, _ in TEMPLATE_COLUMNS]
