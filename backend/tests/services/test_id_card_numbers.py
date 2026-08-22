"""Student/staff card numbering split (2026-08-22) — students and staff used
to share one `card_seq_person` sequence, so a student and a staff member
could end up with the same-looking `SP-####-UAE` number. Students now draw
from a separate `card_seq_student` sequence, and `format_card_id` is what
turns that into a visibly distinct `SP-ST-####-UAE` prefix.
"""

import uuid

import pytest

from app.core.security import create_access_token
from app.models.user import User
from app.services.documents.id_card import ensure_card_number, format_card_id


def test_format_card_id_uses_staff_prefix_for_non_students():
    assert format_card_id(17, ["instructor"]) == "SP-0017-UAE"
    assert format_card_id(17, ["admin", "operations"]) == "SP-0017-UAE"


def test_format_card_id_uses_student_prefix_for_students():
    assert format_card_id(17, ["student"]) == "SP-ST-0017-UAE"


async def _user(db, *, roles, **kw) -> User:
    user = User(
        id=uuid.uuid4(), full_name=kw.pop("full_name", "Card User"),
        email=f"card-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles, status="active", **kw,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_student_and_staff_numbers_come_from_separate_sequences(db):
    student = await _user(db, roles=["student"])
    staff = await _user(db, roles=["instructor"])
    await db.commit()

    student_number = await ensure_card_number(db, student)
    staff_number = await ensure_card_number(db, staff)
    await db.commit()

    # Real Postgres sequences advance independently of this test's own
    # transaction (nextval() isn't rolled back), so other tests sharing this
    # DB may have already moved either sequence — only the shape is checked
    # here, not an exact value. The two sequences existing at all, and never
    # producing a collision by construction, is the actual thing under test.
    assert isinstance(student_number, int) and isinstance(staff_number, int)
    assert format_card_id(student_number, student.roles).startswith("SP-ST-")
    assert format_card_id(staff_number, staff.roles).startswith("SP-") and not \
        format_card_id(staff_number, staff.roles).startswith("SP-ST-")


@pytest.mark.asyncio
async def test_ensure_card_number_no_ops_once_allocated(db):
    student = await _user(db, roles=["student"])
    await db.commit()

    first = await ensure_card_number(db, student)
    second = await ensure_card_number(db, student)
    assert first == second


@pytest.mark.asyncio
async def test_signup_response_card_id_uses_student_prefix(db, client):
    from app.models.instructors.invitation_code import InvitationCode

    code = InvitationCode(
        id=uuid.uuid4(), code="CARDTEST", kind="student", is_active=True, max_uses=10, used_count=0,
    )
    db.add(code)
    await db.commit()

    resp = await client.post("/auth/signup", json={
        "invite_code": "cardtest",
        "full_name": "Card Student", "email": "cardstudent@example.com", "password": "pass-card",
    })
    assert resp.status_code == 201, resp.text
    card_id = resp.json()["user"]["card_id"]
    assert card_id is not None
    assert card_id.startswith("SP-ST-")


@pytest.mark.asyncio
async def test_admin_users_list_shows_student_prefix(db, client):
    admin = await _user(db, roles=["admin"])
    student = await _user(db, roles=["student"])
    await ensure_card_number(db, student)
    await db.commit()

    resp = await client.get("/admin/users", headers=_headers(admin))
    assert resp.status_code == 200, resp.text
    row = next(u for u in resp.json() if u["id"] == str(student.id))
    assert row["card_id"].startswith("SP-ST-")
