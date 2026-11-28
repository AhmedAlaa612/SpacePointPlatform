"""Tests for Completed Cohort payment review, settlement, ignore/restore,
draft PDF invalidation on append, paid-only analytics, and admin-only
instructor payment history.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.enums import PaymentLetterStatus
from app.models.instructors.payment import (
    CohortPaymentDecision,
    InstructorBankDetails,
    PaymentAddon,
    PaymentBatch,
    PaymentLetter,
    PaymentSession,
)
from app.models.sessions.checklist import InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_assignment import CohortInstructorAssignment
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User


async def _user(db, *roles: str, name: str | None = None) -> User:
    u = User(
        id=uuid.uuid4(),
        full_name=name or f"U{uuid.uuid4().hex[:5]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"),
        roles=list(roles),
        status="active",
    )
    db.add(u)
    await db.flush()
    return u


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _role_id(db, name: str = "Facilitator") -> uuid.UUID:
    rid = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))
    assert rid is not None
    return rid


async def _completed_cohort(db, *, name: str = "FSP On Site AAS", duration_hours: Decimal | None = Decimal("3.00")):
    program = Program(
        id=uuid.uuid4(),
        code=f"P-{uuid.uuid4().hex[:8]}",
        name="Foundations of Space",
        program_type="workshop",
        pricing_model="free",
        active=True,
        completion_rule_type="percentage",
        completion_rule_value=70,
        duration_hours=duration_hours,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name=name,
        status="completed",
        visibility="private",
        starts_on=date(2026, 11, 5),
        ends_on=date(2026, 11, 5),
        location="Al Ain American School",
        duration_hours=duration_hours,
    )
    db.add(cohort)
    await db.flush()
    session = Session(
        id=uuid.uuid4(),
        cohort_id=cohort.id,
        meeting_date=date(2026, 11, 5),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    return program, cohort, session


@pytest.mark.asyncio
async def test_completed_cohort_with_draft_days_appears_as_pending(client, db):
    """Reproduces the FSP On Site AAS gap: completed cohort with session_instructors
    and unapproved draft InstructorSessionDay rows must surface in Pending Review."""
    admin = await _user(db, "admin")
    lead = await _user(db, "instructor", name="Rayan A")
    fac = await _user(db, "instructor", name="Noor A")
    _, cohort, session = await _completed_cohort(db)

    lead_role = await _role_id(db, "Lead Facilitator")
    fac_role = await _role_id(db, "Facilitator")
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=lead.id, role_id=lead_role))
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=fac.id, role_id=fac_role))
    db.add(InstructorSessionDay(
        id=uuid.uuid4(), session_id=session.id, user_id=lead.id, att_status="present", status="draft"
    ))
    db.add(InstructorSessionDay(
        id=uuid.uuid4(), session_id=session.id, user_id=fac.id, att_status="present", status="draft"
    ))
    await db.flush()

    r = await client.get("/instructors/admin/payments/cohorts", headers=_headers(admin))
    assert r.status_code == 200
    found = [c for c in r.json() if c["cohort_id"] == str(cohort.id)]
    assert len(found) == 1
    item = found[0]
    assert item["status"] == "pending"
    assert len(item["instructors"]) == 2
    by_uid = {i["instructor_user_id"]: i for i in item["instructors"]}
    assert by_uid[str(lead.id)]["outcome"] == "pending"
    assert by_uid[str(lead.id)]["sessions_count"] == 1
    assert by_uid[str(lead.id)]["hours"] == 3.0
    assert by_uid[str(lead.id)]["attendance_status"] == "present_unapproved"


@pytest.mark.asyncio
async def test_settle_creates_and_appends_to_draft_and_invalidates_existing_pdf(client, db):
    """Appending another cohort to an instructor's active draft that already has
    a PDF must append to the SAME draft and clear pdf_url/pdf_path."""
    admin = await _user(db, "admin")
    inst_with_draft = await _user(db, "instructor", name="Existing Draft Inst")
    inst_fresh = await _user(db, "instructor", name="Fresh Inst")
    inst_ignored = await _user(db, "instructor", name="Skipped Inst")

    batch = PaymentBatch(id=uuid.uuid4(), name="Nov 2026")
    db.add(batch)
    await db.flush()

    existing_draft = PaymentLetter(
        id=uuid.uuid4(),
        instructor_user_id=inst_with_draft.id,
        status=PaymentLetterStatus.draft,
        is_published=False,
        pdf_url="/files/payment-letters/stale.pdf",
        pdf_path="stale/letter.pdf",
        reference="SP-OLD-1",
    )
    db.add(existing_draft)
    await db.flush()
    db.add(PaymentSession(
        id=uuid.uuid4(),
        payment_letter_id=existing_draft.id,
        workshop_description="Earlier Workshop",
        role="Facilitator",
        compensation_aed=400,
        sort_order=1,
    ))

    _, cohort, session = await _completed_cohort(db, name="SatForge Nov")
    fac_role = await _role_id(db, "Facilitator")
    for u in (inst_with_draft, inst_fresh, inst_ignored):
        db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=u.id, role_id=fac_role))
        db.add(CohortInstructorAssignment(
            id=uuid.uuid4(), cohort_id=cohort.id, user_id=u.id, role_id=fac_role,
            rate_basis="per_session", rate_aed=Decimal("500.00"), status="active",
        ))
    await db.flush()

    r = await client.post(
        f"/instructors/admin/payments/cohorts/{cohort.id}/settle",
        json={
            "batch_id": str(batch.id),
            "items": [
                {
                    "instructor_user_id": str(inst_with_draft.id),
                    "action": "add",
                    "role": "Lead Facilitator",
                    "sessions_count": 1,
                    "hours": 4.0,
                    "rate_aed": 500.0,
                    "compensation_aed": 500.0,
                },
                {
                    "instructor_user_id": str(inst_fresh.id),
                    "action": "add",
                    "role": "Facilitator",
                    "sessions_count": 1,
                    "hours": 4.0,
                    "rate_aed": 450.0,
                    "compensation_aed": 450.0,
                },
                {
                    "instructor_user_id": str(inst_ignored.id),
                    "action": "ignore",
                    "role": "Facilitator",
                    "sessions_count": 1,
                    "hours": 4.0,
                    "rate_aed": 0.0,
                    "compensation_aed": 0.0,
                },
            ],
        },
        headers=_headers(admin),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["appended_drafts"] == 1
    assert body["created_drafts"] == 1
    assert body["ignored_count"] == 1
    assert body["cohort"]["status"] == "settled"
    assert body["cohort"]["settled_outcome"] == "partial"

    # Existing draft kept same ID, stayed draft, and had its stale PDF cleared
    r_letters = await client.get("/instructors/admin/payments/letters", headers=_headers(admin))
    assert r_letters.status_code == 200
    letters = {l["instructor_user_id"]: l for l in r_letters.json()}

    draft_out = letters[str(inst_with_draft.id)]
    assert draft_out["id"] == str(existing_draft.id)
    assert draft_out["status"] == "draft"
    assert draft_out["is_published"] is False
    assert draft_out["pdf_url"] is None
    assert len(draft_out["sessions"]) == 2
    assert draft_out["sessions"][1]["workshop_description"] == "SatForge Nov"
    assert draft_out["sessions"][1]["compensation_aed"] == 500.0

    fresh_out = letters[str(inst_fresh.id)]
    assert fresh_out["status"] == "draft"
    assert fresh_out["batch_id"] == str(batch.id)
    assert len(fresh_out["sessions"]) == 1
    assert str(inst_ignored.id) not in letters


@pytest.mark.asyncio
async def test_ignore_restore_and_drop_draft_line_keep_ignored_entries_excluded(client, db):
    """Ignoring a cohort, restoring an ignored instructor, dropping a draft line,
    or ignoring a whole draft must preserve permanent exclusion until explicitly restored."""
    admin = await _user(db, "admin")
    inst1 = await _user(db, "instructor", name="Inst One")
    inst2 = await _user(db, "instructor", name="Inst Two")
    _, cohort, session = await _completed_cohort(db, name="Kuwait Robotics")
    fac_role = await _role_id(db, "Facilitator")
    for u in (inst1, inst2):
        db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=u.id, role_id=fac_role))
    await db.flush()

    # 1. Ignore whole cohort
    r_ign = await client.post(
        f"/instructors/admin/payments/cohorts/{cohort.id}/ignore",
        json={},
        headers=_headers(admin),
    )
    assert r_ign.status_code == 200
    assert r_ign.json()["status"] == "settled"
    assert r_ign.json()["settled_outcome"] == "ignored"

    # Ignored cohort does not leak into legacy /todo
    r_todo = await client.get("/instructors/admin/payments/todo", headers=_headers(admin))
    assert not any(t["instructor_user_id"] in (str(inst1.id), str(inst2.id)) for t in r_todo.json())

    # 2. Restore only inst1 back to pending
    r_rest = await client.post(
        f"/instructors/admin/payments/cohorts/{cohort.id}/restore",
        json={"instructor_user_id": str(inst1.id)},
        headers=_headers(admin),
    )
    assert r_rest.status_code == 200
    assert r_rest.json()["status"] == "pending"
    by_uid = {i["instructor_user_id"]: i for i in r_rest.json()["instructors"]}
    assert by_uid[str(inst1.id)]["outcome"] == "pending"
    assert by_uid[str(inst2.id)]["outcome"] == "ignored"

    # 3. Add inst1 to a draft letter, then drop that line from the draft -> must stay ignored
    r_settle = await client.post(
        f"/instructors/admin/payments/cohorts/{cohort.id}/settle",
        json={
            "items": [{
                "instructor_user_id": str(inst1.id),
                "action": "add",
                "role": "Facilitator",
                "sessions_count": 1,
                "hours": 3.0,
                "rate_aed": 400.0,
                "compensation_aed": 400.0,
            }]
        },
        headers=_headers(admin),
    )
    assert r_settle.status_code == 200
    letter_id = r_settle.json()["touched_letter_ids"][0]
    line_id = r_settle.json()["cohort"]["instructors"][0]["payment_session_id"]
    if line_id is None:
        inst1_row = [i for i in r_settle.json()["cohort"]["instructors"] if i["instructor_user_id"] == str(inst1.id)][0]
        line_id = inst1_row["payment_session_id"]

    r_drop = await client.delete(
        f"/instructors/admin/payments/sessions/{line_id}",
        headers=_headers(admin),
    )
    assert r_drop.status_code == 200

    # Cohort must be settled + ignored, NOT back in pending
    r_cohorts = await client.get("/instructors/admin/payments/cohorts", headers=_headers(admin))
    c_item = [c for c in r_cohorts.json() if c["cohort_id"] == str(cohort.id)][0]
    assert c_item["status"] == "settled"
    assert c_item["settled_outcome"] == "ignored"

    # 4. Restore inst1 again, add to draft, then ignore entire draft via POST /letters/{id}/ignore
    await client.post(
        f"/instructors/admin/payments/cohorts/{cohort.id}/restore",
        json={"instructor_user_id": str(inst1.id)},
        headers=_headers(admin),
    )
    r_settle2 = await client.post(
        f"/instructors/admin/payments/cohorts/{cohort.id}/settle",
        json={
            "items": [{
                "instructor_user_id": str(inst1.id),
                "action": "add",
                "role": "Facilitator",
                "sessions_count": 1,
                "hours": 3.0,
                "rate_aed": 400.0,
                "compensation_aed": 400.0,
            }]
        },
        headers=_headers(admin),
    )
    letter_id2 = r_settle2.json()["touched_letter_ids"][0]
    r_ign_draft = await client.post(
        f"/instructors/admin/payments/letters/{letter_id2}/ignore",
        headers=_headers(admin),
    )
    assert r_ign_draft.status_code == 200

    r_cohorts2 = await client.get("/instructors/admin/payments/cohorts", headers=_headers(admin))
    c_item2 = [c for c in r_cohorts2.json() if c["cohort_id"] == str(cohort.id)][0]
    assert c_item2["status"] == "settled"
    assert c_item2["settled_outcome"] == "ignored"


@pytest.mark.asyncio
async def test_paid_only_analytics_and_admin_only_instructor_history(client, db):
    """Analytics only count status=='paid' letters; mark-paid stamps paid_at and updates
    totals; history endpoint is strictly admin-only."""
    admin = await _user(db, "admin")
    ops = await _user(db, "operations")
    inst = await _user(db, "instructor", name="History Inst")
    db.add(InstructorBankDetails(
        id=uuid.uuid4(),
        user_id=inst.id,
        account_holder_name="History Inst",
        bank_name="ENBD",
        iban="AE070331234567890123456",
    ))

    # Create 1 draft, 1 signed, and 1 paid letter
    draft = PaymentLetter(
        id=uuid.uuid4(), instructor_user_id=inst.id, status=PaymentLetterStatus.draft,
        letter_date="28/11/2026", reference="REF-DRAFT",
    )
    signed = PaymentLetter(
        id=uuid.uuid4(), instructor_user_id=inst.id, status=PaymentLetterStatus.signed,
        is_published=True, letter_date="15/11/2026", reference="REF-SIGNED",
    )
    paid = PaymentLetter(
        id=uuid.uuid4(), instructor_user_id=inst.id, status=PaymentLetterStatus.paid,
        is_published=True, letter_date="20/10/2026", reference="REF-PAID",
        paid_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
    )
    db.add_all([draft, signed, paid])
    await db.flush()

    db.add_all([
        PaymentSession(
            id=uuid.uuid4(), payment_letter_id=draft.id, workshop_description="Draft WS",
            role="Facilitator", duration_hours=2.0, session_count=1, compensation_aed=900, sort_order=1,
        ),
        PaymentSession(
            id=uuid.uuid4(), payment_letter_id=signed.id, workshop_description="Signed WS",
            role="Facilitator", duration_hours=4.0, session_count=2, compensation_aed=1000, sort_order=1,
        ),
        PaymentSession(
            id=uuid.uuid4(), payment_letter_id=paid.id, workshop_description="Paid WS",
            role="Lead Facilitator", duration_hours=6.0, session_count=3, compensation_aed=1500, sort_order=1,
        ),
        PaymentAddon(
            id=uuid.uuid4(), payment_letter_id=paid.id, description="Transport",
            amount_aed=100, sort_order=1,
        ),
    ])
    await db.flush()

    # Baseline analytics: only PAID letter counts (1500 + 100 = 1600)
    r_an = await client.get("/instructors/admin/payments/analytics", headers=_headers(admin))
    assert r_an.status_code == 200
    an = r_an.json()
    assert an["total_paid_aed"] >= 1600.0

    # Non-admin blocked from history
    r_ops = await client.get(
        f"/instructors/admin/payments/instructors/{inst.id}/history",
        headers=_headers(ops),
    )
    assert r_ops.status_code == 403
    r_inst = await client.get(
        f"/instructors/admin/payments/instructors/{inst.id}/history",
        headers=_headers(inst),
    )
    assert r_inst.status_code == 403

    # Admin reads instructor history before marking signed as paid
    r_hist = await client.get(
        f"/instructors/admin/payments/instructors/{inst.id}/history",
        headers=_headers(admin),
    )
    assert r_hist.status_code == 200
    h1 = r_hist.json()
    assert h1["total_paid_aed"] == 1600.0
    assert h1["paid_letters_count"] == 1
    assert h1["paid_sessions_count"] == 3
    assert h1["paid_hours_count"] == 6.0
    assert h1["draft_letters_count"] == 1
    assert h1["signed_letters_count"] == 1
    assert h1["pending_payout_aed"] == 1900.0
    assert h1["bank_details_complete"] is True

    # Mark signed letter as paid -> paid_at stamped and paid analytics increase by 1000
    r_mp = await client.post(
        f"/instructors/admin/payments/letters/{signed.id}/mark-paid",
        headers=_headers(admin),
    )
    assert r_mp.status_code == 200
    assert r_mp.json()["status"] == "paid"
    assert r_mp.json()["paid_at"] is not None

    r_hist2 = await client.get(
        f"/instructors/admin/payments/instructors/{inst.id}/history",
        headers=_headers(admin),
    )
    h2 = r_hist2.json()
    assert h2["total_paid_aed"] == 2600.0
    assert h2["paid_letters_count"] == 2
    assert h2["paid_sessions_count"] == 5
    assert h2["paid_hours_count"] == 10.0
    assert h2["signed_letters_count"] == 0
