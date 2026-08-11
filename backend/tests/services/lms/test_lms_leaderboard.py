"""P2-4 (LMS Phase 2 Stage 2, 2026-08-10) — leaderboard: derived (SUM...
GROUP BY, never cached), cohort- or global-scoped. Display names went from
a D6-pending stand-in to nickname-first (Live Games Phase 2C, 8-2) once
services/nicknames.py (8-1) gave every student a public identity. Redis-free,
HTTP-free.
"""

import uuid

import pytest

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.leaderboard import _display_name, leaderboard
from app.services.lms.points import award_points
from app.services.nicknames import assign_nickname


async def _user(db, *, full_name="Student", contact_id=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name=full_name, email=f"lb-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact_id,
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"LB-{uuid.uuid4().hex[:8]}", name="Leaderboard Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Leaderboard Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    return cohort


async def _register(db, *, contact: Contact, cohort: Cohort) -> Registration:
    reg = Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        status="registered", ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    )
    db.add(reg)
    await db.flush()
    return reg


# ── _display_name: nickname-first, name-fallback for staff (8-2) ───────────

@pytest.mark.parametrize("full_name,expected", [
    ("Ahmed Al Ali", "Ahmed A."),
    ("Cher", "Cher"),
    ("  Noor   Hassan  ", "Noor H."),
    ("", "Student"),
])
def test_display_name_falls_back_to_first_name_and_last_initial_with_no_nickname(full_name, expected):
    assert _display_name(nickname=None, full_name=full_name) == expected


def test_display_name_prefers_the_nickname_when_present():
    assert _display_name(nickname="NebulaFalcon482", full_name="Ahmed Al Ali") == "NebulaFalcon482"


# ── leaderboard: global ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_global_leaderboard_ranks_by_total_points_descending(db):
    low = await _user(db, full_name="Low Scorer")
    high = await _user(db, full_name="High Scorer")
    await award_points(db, user_id=low.id, source="quiz", points=20, idempotency_key="a")
    await award_points(db, user_id=high.id, source="quiz", points=50, idempotency_key="b")
    await award_points(db, user_id=high.id, source="quiz", points=30, idempotency_key="c")
    await db.commit()

    rows = await leaderboard(db)
    by_user = {r["user_id"]: r for r in rows}
    assert by_user[high.id]["points"] == 80
    assert by_user[low.id]["points"] == 20
    assert by_user[high.id]["rank"] == 1
    assert by_user[low.id]["rank"] == 2


@pytest.mark.asyncio
async def test_leaderboard_excludes_users_with_no_points(db):
    scored = await _user(db, full_name="Scored")
    unscored = await _user(db, full_name="Unscored")
    await award_points(db, user_id=scored.id, source="quiz", points=10, idempotency_key="a")
    await db.commit()

    rows = await leaderboard(db)
    ids = {r["user_id"] for r in rows}
    assert scored.id in ids
    assert unscored.id not in ids


@pytest.mark.asyncio
async def test_leaderboard_display_name_is_never_the_full_legal_name(db):
    student = await _user(db, full_name="Ahmed Al Ali")
    await award_points(db, user_id=student.id, source="quiz", points=10, idempotency_key="a")
    await db.commit()

    rows = await leaderboard(db)
    assert rows[0]["display_name"] == "Ahmed A."
    assert rows[0]["display_name"] != "Ahmed Al Ali"


@pytest.mark.asyncio
async def test_leaderboard_shows_the_nickname_once_the_student_has_one(db):
    student = await _user(db, full_name="Ahmed Al Ali")
    await assign_nickname(db, student)
    await award_points(db, user_id=student.id, source="quiz", points=10, idempotency_key="a")
    await db.commit()

    rows = await leaderboard(db)
    assert rows[0]["display_name"] == student.nickname
    assert rows[0]["display_name"] != "Ahmed A."


# ── leaderboard: cohort scope ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cohort_scoped_leaderboard_excludes_students_in_a_different_cohort(db):
    cohort_a = await _cohort(db)
    cohort_b = await _cohort(db)

    contact_a = Contact(id=uuid.uuid4(), full_name="In Cohort A", contact_roles=["student"])
    contact_b = Contact(id=uuid.uuid4(), full_name="In Cohort B", contact_roles=["student"])
    db.add_all([contact_a, contact_b])
    await db.flush()
    student_a = await _user(db, full_name="In Cohort A", contact_id=contact_a.id)
    student_b = await _user(db, full_name="In Cohort B", contact_id=contact_b.id)
    await _register(db, contact=contact_a, cohort=cohort_a)
    await _register(db, contact=contact_b, cohort=cohort_b)

    await award_points(db, user_id=student_a.id, source="quiz", points=10, idempotency_key="a")
    await award_points(db, user_id=student_b.id, source="quiz", points=10, idempotency_key="b")
    await db.commit()

    rows = await leaderboard(db, cohort_id=cohort_a.id)
    ids = {r["user_id"] for r in rows}
    assert student_a.id in ids
    assert student_b.id not in ids


@pytest.mark.asyncio
async def test_cohort_scoped_leaderboard_excludes_a_cancelled_registration(db):
    cohort = await _cohort(db)
    contact = Contact(id=uuid.uuid4(), full_name="Cancelled Student", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = await _user(db, full_name="Cancelled Student", contact_id=contact.id)
    reg = await _register(db, contact=contact, cohort=cohort)
    reg.status = "cancelled"
    await award_points(db, user_id=student.id, source="quiz", points=10, idempotency_key="a")
    await db.commit()

    rows = await leaderboard(db, cohort_id=cohort.id)
    assert rows == []
