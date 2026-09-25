"""LM1-7 service tests — get_or_create_student_account, curriculum
auto-enroll, and enrollment status following registration status. Direct
service calls (no HTTP layer) — the router wiring is covered separately in
tests/routers/sessions/test_desk_register_lms.py.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.lms import Course, Enrollment
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program
from app.services.lms.ops_integration import (
    deactivate_registration_enrollments,
    get_or_create_student_account,
    send_registered_notice_email,
    send_set_password_email,
    sync_registration_lms,
)


async def _contact(db, *, email="student@example.com", full_name="Ada Lovelace") -> Contact:
    contact = Contact(id=uuid.uuid4(), full_name=full_name, contact_roles=["student"], email=email)
    db.add(contact)
    await db.flush()
    return contact


async def _program_cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    return program, cohort


async def _course(db, *, author) -> Course:
    course = Course(id=uuid.uuid4(), title="Course", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    return course


async def _registration(db, *, contact, cohort) -> Registration:
    reg = Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        status="registered", ticket_token=uuid.uuid4().hex, registered_via="desk",
        payment_status="waived",
    )
    db.add(reg)
    await db.flush()
    return reg


async def _author(db) -> User:
    author = User(
        id=uuid.uuid4(), full_name="Author", email=f"author-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(author)
    await db.flush()
    return author


# ── get_or_create_student_account ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_creates_a_new_student_account_with_a_random_password(db):
    contact = await _contact(db)
    await db.commit()

    user, created = await get_or_create_student_account(db, contact.id)
    assert created is True
    assert user.contact_id == contact.id
    assert user.roles == ["student"]
    assert user.must_change_password is True
    assert user.email == contact.email


@pytest.mark.asyncio
async def test_reuses_an_existing_account_linked_to_the_contact_and_adds_student_role(db):
    contact = await _contact(db)
    existing = User(
        id=uuid.uuid4(), full_name="Existing", email="existing@example.com",
        password_hash="x", roles=["instructor"], contact_id=contact.id, status="active",
    )
    db.add(existing)
    await db.commit()

    user, created = await get_or_create_student_account(db, contact.id)
    assert created is False
    assert user.id == existing.id
    assert set(user.role_values) == {"instructor", "student"}


@pytest.mark.asyncio
async def test_repeated_lookups_return_the_same_account(db):
    """B4 mitigation: the lookup carries a deterministic .order_by regardless
    of whether duplicates are even possible — belt-and-suspenders alongside
    D1's UNIQUE(users.contact_id) (Phase 2 Stage 1), which now makes a
    duplicate impossible to create in the first place (see the test below)."""
    contact = await _contact(db)
    existing = User(
        id=uuid.uuid4(), full_name="The Account", email="the-account@example.com",
        password_hash="x", roles=["student"], contact_id=contact.id, status="active",
    )
    db.add(existing)
    await db.commit()

    first, _ = await get_or_create_student_account(db, contact.id)
    second, _ = await get_or_create_student_account(db, contact.id)
    assert first.id == existing.id
    assert second.id == existing.id


@pytest.mark.asyncio
async def test_a_second_account_on_the_same_contact_violates_the_d1_constraint(db):
    """D1 (Phase 2 Stage 1): one account per contact, enforced by
    UNIQUE(users.contact_id) — not just convention. B4's duplicate-account
    scenario this test used to construct is no longer a valid DB state."""
    from sqlalchemy.exc import IntegrityError

    contact = await _contact(db)
    db.add(User(
        id=uuid.uuid4(), full_name="First Account", email="first@example.com",
        password_hash="x", roles=["student"], contact_id=contact.id, status="active",
    ))
    await db.commit()

    db.add(User(
        id=uuid.uuid4(), full_name="Second Account", email="second@example.com",
        password_hash="x", roles=["student"], contact_id=contact.id, status="active",
    ))
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_no_email_skips_account_creation_without_raising(db):
    contact = await _contact(db, email=None)
    await db.commit()

    user, created = await get_or_create_student_account(db, contact.id)
    assert user is None and created is False


@pytest.mark.asyncio
async def test_email_collision_with_a_different_account_reuses_user_and_adds_student_role(db):
    contact = await _contact(db, email="taken@example.com")
    other = User(
        id=uuid.uuid4(), full_name="Someone Else", email="taken@example.com",
        password_hash="x", roles=["ambassador"], status="active",
    )
    db.add(other)
    await db.commit()

    user, created = await get_or_create_student_account(db, contact.id)
    assert user is not None and created is False
    assert user.id == other.id
    assert "student" in user.role_values


async def _attach_checklist(db, *, program, courses: list[Course]) -> LmsProgram:
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Ops Integration Checklist")
    db.add(lms_program)
    await db.flush()
    for i, course in enumerate(courses, start=1):
        db.add(LmsProgramItem(
            id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=i,
            item_type="course", title=course.title, course_id=course.id,
        ))
    return lms_program


# ── assign_lms_program (formerly enroll_in_cohort_curriculum) ───────────────

@pytest.mark.asyncio
async def test_enrolls_in_every_checklist_course(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course_a = await _course(db, author=author)
    course_b = await _course(db, author=author)
    await _attach_checklist(db, program=program, courses=[course_a, course_b])
    contact = await _contact(db)
    student = User(
        id=uuid.uuid4(), full_name="S", email="s@example.com", password_hash="x",
        roles=["student"], contact_id=contact.id, status="active",
    )
    db.add(student)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()

    assignment = await assign_lms_program(
        db, user_id=student.id, cohort_id=cohort.id, registration_id=registration.id,
    )
    assert assignment is not None
    enrollments = (await db.execute(select(Enrollment).where(Enrollment.user_id == student.id))).scalars().all()
    assert {e.course_id for e in enrollments} == {course_a.id, course_b.id}
    assert all(e.source == "registration" and e.registration_id == registration.id for e in enrollments)


# ── sync_registration_lms + deactivate ──────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_registration_lms_creates_account_and_enrolls(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=author)
    await _attach_checklist(db, program=program, courses=[course])
    contact = await _contact(db)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()

    user = await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=True)
    assert user is not None and user.contact_id == contact.id

    rows = (await db.execute(select(Enrollment).where(Enrollment.user_id == user.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].course_id == course.id and rows[0].registration_id == registration.id


@pytest.mark.asyncio
async def test_sync_registration_lms_new_account_email_mentions_the_program(db, monkeypatch):
    program, cohort = await _program_cohort(db)
    contact = await _contact(db)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()
    captured = _capture_send(monkeypatch)

    await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=True)

    assert captured["subject"] == "Your SpacePoint learning account"
    assert f"You're registered for {program.name} ({cohort.name})." in captured["body"]
    assert "Step 1" in captured["body"]


@pytest.mark.asyncio
async def test_sync_registration_lms_emails_a_returning_student_a_plain_registered_notice(db, monkeypatch):
    """2026-09-10: previously an already-existing account registering for a
    new cohort got nothing at all. Now it gets send_registered_notice_email —
    same send_welcome_email gate, different content (no token/password step)."""
    program, cohort = await _program_cohort(db)
    contact = await _contact(db)
    existing = User(
        id=uuid.uuid4(), full_name="Ada Lovelace", email=contact.email, password_hash="x",
        roles=["student"], contact_id=contact.id, status="active",
    )
    db.add(existing)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()
    captured = _capture_send(monkeypatch)

    user = await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=True)

    assert user is not None and user.id == existing.id
    assert captured["subject"] == f"You're registered — {program.name} ({cohort.name})"
    assert "Step 1" not in captured["body"]


@pytest.mark.asyncio
async def test_sync_registration_lms_respects_send_welcome_email_false_for_a_returning_student_too(db, monkeypatch):
    program, cohort = await _program_cohort(db)
    contact = await _contact(db)
    existing = User(
        id=uuid.uuid4(), full_name="Ada Lovelace", email=contact.email, password_hash="x",
        roles=["student"], contact_id=contact.id, status="active",
    )
    db.add(existing)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()
    sent = False

    async def _fake(*args, **kwargs):
        nonlocal sent
        sent = True
        return True

    monkeypatch.setattr("app.services.lms.ops_integration.try_send_email", _fake)

    await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=True, send_welcome_email=False)

    assert sent is False


@pytest.mark.asyncio
async def test_sync_registration_lms_noop_when_create_account_false(db):
    program, cohort = await _program_cohort(db)
    contact = await _contact(db)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()

    user = await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=False)
    assert user is None
    assert (await db.execute(select(User).where(User.contact_id == contact.id))).first() is None


@pytest.mark.asyncio
async def test_deactivate_registration_enrollments_flips_active_rows_only(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=author)
    contact = await _contact(db)
    registration = await _registration(db, contact=contact, cohort=cohort)
    student = User(
        id=uuid.uuid4(), full_name="S", email="s2@example.com", password_hash="x",
        roles=["student"], contact_id=contact.id, status="active",
    )
    db.add(student)
    await db.flush()
    enrollment = Enrollment(
        id=uuid.uuid4(), user_id=student.id, course_id=course.id, source="registration",
        program_id=program.id, registration_id=registration.id, status="active",
    )
    db.add(enrollment)
    await db.commit()

    await deactivate_registration_enrollments(db, registration.id)
    await db.commit()
    await db.refresh(enrollment)
    assert enrollment.status == "inactive"


# ── send_set_password_email — audience-specific copy (2026-09-10) ──────────

async def _new_user(db, *, roles: list[str]) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Priya Nair", email=f"priya-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles, status="active",
    )
    db.add(user)
    await db.commit()
    return user


def _capture_send(monkeypatch):
    """Stands in for `try_send_email` so a test can inspect the exact
    subject/body without needing real SMTP — same technique other tests in
    this file already use for the LMS side of this function."""
    captured = {}

    async def _fake(to, subject, body, **kwargs):
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        return True

    monkeypatch.setattr("app.services.lms.ops_integration.try_send_email", _fake)
    return captured


@pytest.mark.asyncio
async def test_judge_audience_copy_never_says_learning_account(db, monkeypatch):
    """The bug report this fixes: a judge invite calling itself a
    "learning account" is confusing since judges never touch the LMS."""
    judge = await _new_user(db, roles=["judge"])
    captured = _capture_send(monkeypatch)

    await send_set_password_email(judge, purpose="welcome", audience="judge")

    assert captured["subject"] == "Your SpacePoint judge account"
    assert "learning" not in captured["subject"].lower()
    assert "learning" not in captured["body"].lower()
    assert "judge" in captured["body"].lower()


@pytest.mark.asyncio
async def test_judge_email_links_to_the_portal_login_not_the_lms_login(db, monkeypatch):
    judge = await _new_user(db, roles=["judge"])
    captured = _capture_send(monkeypatch)

    await send_set_password_email(judge, purpose="welcome", audience="judge")

    assert f"{settings.FRONTEND_URL}/login" in captured["body"]
    assert f"{settings.FRONTEND_URL}/learn/login" not in captured["body"]
    assert f"{settings.FRONTEND_URL}/set-password?token=" in captured["body"]


@pytest.mark.asyncio
async def test_student_email_links_to_the_lms_login(db, monkeypatch):
    student = await _new_user(db, roles=["student"])
    captured = _capture_send(monkeypatch)

    await send_set_password_email(student, purpose="welcome", audience="student")

    assert captured["subject"] == "Your SpacePoint learning account"
    assert f"{settings.FRONTEND_URL}/learn/login" in captured["body"]
    assert f"{settings.FRONTEND_URL}/learn/set-password?token=" in captured["body"]


@pytest.mark.asyncio
async def test_default_audience_is_the_generic_portal_copy(db, monkeypatch):
    """No caller-supplied audience (e.g. the public forgot-password flow,
    which serves every role from one form) — falls back to copy that
    doesn't claim any specific surface."""
    staff = await _new_user(db, roles=["operations"])
    captured = _capture_send(monkeypatch)

    await send_set_password_email(staff, purpose="reset")

    assert captured["subject"] == "Your SpacePoint account"
    assert "learning" not in captured["subject"].lower()
    assert "judge" not in captured["body"].lower()


