"""Role guards for the inventory phase (I0-2) and the LMS phase (LM0-2).

The point of `storekeeper` is what it CANNOT reach. The operator's brief was
explicit: that person refills kits and receives goods, and must not get at
session assignments or kit create/edit/delete. There is no special mechanism
for that — it falls out of `require_operations` not listing the role — so these
tests exist to make sure nobody "helpfully" adds it later.

The same reasoning applies to `student` (LM0-2): a learner account that could
reach an ops endpoint is the I3-1 failure mode, and it stays invisible until
someone walks the UI as that role. So the negative space is tested here, not
assumed.

Pure guard tests: no DB, no HTTP, no Redis. `RequireRole` is a plain async
callable, so we can hand it a User directly instead of going through FastAPI's
dependency machinery.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.core.dependencies import (
    require_inventory_approval,
    require_lms_content,
    require_lms_student,
    require_operations,
    require_session_delivery,
    require_storekeeper,
)
from app.models.user import User


def _user(*roles: str) -> User:
    return User(
        id=uuid.uuid4(),
        full_name="Guard Test",
        email=f"guard-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=list(roles),
        status="active",
    )


async def _allows(guard, user: User) -> bool:
    try:
        await guard(user)
        return True
    except HTTPException as exc:
        assert exc.status_code == 403
        return False


# ── storekeeper: narrow by design ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_storekeeper_may_restock():
    assert await _allows(require_storekeeper, _user("storekeeper"))


@pytest.mark.asyncio
async def test_operations_may_also_restock():
    """The storekeeper's narrowness is not an exclusive claim on restocking —
    ops does it too."""
    assert await _allows(require_storekeeper, _user("operations"))


@pytest.mark.asyncio
async def test_storekeeper_cannot_reach_operations_endpoints():
    """The whole reason the role exists. Programs, cohorts, registrations,
    contacts, kit create/edit/delete and session assignment all sit behind
    require_operations — a storekeeper must bounce off every one of them."""
    assert not await _allows(require_operations, _user("storekeeper"))


@pytest.mark.asyncio
async def test_storekeeper_cannot_deliver_sessions():
    """Session delivery (start/attendance/mark-done) is not theirs either."""
    assert not await _allows(require_session_delivery, _user("storekeeper"))


@pytest.mark.asyncio
async def test_storekeeper_cannot_approve():
    assert not await _allows(require_inventory_approval, _user("storekeeper"))


# ── coo: approves, but is not an ops account ────────────────────────────────

@pytest.mark.asyncio
async def test_coo_may_approve():
    assert await _allows(require_inventory_approval, _user("coo"))


@pytest.mark.asyncio
async def test_admin_may_approve_in_the_coos_place():
    """`admin` passes every RequireRole check, which is exactly what "the CEO
    can approve when Abu Baker isn't available, without changing the workflow"
    requires — no delegation table, no expiry. Which human actually signed is
    recorded on the approval, not inferred from the role."""
    assert await _allows(require_inventory_approval, _user("admin"))


@pytest.mark.asyncio
async def test_coo_is_not_an_operations_account():
    """Approving is not the same as running operations. A coo-only user has no
    business editing cohorts, so this must stay a 403 — if someone needs both,
    they get both roles."""
    assert not await _allows(require_operations, _user("coo"))


@pytest.mark.asyncio
async def test_operations_alone_cannot_approve():
    """Otherwise the approval step would be self-approval by whoever raised
    the request, which is the only thing it exists to prevent."""
    assert not await _allows(require_inventory_approval, _user("operations"))


# ── combinations ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_user_may_hold_both_ops_and_coo():
    user = _user("operations", "coo")
    assert await _allows(require_operations, user)
    assert await _allows(require_inventory_approval, user)


@pytest.mark.asyncio
async def test_unrelated_role_reaches_nothing():
    intern = _user("intern")
    assert not await _allows(require_storekeeper, intern)
    assert not await _allows(require_operations, intern)
    assert not await _allows(require_inventory_approval, intern)


# ── student: a learner surface, not an account with reach (LM0-2) ────────────

@pytest.mark.asyncio
async def test_student_may_reach_the_learner_surface():
    assert await _allows(require_lms_student, _user("student"))


@pytest.mark.asyncio
async def test_student_is_not_an_operations_account():
    """The one that matters. Ops endpoints own programs, cohorts, contacts and
    registrations — a student reaching any of them is the I3-1 failure mode, and
    `require_operations` not listing the role is the only thing preventing it."""
    assert not await _allows(require_operations, _user("student"))


@pytest.mark.asyncio
async def test_student_cannot_author_course_content():
    """Learners consume content; they don't write it. Authoring is ops +
    facilitators (LM1-5)."""
    assert not await _allows(require_lms_content, _user("student"))


@pytest.mark.asyncio
async def test_student_cannot_deliver_sessions_or_touch_inventory():
    """Nothing in the delivery or inventory domains is a student surface."""
    student = _user("student")
    assert not await _allows(require_session_delivery, student)
    assert not await _allows(require_storekeeper, student)
    assert not await _allows(require_inventory_approval, student)


@pytest.mark.asyncio
async def test_other_roles_are_not_students():
    """`require_lms_student` is not a "logged in" check — an intern or a
    storekeeper wandering onto a player route must bounce. (admin is the
    documented exception: it passes every guard by design, and the LMS is not a
    surface built for it.)"""
    for role in ("intern", "operations", "instructor", "facilitator", "storekeeper", "coo"):
        assert not await _allows(require_lms_student, _user(role)), role


@pytest.mark.asyncio
async def test_admin_passes_the_student_guard_by_design():
    """Documented in §3 of the LMS plan: admin passes every RequireRole check.
    Asserted here so the behaviour is a decision on record rather than a
    surprise to whoever next reads the guard list."""
    assert await _allows(require_lms_student, _user("admin"))


@pytest.mark.asyncio
async def test_ops_and_facilitators_author_content():
    assert await _allows(require_lms_content, _user("operations"))
    assert await _allows(require_lms_content, _user("facilitator"))


@pytest.mark.asyncio
async def test_plain_instructors_do_not_author_content():
    """Same split as require_materials_manager: facilitators write the material,
    so a course can't be edited by whoever happens to be teaching it that day.
    Instructors still get the read-only progress view (LM1-10)."""
    assert not await _allows(require_lms_content, _user("instructor"))


@pytest.mark.asyncio
async def test_a_facilitator_may_also_be_a_student():
    """Staff taking a course is ordinary — the roles compose, no special case."""
    user = _user("facilitator", "student")
    assert await _allows(require_lms_student, user)
    assert await _allows(require_lms_content, user)
    assert not await _allows(require_operations, user)
