"""services/internship/ref_number.py — auto-incrementing "N/YYYY" internship
reference numbers. Redis-free, HTTP-free.
"""

import uuid

from app.models.internship import InternProfile
from app.models.user import User
from app.services.internship.ref_number import next_ref_number


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ref Number User", email=f"refnum-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["intern"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def test_starts_at_one_with_no_history(db):
    assert await next_ref_number(db, year=2030) == "1/2030"
    assert await next_ref_number(db, year=2030) == "2/2030"


async def test_seeds_from_existing_intern_profiles(db):
    for n in ("13/2031", "27/2031", "85/2031", "9/2032"):
        user = await _user(db)
        db.add(InternProfile(user_id=user.id, ref_number=n))
    await db.flush()

    # continues after the highest existing number for that year, ignoring
    # other years' numbers
    assert await next_ref_number(db, year=2031) == "86/2031"
    assert await next_ref_number(db, year=2032) == "10/2032"


async def test_ignores_malformed_ref_numbers(db):
    user = await _user(db)
    db.add(InternProfile(user_id=user.id, ref_number="not-a-real-ref"))
    await db.flush()
    assert await next_ref_number(db, year=2033) == "1/2033"


async def test_override_then_continues_from_override_plus_one(db):
    assert await next_ref_number(db, year=2034) == "1/2034"
    assert await next_ref_number(db, year=2034, override=500) == "500/2034"
    assert await next_ref_number(db, year=2034) == "501/2034"


async def test_override_lower_than_current_does_not_go_backwards(db):
    for _ in range(3):
        await next_ref_number(db, year=2035)
    # counter is at 3; an override of 1 must not roll the counter back
    assert await next_ref_number(db, year=2035, override=1) == "1/2035"
    assert await next_ref_number(db, year=2035) == "4/2035"


async def test_years_are_independent(db):
    assert await next_ref_number(db, year=2036) == "1/2036"
    assert await next_ref_number(db, year=2037) == "1/2037"
    assert await next_ref_number(db, year=2036) == "2/2036"