@pytest.mark.asyncio
async def test_body_spells_out_both_steps_as_a_fallback_to_the_button(db, monkeypatch):
    judge = await _new_user(db, roles=["judge"])
    captured = _capture_send(monkeypatch)

    await send_set_password_email(judge, purpose="welcome", audience="judge")

    assert "Step 1" in captured["body"]
    assert "Step 2" in captured["body"]
    body_lower = captured["body"].lower()
    assert body_lower.index("step 1") < body_lower.index("step 2")


@pytest.mark.asyncio
async def test_new_account_intro_mentions_the_program_when_context_is_given(db, monkeypatch):
    student = await _new_user(db, roles=["student"])
    captured = _capture_send(monkeypatch)

    await send_set_password_email(student, purpose="welcome", audience="student", context="Ru'ya Qualifier")

    assert "You're registered for Ru'ya Qualifier." in captured["body"]
    assert "An account was created for you" not in captured["body"]


# ── send_registered_notice_email — the "existing account" sibling ──────────

@pytest.mark.asyncio
async def test_registered_notice_has_no_token_just_a_login_link(db, monkeypatch):
    student = await _new_user(db, roles=["student"])
    captured = _capture_send(monkeypatch)

    await send_registered_notice_email(student, audience="student", context="Ru'ya Qualifier")

    assert captured["subject"] == "You're registered — Ru'ya Qualifier"
    assert "You're registered for Ru'ya Qualifier." in captured["body"]
    assert f"{settings.FRONTEND_URL}/learn/login" in captured["body"]
    assert "token=" not in captured["body"]
    assert "Step 1" not in captured["body"]


@pytest.mark.asyncio
async def test_registered_notice_for_a_judge_links_to_the_portal_login(db, monkeypatch):
    judge = await _new_user(db, roles=["judge"])
    captured = _capture_send(monkeypatch)

    await send_registered_notice_email(judge, audience="judge", context="Ru'ya Finalist")

    assert captured["subject"] == "You're confirmed as a judge — Ru'ya Finalist"
    assert "You've been registered as a judge for Ru'ya Finalist." in captured["body"]
    assert f"{settings.FRONTEND_URL}/login" in captured["body"]
    assert f"{settings.FRONTEND_URL}/learn/login" not in captured["body"]
