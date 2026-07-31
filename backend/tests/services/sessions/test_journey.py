"""Materials, responsibilities and the payment bridge (I5-5 … I5-8).

Deliberately one test per decision that could be got wrong, not per branch.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.instructors.payment import PaymentLetter, PaymentSession
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.sessions import journey as svc
from app.services.sessions import materials as mat


async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) or ["instructor"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _chain(db, *, duration=None):
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="Prog",
        program_type="workshop", pricing_model="free", active=True, duration_hours=duration,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="C", status="running", location="Dubai"
    )
    db.add(cohort)
    await db.flush()
    session = Session(
        id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 7, 12), title="Orbits"
    )
    db.add(session)
    await db.flush()
    return program, cohort, session


async def _link(db, user, *, title, **owner):
    return await mat.add_material(db, user=user, title=title, url="https://example.com/x", **owner)


# ── I5-6: materials override, never merge ───────────────────────────────────

@pytest.mark.asyncio
async def test_the_nearest_level_with_materials_wins_outright(db):
    """Override, not merge. Merging would make it impossible to *remove* a
    program-level file for one cohort, which is what overridable has to mean."""
    ops = await _user(db, "operations")
    program, cohort, session = await _chain(db)

    await _link(db, ops, title="Program deck", program_id=program.id)
    rows, level = await mat.resolve_for_session(db, session)
    assert level == "program" and [m.title for m in rows] == ["Program deck"]

    await _link(db, ops, title="Cohort deck", cohort_id=cohort.id)
    rows, level = await mat.resolve_for_session(db, session)
    assert level == "cohort" and [m.title for m in rows] == ["Cohort deck"]

    await _link(db, ops, title="Session deck", session_id=session.id)
    rows, level = await mat.resolve_for_session(db, session)
    assert level == "session" and [m.title for m in rows] == ["Session deck"]


@pytest.mark.asyncio
async def test_a_session_with_nothing_anywhere_reports_none(db):
    _p, _c, session = await _chain(db)
    rows, level = await mat.resolve_for_session(db, session)
    assert rows == [] and level == "none"


@pytest.mark.asyncio
async def test_a_material_needs_exactly_one_owner_and_one_source(db):
    ops = await _user(db, "operations")
    program, cohort, _s = await _chain(db)

    with pytest.raises(HTTPException):          # two owners
        await _link(db, ops, title="x", program_id=program.id, cohort_id=cohort.id)
    with pytest.raises(HTTPException):          # no owner
        await _link(db, ops, title="x")
    with pytest.raises(HTTPException):          # neither file nor link
        await mat.add_material(db, user=ops, title="x", program_id=program.id)


# ── I5-5: responsibilities ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accepting_a_stale_version_is_refused(db):
    """If ops edits the wording while an invite is open, the acceptance that
    comes back is for text the instructor never saw."""
    instructor = await _user(db)
    _p, _c, session = await _chain(db)
    interest = InstructorInterest(
        id=uuid.uuid4(), session_id=session.id, user_id=instructor.id
    )
    db.add(interest)
    await db.flush()

    _text, v1 = await svc.set_responsibilities(db, "Arrive 30 minutes early.")
    await svc.set_responsibilities(db, "Arrive 45 minutes early.")

    with pytest.raises(HTTPException) as exc:
        await svc.accept_responsibilities(db, interest=interest, version=v1)
    assert exc.value.status_code == 409

    _text, v2 = await svc.get_responsibilities(db)
    await svc.accept_responsibilities(db, interest=interest, version=v2)
    assert interest.responsibilities_accepted_at is not None
    assert interest.responsibilities_version == v2


@pytest.mark.asyncio
async def test_the_version_changes_only_when_the_words_do(db):
    _t, a = await svc.set_responsibilities(db, "Same text")
    _t, b = await svc.set_responsibilities(db, "Same text")
    _t, c = await svc.set_responsibilities(db, "Different text")
    assert a == b and a != c



@pytest.mark.asyncio
async def test_role_with_no_description_is_identical_to_the_general_text(db):
    """A role that hasn't had its own wording written yet must not silently
    invalidate every acceptance already recorded against the general-only
    version — same text, same hash."""
    await svc.set_responsibilities(db, "Arrive 30 minutes early.")
    role = DeliveryRole(id=uuid.uuid4(), name="Lead", sort_order=1)
    db.add(role)
    await db.flush()

    general_text, general_version = await svc.get_responsibilities(db)
    role_text, role_version, role_name = await svc.get_responsibilities_for_role(db, role.id)
    assert (role_text, role_version) == (general_text, general_version)
    assert role_name == "Lead"


@pytest.mark.asyncio
async def test_a_roles_own_description_is_combined_and_gets_its_own_version(db):
    """§ the operator's actual complaint: picking a role should show that
    role's responsibilities, not a generic blob agreed to regardless of it."""
    await svc.set_responsibilities(db, "Arrive 30 minutes early.")
    lead = DeliveryRole(id=uuid.uuid4(), name="Lead", sort_order=1, description="Carry the kit.")
    assistant = DeliveryRole(id=uuid.uuid4(), name="Assistant", sort_order=2, description="Help set up.")
    db.add_all([lead, assistant])
    await db.flush()

    lead_text, lead_version, lead_name = await svc.get_responsibilities_for_role(db, lead.id)
    asst_text, asst_version, asst_name = await svc.get_responsibilities_for_role(db, assistant.id)

    assert "Arrive 30 minutes early." in lead_text and "Carry the kit." in lead_text
    assert "Help set up." in asst_text and "Carry the kit." not in asst_text
    assert lead_version != asst_version
    assert lead_name == "Lead" and asst_name == "Assistant"


