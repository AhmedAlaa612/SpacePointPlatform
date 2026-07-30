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
