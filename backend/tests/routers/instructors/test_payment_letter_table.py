"""The editable payment-letter table (I5-1).

`PaymentSession` always had every column the generated document prints; only
three were reachable from the portal, and existing rows were read-only — which
is why the finished letter was being hand-fixed in Word. These tests pin the
two things that actually matter about the fix: that the previously
unreachable columns can now be set, and that a signed letter cannot be
rewritten underneath the signature.

Redis-free on the shared `client`.
"""

import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.enums import PaymentLetterStatus, PaymentSessionRole
from app.models.instructors.payment import PaymentAddon, PaymentLetter, PaymentSession
from app.models.user import User


async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=list(roles), status="active",
    )
    db.add(u)
    await db.flush()
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _letter(db, instructor, status=PaymentLetterStatus.draft) -> PaymentLetter:
    letter = PaymentLetter(
        id=uuid.uuid4(), instructor_user_id=instructor.id,
        reference="Facilitator Agreement", status=status,
    )
    db.add(letter)
    await db.flush()
    return letter


async def _row(db, letter, **kw) -> PaymentSession:
    row = PaymentSession(
        id=uuid.uuid4(), payment_letter_id=letter.id,
        workshop_description=kw.pop("workshop_description", "CubeSat workshop"),
        role=kw.pop("role", PaymentSessionRole.facilitator),
        compensation_aed=kw.pop("compensation_aed", 500),
        sort_order=kw.pop("sort_order", 1),
        **kw,
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.asyncio
async def test_the_three_columns_that_were_hand_fixed_in_word_can_now_be_set(client, db):
    """Date, location and duration had no path from the portal at all. This is
    the whole point of I5-1."""
    admin = await _user(db, "admin")
    instructor = await _user(db, "instructor")
    letter = await _letter(db, instructor)
    row = await _row(db, letter)

    r = await client.patch(
        f"/instructors/admin/payments/sessions/{row.id}",
        json={
            "session_date": "12/07/2026",
            "location": "Dubai",
            "duration_hours": 3.5,
            "role": "Lead Facilitator",
        },
        headers=_headers(admin),
    )
    assert r.status_code == 200
    [out] = r.json()["sessions"]
    assert out["session_date"] == "12/07/2026"
    assert out["location"] == "Dubai"
    assert out["duration_hours"] == 3.5
    assert out["role"] == "Lead Facilitator"


@pytest.mark.asyncio
async def test_an_omitted_field_is_left_alone_and_an_explicit_null_clears_it(client, db):
    """`exclude_unset` is what lets the table save one cell without
    resubmitting — and without silently blanking the rest of the row."""
    admin = await _user(db, "admin")
    instructor = await _user(db, "instructor")
    letter = await _letter(db, instructor)
    row = await _row(db, letter, location="Dubai", session_date="01/01/2026")

    r = await client.patch(
        f"/instructors/admin/payments/sessions/{row.id}",
        json={"compensation_aed": 750}, headers=_headers(admin),
    )
    [out] = r.json()["sessions"]
    assert out["compensation_aed"] == 750
    assert out["location"] == "Dubai"          # untouched
    assert out["session_date"] == "01/01/2026"

    r = await client.patch(
        f"/instructors/admin/payments/sessions/{row.id}",
        json={"location": None}, headers=_headers(admin),
    )
    [out] = r.json()["sessions"]
    assert out["location"] is None


@pytest.mark.asyncio
async def test_reordering_is_two_sort_order_writes_and_the_list_follows(client, db):
    """The document reads `sort_order`, so swapping it is all reordering is —
    nothing else has to know about ordering."""
    admin = await _user(db, "admin")
    instructor = await _user(db, "instructor")
    letter = await _letter(db, instructor)
    first = await _row(db, letter, workshop_description="First", sort_order=1)
    second = await _row(db, letter, workshop_description="Second", sort_order=2)

    await client.patch(f"/instructors/admin/payments/sessions/{first.id}",
                       json={"sort_order": 2}, headers=_headers(admin))
    r = await client.patch(f"/instructors/admin/payments/sessions/{second.id}",
                           json={"sort_order": 1}, headers=_headers(admin))

    assert [s["workshop_description"] for s in r.json()["sessions"]] == ["Second", "First"]


@pytest.mark.asyncio
async def test_a_signed_letter_cannot_be_rewritten_under_the_signature(client, db):
    """The stored signed PDF is what the instructor put their name to, and the
    table is what a regenerated document and the certificates are built from.
    Correcting a signed letter is a new letter, not an edit."""
    admin = await _user(db, "admin")
    instructor = await _user(db, "instructor")
    letter = await _letter(db, instructor, status=PaymentLetterStatus.signed)
    row = await _row(db, letter)

    r = await client.patch(
        f"/instructors/admin/payments/sessions/{row.id}",
        json={"compensation_aed": 99999}, headers=_headers(admin),
    )
    assert r.status_code == 409
    assert "signed" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_every_write_path_is_shut_once_the_letter_is_signed(client, db):
    """Not just editing. Adding a line to a signed letter, or deleting one off
    it, changes the document just as much — and the delete paths predate I5-1
    with no guard at all. All four are enumerated here because this is the
    kind of restriction a later change quietly reopens."""
    admin = await _user(db, "admin")
    instructor = await _user(db, "instructor")
    letter = await _letter(db, instructor, status=PaymentLetterStatus.signed)
    row = await _row(db, letter)
    addon = PaymentAddon(
        id=uuid.uuid4(), payment_letter_id=letter.id,
        description="Poster printing", amount_aed=200, sort_order=1,
    )
    db.add(addon)
    await db.flush()

    calls = [
        client.post(f"/instructors/admin/payments/letters/{letter.id}/sessions",
                    json={"workshop_description": "Sneaked in", "role": "Facilitator",
                          "compensation_aed": 100}, headers=_headers(admin)),
        client.post(f"/instructors/admin/payments/letters/{letter.id}/addons",
                    json={"description": "Sneaked in", "amount_aed": 100},
                    headers=_headers(admin)),
        client.delete(f"/instructors/admin/payments/sessions/{row.id}", headers=_headers(admin)),
        client.delete(f"/instructors/admin/payments/addons/{addon.id}", headers=_headers(admin)),
    ]
    for call in calls:
        assert (await call).status_code == 409

    # And nothing actually changed underneath the signature.
    r = await client.get("/instructors/admin/payments/letters", headers=_headers(admin))
    [out] = [x for x in r.json() if x["id"] == str(letter.id)]
    assert len(out["sessions"]) == 1 and len(out["addons"]) == 1


@pytest.mark.asyncio
async def test_a_draft_letters_lines_can_still_be_added_and_deleted(client, db):
    """The guard must not seize up the normal case."""
    admin = await _user(db, "admin")
    instructor = await _user(db, "instructor")
    letter = await _letter(db, instructor)
    row = await _row(db, letter)

    r = await client.post(
        f"/instructors/admin/payments/letters/{letter.id}/sessions",
        json={"workshop_description": "Second", "role": "Facilitator", "compensation_aed": 100},
        headers=_headers(admin),
    )
    assert r.status_code == 201 and len(r.json()["sessions"]) == 2

    r = await client.delete(
        f"/instructors/admin/payments/sessions/{row.id}", headers=_headers(admin)
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_addons_are_editable_on_the_same_terms(client, db):
    admin = await _user(db, "admin")
    instructor = await _user(db, "instructor")
    letter = await _letter(db, instructor)
    addon = PaymentAddon(
        id=uuid.uuid4(), payment_letter_id=letter.id,
        description="Poster printing", amount_aed=200, sort_order=1,
    )
    db.add(addon)
    await db.flush()

    r = await client.patch(
        f"/instructors/admin/payments/addons/{addon.id}",
        json={"amount_aed": 250, "notes": "agreed with ops"}, headers=_headers(admin),
    )
    assert r.status_code == 200
    [out] = r.json()["addons"]
    assert out["amount_aed"] == 250 and out["notes"] == "agreed with ops"


@pytest.mark.asyncio
async def test_only_an_admin_can_edit_the_table(client, db):
    instructor = await _user(db, "instructor")
    letter = await _letter(db, instructor)
    row = await _row(db, letter)

    r = await client.patch(
        f"/instructors/admin/payments/sessions/{row.id}",
        json={"compensation_aed": 1}, headers=_headers(instructor),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_editing_a_row_that_does_not_exist_is_404(client, db):
    admin = await _user(db, "admin")
    r = await client.patch(
        f"/instructors/admin/payments/sessions/{uuid.uuid4()}",
        json={"compensation_aed": 1}, headers=_headers(admin),
    )
    assert r.status_code == 404


# ── cohort lines (2026-08-24) ───────────────────────────────────────────────
# `bill-sessions` changed shape: it takes `line_ids` (a cohort id, or a session
# id for work outside any cohort assignment) rather than `session_ids`, and the
# amount now arrives pre-computed instead of at 0. Nothing covered this
# endpoint before, so these are the first tests of it.

@pytest.mark.asyncio
async def test_billing_a_cohort_line_prefills_the_amount_and_records_coverage(db, client):
    import uuid as _uuid
    from datetime import date as _date, datetime as _datetime, timezone as _timezone
    from decimal import Decimal as _Decimal

    from sqlalchemy import select

    from app.models.instructors.payment import PaymentLetter, PaymentSession
    from app.models.sessions.cohort import Cohort
    from app.models.sessions.cohort_assignment import CohortInstructorAssignment
    from app.models.sessions.delivery_role import DeliveryRole
    from app.models.sessions.payment_coverage import PaymentSessionCoverage
    from app.models.sessions.program import Program
    from app.models.sessions.session import Session, SessionInstructor
    from app.models.user import User

    admin = await _user(db, "admin")
    admin_headers = _headers(admin)
    instructor = await _user(db, "instructor")
    program = Program(
        id=_uuid.uuid4(), code=f"BL-{_uuid.uuid4().hex[:8]}", name="Billing Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=_uuid.uuid4(), program_id=program.id, name="Billing Cohort",
        status="running", visibility="public",
        starts_on=_date(2026, 10, 10), ends_on=_date(2026, 10, 11),
    )
    db.add(cohort)
    await db.flush()

    role_id = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator"))
    sessions = []
    for i in range(2):
        s = Session(
            id=_uuid.uuid4(), cohort_id=cohort.id, meeting_date=_date(2026, 10, 10 + i),
            completed_at=_datetime.now(_timezone.utc),
        )
        db.add(s)
        sessions.append(s)
    await db.flush()
    for s in sessions:
        db.add(SessionInstructor(
            id=_uuid.uuid4(), session_id=s.id, user_id=instructor.id, role_id=role_id,
        ))
    db.add(CohortInstructorAssignment(
        id=_uuid.uuid4(), cohort_id=cohort.id, user_id=instructor.id, role_id=role_id,
        rate_basis="per_session", rate_aed=_Decimal("500.00"), status="active",
    ))
    letter = PaymentLetter(id=_uuid.uuid4(), instructor_user_id=instructor.id)
    db.add(letter)
    await db.commit()

    billable = await client.get(
        f"/instructors/admin/payments/letters/{letter.id}/billable", headers=admin_headers
    )
    assert billable.status_code == 200, billable.text
    lines = billable.json()
    assert len(lines) == 1
    line = lines[0]
    assert line["cohort_id"] == str(cohort.id)
    assert line["session_id"] is None
    assert line["line_id"] == str(cohort.id)
    assert line["session_count"] == 2
    assert line["session_date"] == "10/10/2026 - 11/10/2026"
    assert line["compensation_aed"] == 1000.0

    billed = await client.post(
        f"/instructors/admin/payments/letters/{letter.id}/bill-sessions",
        json={"line_ids": [line["line_id"]]}, headers=admin_headers,
    )
    assert billed.status_code == 201, billed.text
    rows = billed.json()["sessions"]
    assert len(rows) == 1
    assert rows[0]["compensation_aed"] == 1000.0, "the amount arrives filled in, not at 0"

    coverage = (await db.execute(
        select(PaymentSessionCoverage.session_id)
        .join(PaymentSession, PaymentSession.id == PaymentSessionCoverage.payment_session_id)
        .where(PaymentSession.payment_letter_id == letter.id)
    )).scalars().all()
    assert set(coverage) == {s.id for s in sessions}

    # And it must not be billable twice.
    again = await client.get(
        f"/instructors/admin/payments/letters/{letter.id}/billable", headers=admin_headers
    )
    assert again.json() == []

    conflict = await client.post(
        f"/instructors/admin/payments/letters/{letter.id}/bill-sessions",
        json={"line_ids": [str(cohort.id)]}, headers=admin_headers,
    )
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_todo_preview_shows_pending_lines_without_creating_a_letter(db, client):
    """The to-do card's Preview button — see what "Create letter" would pull
    in without having to create anything first."""
    import uuid as _uuid
    from datetime import date as _date, datetime as _datetime, timezone as _timezone
    from decimal import Decimal as _Decimal

    from sqlalchemy import select

    from app.models.sessions.cohort import Cohort
    from app.models.sessions.cohort_assignment import CohortInstructorAssignment
    from app.models.sessions.delivery_role import DeliveryRole
    from app.models.sessions.program import Program
    from app.models.sessions.session import Session, SessionInstructor

    admin = await _user(db, "admin")
    admin_headers = _headers(admin)
    instructor = await _user(db, "instructor")
    program = Program(
        id=_uuid.uuid4(), code=f"PV-{_uuid.uuid4().hex[:8]}", name="Preview Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=_uuid.uuid4(), program_id=program.id, name="Preview Cohort",
        status="running", visibility="public",
    )
    db.add(cohort)
    await db.flush()

    role_id = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator"))
    session = Session(
        id=_uuid.uuid4(), cohort_id=cohort.id, meeting_date=_date(2026, 11, 1),
        completed_at=_datetime.now(_timezone.utc),
    )
    db.add(session)
    await db.flush()
    db.add(SessionInstructor(id=_uuid.uuid4(), session_id=session.id, user_id=instructor.id, role_id=role_id))
    db.add(CohortInstructorAssignment(
        id=_uuid.uuid4(), cohort_id=cohort.id, user_id=instructor.id, role_id=role_id,
        rate_basis="per_session", rate_aed=_Decimal("500.00"), status="active",
    ))
    await db.commit()

    resp = await client.get(f"/instructors/admin/payments/todo/{instructor.id}/preview", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    lines = resp.json()
    assert len(lines) == 1
    assert lines[0]["cohort_id"] == str(cohort.id)
    assert lines[0]["compensation_aed"] == 500.0

    # No letter exists yet — this is a read-only preview.
    from app.models.instructors.payment import PaymentLetter
    letters = (await db.execute(select(PaymentLetter))).scalars().all()
    assert letters == []


@pytest.mark.asyncio
async def test_todo_preview_requires_admin(db, client):
    instructor = await _user(db, "instructor")
    resp = await client.get(
        f"/instructors/admin/payments/todo/{instructor.id}/preview", headers=_headers(instructor),
    )
    assert resp.status_code == 403