@pytest.mark.asyncio
async def test_accepting_is_checked_against_the_interests_own_role(db):
    """The version an instructor submits has to match *their* role's combined
    text — not the general text, and not another role's."""
    instructor = await _user(db)
    _p, _c, session = await _chain(db)
    lead = DeliveryRole(id=uuid.uuid4(), name="Lead", sort_order=1, description="Carry the kit.")
    db.add(lead)
    await db.flush()

    interest = InstructorInterest(
        id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role_id=lead.id,
    )
    db.add(interest)
    await db.flush()

    _general_text, general_version = await svc.get_responsibilities(db)
    with pytest.raises(HTTPException) as exc:
        await svc.accept_responsibilities(db, interest=interest, version=general_version)
    assert exc.value.status_code == 409

    _lead_text, lead_version, _name = await svc.get_responsibilities_for_role(db, lead.id)
    await svc.accept_responsibilities(db, interest=interest, version=lead_version)
    assert interest.responsibilities_version == lead_version


# ── I5-8: the payment bridge ────────────────────────────────────────────────

async def _delivered(db, instructor, *, duration=None):
    program, cohort, session = await _chain(db, duration=duration)
    role_id = await db.scalar(
        select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator")
    )
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role_id=role_id
    ))
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return session


@pytest.mark.asyncio
async def test_a_completed_session_is_billable_and_prefilled_from_real_data(db):
    instructor = await _user(db)
    session = await _delivered(db, instructor, duration=Decimal("3"))

    [row] = await svc.unbilled_sessions(db, instructor.id)
    assert row["session_id"] == session.id
    assert row["session_date"] == "12/07/2026"       # as the document prints it
    assert row["workshop_description"] == "Orbits"
    assert row["role"] == "Lead Facilitator"
    assert row["location"] == "Dubai"
    assert row["duration_hours"] == 3.0             # inherited from the program


@pytest.mark.asyncio
async def test_an_unfinished_session_is_not_billable(db):
    instructor = await _user(db)
    _p, _c, session = await _chain(db)
    role_id = await db.scalar(
        select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator")
    )
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role_id=role_id
    ))
    await db.flush()
    assert await svc.unbilled_sessions(db, instructor.id) == []


@pytest.mark.asyncio
async def test_a_session_already_on_a_letter_drops_off_the_list(db):
    """The FK's presence is what prevents double-billing — there is no
    separate flag to keep honest."""
    instructor = await _user(db)
    session = await _delivered(db, instructor)

    letter = PaymentLetter(id=uuid.uuid4(), instructor_user_id=instructor.id, reference="R")
    db.add(letter)
    await db.flush()
    db.add(PaymentSession(
        id=uuid.uuid4(), payment_letter_id=letter.id, session_id=session.id,
        workshop_description="Orbits", role="Lead Facilitator", compensation_aed=500,
    ))
    await db.flush()

    assert await svc.unbilled_sessions(db, instructor.id) == []


@pytest.mark.asyncio
async def test_paying_the_lead_leaves_the_assistant_still_billable(db):
    """One session, several people paid — `session_openings` exists to offer
    "1 Lead Facilitator at 2000 and 2 Assistants at 400", so each is billed
    separately.

    Regression: "already billed" was asked globally rather than per
    instructor, so paying the lead silently removed the session from the
    assistant's list. They could never be offered it again, and nothing
    surfaced that it had gone — the session simply stopped appearing.
    """
    lead, assistant = await _user(db), await _user(db)
    _p, _c, session = await _chain(db)

    for user, role_name in ((lead, "Lead Facilitator"), (assistant, "Assistant Facilitator")):
        db.add(SessionInstructor(
            id=uuid.uuid4(), session_id=session.id, user_id=user.id,
            role_id=await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == role_name)),
        ))
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()

    assert len(await svc.unbilled_sessions(db, lead.id)) == 1
    assert len(await svc.unbilled_sessions(db, assistant.id)) == 1

    letter = PaymentLetter(id=uuid.uuid4(), instructor_user_id=lead.id, reference="R")
    db.add(letter)
    await db.flush()
    db.add(PaymentSession(
        id=uuid.uuid4(), payment_letter_id=letter.id, session_id=session.id,
        workshop_description="Orbits", role="Lead Facilitator", compensation_aed=2000,
    ))
    await db.flush()

    assert await svc.unbilled_sessions(db, lead.id) == [], "the lead is paid"
    assert len(await svc.unbilled_sessions(db, assistant.id)) == 1, (
        "the assistant delivered it too and has not been paid"
    )


@pytest.mark.asyncio
async def test_somebody_elses_session_is_not_billable_to_you(db):
    mine, theirs = await _user(db), await _user(db)
    await _delivered(db, theirs)
    assert await svc.unbilled_sessions(db, mine.id) == []
