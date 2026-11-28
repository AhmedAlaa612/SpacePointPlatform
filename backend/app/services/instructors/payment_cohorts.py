"""Cohort-to-letter payment intake, settlement, ignore/restore, and paid-only analytics."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PaymentLetterStatus
from app.models.instructors.payment import (
    CohortPaymentDecision,
    InstructorBankDetails,
    PaymentAddon,
    PaymentBatch,
    PaymentLetter,
    PaymentSession,
)
from app.models.inventory.location import Location
from app.models.sessions.checklist import InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_assignment import CohortInstructorAssignment
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.payment_coverage import PaymentSessionCoverage
from app.models.sessions.program import Program
from app.models.sessions.program_variation import ProgramVariation
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.schemas.instructors.payment import (
    CohortInstructorPaymentOut,
    CompletedCohortPaymentOut,
    InstructorPaymentHistoryOut,
    MonthlyPaidPointOut,
    PaymentLetterOut,
    PaymentsAnalyticsOut,
    SettleCohortPaymentIn,
    SettleCohortPaymentOut,
)
from app.services import storage
from app.services.sessions.journey import _format_range, find_or_create_draft_letter

_MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _resolve_duration_sync(
    session: Session,
    cohort: Cohort,
    variation: ProgramVariation | None,
    program: Program,
) -> float:
    for val in (
        session.duration_hours,
        cohort.duration_hours,
        variation.duration_hours if variation else None,
        program.duration_hours,
    ):
        if val is not None:
            return float(val)
    return 0.0


def _compute_settled_outcome(outcomes: list[str]) -> str:
    has_added = any(o == "added" for o in outcomes)
    has_ignored = any(o == "ignored" for o in outcomes)
    if has_added and has_ignored:
        return "partial"
    if has_added:
        return "added"
    return "ignored"


async def _cohort_location_name(
    db: AsyncSession,
    cohort: Cohort,
    sessions: list[Session],
    locations_by_id: dict[uuid.UUID, Location],
) -> str | None:
    loc_id = cohort.location_id
    if loc_id is None:
        for s in sessions:
            if s.location_id is not None:
                loc_id = s.location_id
                break
    if loc_id is not None:
        loc = locations_by_id.get(loc_id)
        if loc is None:
            loc = await db.get(Location, loc_id)
            if loc is not None:
                locations_by_id[loc_id] = loc
        if loc is not None and loc.name:
            return loc.name
    return cohort.location


def _cohort_date_range(cohort: Cohort, sessions: list[Session]) -> str:
    span = [d for d in (cohort.starts_on, cohort.ends_on) if d is not None]
    if len(span) >= 2:
        return _format_range(span)
    dates = [s.meeting_date for s in sessions if s.meeting_date is not None]
    if dates:
        return _format_range(dates)
    if span:
        return _format_range(span)
    return ""


def _attendance_summary(
    session_ids: list[uuid.UUID],
    days_by_key: dict[tuple[uuid.UUID, uuid.UUID], InstructorSessionDay],
    user_id: uuid.UUID,
) -> tuple[str, str, int]:
    """Return (attendance_status, attendance_tag, default_sessions_count)."""
    assigned_cnt = len(session_ids)
    if assigned_cnt == 0:
        return "no_checkin", "0 sessions", 0

    approved_cnt = 0
    present_cnt = 0
    absent_cnt = 0
    for sid in session_ids:
        day = days_by_key.get((sid, user_id))
        if day is None:
            continue
        if day.att_status == "absent":
            absent_cnt += 1
        elif day.att_status == "present":
            present_cnt += 1
            if day.status == "approved":
                approved_cnt += 1

    if approved_cnt > 0:
        tag = f"{approved_cnt} / {assigned_cnt} approved"
        return "approved", tag, approved_cnt
    if present_cnt > 0:
        tag = f"{present_cnt} / {assigned_cnt} present (unapproved)"
        return "present_unapproved", tag, present_cnt
    if absent_cnt >= assigned_cnt:
        return "absent", f"Absent ({absent_cnt} / {assigned_cnt})", 0
    return "no_checkin", f"No check-in ({assigned_cnt} session{'s' if assigned_cnt != 1 else ''})", max(0, assigned_cnt - absent_cnt)


async def list_completed_cohort_payments(
    db: AsyncSession,
    cohort_id: uuid.UUID | None = None,
) -> list[CompletedCohortPaymentOut]:
    """Return every completed cohort with its instructors' review/settlement state."""
    stmt = (
        select(Cohort, Program)
        .join(Program, Program.id == Cohort.program_id)
        .where(Cohort.status == "completed")
        .order_by(Cohort.starts_on.desc().nullslast(), Cohort.created_at.desc())
    )
    if cohort_id is not None:
        stmt = stmt.where(Cohort.id == cohort_id)

    cohort_rows = (await db.execute(stmt)).all()
    if not cohort_rows:
        return []

    cohort_ids = [c.id for c, _ in cohort_rows]

    # Batch-fetch variations, locations, sessions, assignments, openings, decisions, roles, drafts
    var_ids = {c.variation_id for c, _ in cohort_rows if c.variation_id is not None}
    variations: dict[uuid.UUID, ProgramVariation] = {}
    if var_ids:
        for v in (await db.execute(select(ProgramVariation).where(ProgramVariation.id.in_(var_ids)))).scalars().all():
            variations[v.id] = v

    sessions_all = (await db.execute(
        select(Session).where(Session.cohort_id.in_(cohort_ids)).order_by(Session.meeting_date.asc())
    )).scalars().all()
    sessions_by_cohort: dict[uuid.UUID, list[Session]] = {}
    session_by_id: dict[uuid.UUID, Session] = {}
    for s in sessions_all:
        sessions_by_cohort.setdefault(s.cohort_id, []).append(s)
        session_by_id[s.id] = s

    all_session_ids = list(session_by_id.keys())

    loc_ids = {c.location_id for c, _ in cohort_rows if c.location_id is not None}
    loc_ids |= {s.location_id for s in sessions_all if s.location_id is not None}
    locations_by_id: dict[uuid.UUID, Location] = {}
    if loc_ids:
        for loc in (await db.execute(select(Location).where(Location.id.in_(loc_ids)))).scalars().all():
            locations_by_id[loc.id] = loc

    roles_by_id: dict[uuid.UUID, DeliveryRole] = {
        r.id: r for r in (await db.execute(select(DeliveryRole))).scalars().all()
    }

    openings_by_key: dict[tuple[uuid.UUID, uuid.UUID], CohortOpening] = {}
    for op in (await db.execute(
        select(CohortOpening).where(CohortOpening.cohort_id.in_(cohort_ids))
    )).scalars().all():
        openings_by_key[(op.cohort_id, op.role_id)] = op

    assignments_by_key: dict[tuple[uuid.UUID, uuid.UUID], CohortInstructorAssignment] = {}
    assignments_by_cohort: dict[uuid.UUID, list[CohortInstructorAssignment]] = {}
    for a in (await db.execute(
        select(CohortInstructorAssignment).where(
            CohortInstructorAssignment.cohort_id.in_(cohort_ids),
            CohortInstructorAssignment.status == "active",
        )
    )).scalars().all():
        assignments_by_key[(a.cohort_id, a.user_id)] = a
        assignments_by_cohort.setdefault(a.cohort_id, []).append(a)

    si_rows: list[SessionInstructor] = []
    if all_session_ids:
        si_rows = (await db.execute(
            select(SessionInstructor).where(SessionInstructor.session_id.in_(all_session_ids))
        )).scalars().all()

    si_sessions_by_cohort_user: dict[tuple[uuid.UUID, uuid.UUID], list[Session]] = {}
    si_role_by_cohort_user: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}
    for si in si_rows:
        sess = session_by_id.get(si.session_id)
        if sess is None:
            continue
        key = (sess.cohort_id, si.user_id)
        si_sessions_by_cohort_user.setdefault(key, []).append(sess)
        if si.role_id is not None and key not in si_role_by_cohort_user:
            si_role_by_cohort_user[key] = si.role_id

    days_by_key: dict[tuple[uuid.UUID, uuid.UUID], InstructorSessionDay] = {}
    if all_session_ids:
        for d in (await db.execute(
            select(InstructorSessionDay).where(InstructorSessionDay.session_id.in_(all_session_ids))
        )).scalars().all():
            days_by_key[(d.session_id, d.user_id)] = d

    decisions_by_key: dict[tuple[uuid.UUID, uuid.UUID], CohortPaymentDecision] = {}
    decisions_by_cohort: dict[uuid.UUID, list[CohortPaymentDecision]] = {}
    for dec in (await db.execute(
        select(CohortPaymentDecision).where(CohortPaymentDecision.cohort_id.in_(cohort_ids))
    )).scalars().all():
        decisions_by_key[(dec.cohort_id, dec.instructor_user_id)] = dec
        decisions_by_cohort.setdefault(dec.cohort_id, []).append(dec)

    # Pre-existing PaymentSessions linked to these cohorts or their sessions (backward compat)
    ps_by_cohort_user: dict[tuple[uuid.UUID, uuid.UUID], tuple[PaymentSession, PaymentLetter]] = {}
    ps_rows = (await db.execute(
        select(PaymentSession, PaymentLetter)
        .join(PaymentLetter, PaymentLetter.id == PaymentSession.payment_letter_id)
        .where(PaymentSession.cohort_id.in_(cohort_ids))
    )).all()
    for ps, pl in ps_rows:
        if ps.cohort_id is not None:
            ps_by_cohort_user.setdefault((ps.cohort_id, pl.instructor_user_id), (ps, pl))

    if all_session_ids:
        direct_ps = (await db.execute(
            select(PaymentSession, PaymentLetter)
            .join(PaymentLetter, PaymentLetter.id == PaymentSession.payment_letter_id)
            .where(PaymentSession.session_id.in_(all_session_ids))
        )).all()
        for ps, pl in direct_ps:
            sess = session_by_id.get(ps.session_id) if ps.session_id else None
            if sess is not None:
                ps_by_cohort_user.setdefault((sess.cohort_id, pl.instructor_user_id), (ps, pl))

        cov_ps = (await db.execute(
            select(PaymentSessionCoverage.session_id, PaymentSession, PaymentLetter)
            .join(PaymentSession, PaymentSession.id == PaymentSessionCoverage.payment_session_id)
            .join(PaymentLetter, PaymentLetter.id == PaymentSession.payment_letter_id)
            .where(PaymentSessionCoverage.session_id.in_(all_session_ids))
        )).all()
        for cov_sid, ps, pl in cov_ps:
            sess = session_by_id.get(cov_sid)
            if sess is not None:
                ps_by_cohort_user.setdefault((sess.cohort_id, pl.instructor_user_id), (ps, pl))

    # Letters referenced by decisions + active drafts per instructor
    referenced_letter_ids = {
        d.payment_letter_id for d in decisions_by_key.values() if d.payment_letter_id is not None
    }
    letters_by_id: dict[uuid.UUID, PaymentLetter] = {}
    if referenced_letter_ids:
        for l in (await db.execute(
            select(PaymentLetter).where(PaymentLetter.id.in_(referenced_letter_ids))
        )).scalars().all():
            letters_by_id[l.id] = l

    referenced_ps_ids = {
        d.payment_session_id for d in decisions_by_key.values() if d.payment_session_id is not None
    }
    ps_by_id: dict[uuid.UUID, PaymentSession] = {}
    if referenced_ps_ids:
        for ps in (await db.execute(
            select(PaymentSession).where(PaymentSession.id.in_(referenced_ps_ids))
        )).scalars().all():
            ps_by_id[ps.id] = ps

    active_draft_by_user: dict[uuid.UUID, PaymentLetter] = {}
    for draft in (await db.execute(
        select(PaymentLetter)
        .where(PaymentLetter.status == PaymentLetterStatus.draft)
        .order_by(PaymentLetter.created_at.desc())
    )).scalars().all():
        active_draft_by_user.setdefault(draft.instructor_user_id, draft)

    # Collect all candidate user IDs
    candidate_user_ids: set[uuid.UUID] = set()
    for (_cid, uid) in assignments_by_key:
        candidate_user_ids.add(uid)
    for (_cid, uid) in si_sessions_by_cohort_user:
        candidate_user_ids.add(uid)
    for (_cid, uid) in decisions_by_key:
        candidate_user_ids.add(uid)
    for (_cid, uid) in ps_by_cohort_user:
        candidate_user_ids.add(uid)

    users_by_id: dict[uuid.UUID, User] = {}
    if candidate_user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(candidate_user_ids)))).scalars().all():
            users_by_id[u.id] = u

    out: list[CompletedCohortPaymentOut] = []
    for cohort, program in cohort_rows:
        c_sessions = sessions_by_cohort.get(cohort.id, [])
        variation = variations.get(cohort.variation_id) if cohort.variation_id else None

        user_ids_in_cohort: list[uuid.UUID] = []
        seen_uids: set[uuid.UUID] = set()
        for a in assignments_by_cohort.get(cohort.id, []):
            if a.user_id not in seen_uids:
                seen_uids.add(a.user_id)
                user_ids_in_cohort.append(a.user_id)
        for (cid_key, uid) in si_sessions_by_cohort_user:
            if cid_key == cohort.id and uid not in seen_uids:
                seen_uids.add(uid)
                user_ids_in_cohort.append(uid)
        for d in decisions_by_cohort.get(cohort.id, []):
            if d.instructor_user_id not in seen_uids:
                seen_uids.add(d.instructor_user_id)
                user_ids_in_cohort.append(d.instructor_user_id)
        for (cid_key, uid) in ps_by_cohort_user:
            if cid_key == cohort.id and uid not in seen_uids:
                seen_uids.add(uid)
                user_ids_in_cohort.append(uid)

        if not user_ids_in_cohort:
            continue

        instructor_items: list[CohortInstructorPaymentOut] = []
        for uid in user_ids_in_cohort:
            user = users_by_id.get(uid)
            if user is None:
                continue

            key = (cohort.id, uid)
            assignment = assignments_by_key.get(key)
            user_sessions = si_sessions_by_cohort_user.get(key, [])
            if not user_sessions and assignment is not None:
                # Assignment without session_instructors rows — fall back to cohort sessions
                user_sessions = c_sessions

            role_id = (
                assignment.role_id
                if assignment is not None
                else si_role_by_cohort_user.get(key)
            )
            role_obj = roles_by_id.get(role_id) if role_id else None
            role_name = role_obj.name if role_obj else "Facilitator"

            session_ids_for_user = [s.id for s in user_sessions]
            att_status, att_tag, default_sess_cnt = _attendance_summary(
                session_ids_for_user, days_by_key, uid
            )

            # Default hours across the counted sessions (or cohort/program fallback)
            default_hours = 0.0
            if user_sessions and default_sess_cnt > 0:
                per_sess_hours = [
                    _resolve_duration_sync(s, cohort, variation, program)
                    for s in user_sessions
                ]
                if default_sess_cnt >= len(per_sess_hours):
                    default_hours = sum(per_sess_hours)
                else:
                    avg_h = sum(per_sess_hours) / len(per_sess_hours)
                    default_hours = round(avg_h * default_sess_cnt, 2)
            elif cohort.duration_hours is not None:
                default_hours = float(cohort.duration_hours) * default_sess_cnt
            elif program.duration_hours is not None:
                default_hours = float(program.duration_hours) * default_sess_cnt

            rate_basis = assignment.rate_basis if assignment is not None else "per_session"
            resolved_rate: float | None = None
            default_total = 0.0
            if assignment is not None and rate_basis == "flat":
                default_total = float(assignment.flat_amount_aed or 0)
            else:
                if assignment is not None and assignment.rate_aed is not None:
                    resolved_rate = float(assignment.rate_aed)
                elif role_id is not None and (cohort.id, role_id) in openings_by_key and openings_by_key[(cohort.id, role_id)].amount_aed is not None:
                    resolved_rate = float(openings_by_key[(cohort.id, role_id)].amount_aed)
                elif role_obj is not None and role_obj.default_rate_aed is not None:
                    resolved_rate = float(role_obj.default_rate_aed)

                if resolved_rate is not None:
                    default_total = round(resolved_rate * default_sess_cnt, 2)

            decision = decisions_by_key.get(key)
            existing_ps_pair = ps_by_cohort_user.get(key)
            active_draft = active_draft_by_user.get(uid)

            if decision is not None:
                outcome = "added" if decision.decision == "added" else "ignored"
                linked_letter = (
                    letters_by_id.get(decision.payment_letter_id)
                    if decision.payment_letter_id
                    else None
                )
                linked_ps = (
                    ps_by_id.get(decision.payment_session_id)
                    if decision.payment_session_id
                    else None
                )
                if outcome == "added" and linked_ps is not None:
                    role_name = linked_ps.role
                    sess_cnt = linked_ps.session_count if linked_ps.session_count is not None else default_sess_cnt
                    hours_val = linked_ps.duration_hours if linked_ps.duration_hours is not None else default_hours
                    rate_val = linked_ps.rate_aed if linked_ps.rate_aed is not None else resolved_rate
                    total_val = float(linked_ps.compensation_aed)
                else:
                    role_name = decision.role_name or role_name
                    sess_cnt = decision.sessions_count if decision.sessions_count is not None else default_sess_cnt
                    hours_val = decision.hours if decision.hours is not None else default_hours
                    rate_val = decision.rate_aed if decision.rate_aed is not None else resolved_rate
                    total_val = float(decision.total_aed) if decision.total_aed is not None else default_total

                instructor_items.append(
                    CohortInstructorPaymentOut(
                        instructor_user_id=uid,
                        full_name=user.full_name,
                        email=user.email,
                        role_name=role_name,
                        sessions_count=sess_cnt,
                        assigned_sessions_count=len(session_ids_for_user),
                        hours=round(hours_val, 2),
                        rate_aed=rate_val,
                        rate_basis=rate_basis,
                        total_aed=total_val,
                        attendance_status=att_status,
                        attendance_tag=att_tag,
                        outcome=outcome,  # type: ignore[arg-type]
                        has_active_draft=active_draft is not None,
                        active_draft_letter_id=active_draft.id if active_draft else None,
                        letter_id=linked_letter.id if linked_letter else decision.payment_letter_id,
                        letter_reference=linked_letter.reference if linked_letter else None,
                        letter_status=linked_letter.status if linked_letter else None,
                        payment_session_id=decision.payment_session_id,
                        decided_at=decision.decided_at,
                    )
                )
            elif existing_ps_pair is not None:
                ps_row, pl_row = existing_ps_pair
                instructor_items.append(
                    CohortInstructorPaymentOut(
                        instructor_user_id=uid,
                        full_name=user.full_name,
                        email=user.email,
                        role_name=ps_row.role or role_name,
                        sessions_count=ps_row.session_count if ps_row.session_count is not None else default_sess_cnt,
                        assigned_sessions_count=len(session_ids_for_user),
                        hours=round(ps_row.duration_hours if ps_row.duration_hours is not None else default_hours, 2),
                        rate_aed=ps_row.rate_aed if ps_row.rate_aed is not None else resolved_rate,
                        rate_basis=rate_basis,
                        total_aed=float(ps_row.compensation_aed),
                        attendance_status=att_status,
                        attendance_tag=att_tag,
                        outcome="added",
                        has_active_draft=active_draft is not None,
                        active_draft_letter_id=active_draft.id if active_draft else None,
                        letter_id=pl_row.id,
                        letter_reference=pl_row.reference,
                        letter_status=pl_row.status,
                        payment_session_id=ps_row.id,
                        decided_at=pl_row.created_at,
                    )
                )
            else:
                instructor_items.append(
                    CohortInstructorPaymentOut(
                        instructor_user_id=uid,
                        full_name=user.full_name,
                        email=user.email,
                        role_name=role_name,
                        sessions_count=default_sess_cnt,
                        assigned_sessions_count=len(session_ids_for_user),
                        hours=round(default_hours, 2),
                        rate_aed=resolved_rate,
                        rate_basis=rate_basis,
                        total_aed=default_total,
                        attendance_status=att_status,
                        attendance_tag=att_tag,
                        outcome="pending",
                        has_active_draft=active_draft is not None,
                        active_draft_letter_id=active_draft.id if active_draft else None,
                    )
                )

        if not instructor_items:
            continue

        outcomes = [i.outcome for i in instructor_items]
        is_settled = all(o != "pending" for o in outcomes)
        settled_outcome = _compute_settled_outcome(outcomes) if is_settled else None
        decided_dates = [i.decided_at for i in instructor_items if i.decided_at is not None]
        settled_at = max(decided_dates) if is_settled and decided_dates else None

        completed_dates = [s.completed_at for s in c_sessions if s.completed_at is not None]
        completed_date_str = (
            max(completed_dates).strftime("%d/%m/%Y")
            if completed_dates
            else (cohort.ends_on or cohort.starts_on).strftime("%d/%m/%Y")
            if (cohort.ends_on or cohort.starts_on)
            else None
        )

        location_name = await _cohort_location_name(db, cohort, c_sessions, locations_by_id)
        date_range = _cohort_date_range(cohort, c_sessions)

        out.append(
            CompletedCohortPaymentOut(
                cohort_id=cohort.id,
                name=cohort.name,
                program_name=program.name,
                date_range=date_range,
                completed_date=completed_date_str,
                location=location_name,
                status="settled" if is_settled else "pending",
                settled_outcome=settled_outcome,  # type: ignore[arg-type]
                settled_at=settled_at,
                instructors=instructor_items,
            )
        )

    return out


async def _upsert_decision(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    instructor_user_id: uuid.UUID,
    decision: str,
    payment_letter_id: uuid.UUID | None,
    payment_session_id: uuid.UUID | None,
    role_name: str | None,
    sessions_count: int | None,
    hours: float | None,
    rate_aed: float | None,
    total_aed: float | None,
    admin_user_id: uuid.UUID,
) -> CohortPaymentDecision:
    existing = (await db.execute(
        select(CohortPaymentDecision).where(
            CohortPaymentDecision.cohort_id == cohort_id,
            CohortPaymentDecision.instructor_user_id == instructor_user_id,
        )
    )).scalars().first()
    now = datetime.now(timezone.utc)
    if existing is None:
        existing = CohortPaymentDecision(
            id=uuid.uuid4(),
            cohort_id=cohort_id,
            instructor_user_id=instructor_user_id,
            decision=decision,
            payment_letter_id=payment_letter_id,
            payment_session_id=payment_session_id,
            role_name=role_name,
            sessions_count=sessions_count,
            hours=hours,
            rate_aed=rate_aed,
            total_aed=total_aed,
            decided_by_admin_id=admin_user_id,
            decided_at=now,
        )
        db.add(existing)
    else:
        existing.decision = decision
        existing.payment_letter_id = payment_letter_id
        existing.payment_session_id = payment_session_id
        existing.role_name = role_name
        existing.sessions_count = sessions_count
        existing.hours = hours
        existing.rate_aed = rate_aed
        existing.total_aed = total_aed
        existing.decided_by_admin_id = admin_user_id
        existing.decided_at = now
    await db.flush()
    return existing


async def settle_cohort_payment(
    db: AsyncSession,
    cohort_id: uuid.UUID,
    body: SettleCohortPaymentIn,
    admin_user_id: uuid.UUID,
) -> SettleCohortPaymentOut:
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail="Cohort not found")
    if cohort.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed cohorts can be settled in Payments")

    program = await db.get(Program, cohort.program_id)
    sessions = (await db.execute(
        select(Session).where(Session.cohort_id == cohort_id).order_by(Session.meeting_date.asc())
    )).scalars().all()
    locations_by_id: dict[uuid.UUID, Location] = {}
    location_name = await _cohort_location_name(db, cohort, sessions, locations_by_id)
    date_range = _cohort_date_range(cohort, sessions)
    workshop_title = cohort.name or (program.name if program else "Cohort")

    session_ids_by_user: dict[uuid.UUID, list[uuid.UUID]] = {}
    for si in (await db.execute(
        select(SessionInstructor, Session.id)
        .join(Session, Session.id == SessionInstructor.session_id)
        .where(Session.cohort_id == cohort_id)
    )).all():
        session_ids_by_user.setdefault(si[0].user_id, []).append(si[1])

    created_drafts = 0
    appended_drafts = 0
    ignored_count = 0
    touched_letter_ids: list[uuid.UUID] = []

    for item in body.items:
        if item.action == "ignore":
            await _upsert_decision(
                db,
                cohort_id=cohort_id,
                instructor_user_id=item.instructor_user_id,
                decision="ignored",
                payment_letter_id=None,
                payment_session_id=None,
                role_name=item.role,
                sessions_count=item.sessions_count,
                hours=item.hours,
                rate_aed=item.rate_aed,
                total_aed=item.compensation_aed,
                admin_user_id=admin_user_id,
            )
            ignored_count += 1
            continue

        # Check if an open draft already exists for this instructor
        existing_draft = (await db.execute(
            select(PaymentLetter)
            .where(
                PaymentLetter.instructor_user_id == item.instructor_user_id,
                PaymentLetter.status == PaymentLetterStatus.draft,
            )
            .order_by(PaymentLetter.created_at.desc())
            .limit(1)
        )).scalars().first()

        if existing_draft is not None:
            letter = existing_draft
            appended_drafts += 1
        else:
            letter = await find_or_create_draft_letter(db, item.instructor_user_id)
            if body.batch_id is not None and letter.batch_id is None:
                letter.batch_id = body.batch_id
            created_drafts += 1

        # Invalidate any previously generated PDF and ensure letter remains draft
        letter.pdf_url = None
        letter.pdf_path = None
        letter.status = PaymentLetterStatus.draft
        letter.is_published = False

        highest = (await db.scalar(
            select(func.max(PaymentSession.sort_order))
            .where(PaymentSession.payment_letter_id == letter.id)
        )) or 0

        line = PaymentSession(
            id=uuid.uuid4(),
            payment_letter_id=letter.id,
            cohort_id=cohort.id,
            session_id=None,
            session_date=date_range,
            workshop_description=workshop_title,
            role=item.role,
            location=location_name,
            duration_hours=item.hours,
            compensation_aed=item.compensation_aed,
            session_count=item.sessions_count,
            rate_aed=item.rate_aed,
            sort_order=highest + 1,
        )
        db.add(line)
        await db.flush()

        for sid in session_ids_by_user.get(item.instructor_user_id, []):
            exists_cov = await db.scalar(
                select(PaymentSessionCoverage.id).where(
                    PaymentSessionCoverage.payment_session_id == line.id,
                    PaymentSessionCoverage.session_id == sid,
                )
            )
            if exists_cov is None:
                db.add(PaymentSessionCoverage(
                    id=uuid.uuid4(),
                    payment_session_id=line.id,
                    session_id=sid,
                ))

        await _upsert_decision(
            db,
            cohort_id=cohort_id,
            instructor_user_id=item.instructor_user_id,
            decision="added",
            payment_letter_id=letter.id,
            payment_session_id=line.id,
            role_name=item.role,
            sessions_count=item.sessions_count,
            hours=item.hours,
            rate_aed=item.rate_aed,
            total_aed=item.compensation_aed,
            admin_user_id=admin_user_id,
        )
        if letter.id not in touched_letter_ids:
            touched_letter_ids.append(letter.id)

    await db.commit()

    refreshed = await list_completed_cohort_payments(db, cohort_id=cohort_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Cohort not found")
    return SettleCohortPaymentOut(
        cohort=refreshed[0],
        created_drafts=created_drafts,
        appended_drafts=appended_drafts,
        ignored_count=ignored_count,
        touched_letter_ids=touched_letter_ids,
    )


async def ignore_cohort_payment(
    db: AsyncSession,
    cohort_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    instructor_user_id: uuid.UUID | None = None,
) -> CompletedCohortPaymentOut:
    cohorts = await list_completed_cohort_payments(db, cohort_id=cohort_id)
    if not cohorts:
        raise HTTPException(status_code=404, detail="Completed cohort not found")
    cohort_view = cohorts[0]

    for inst in cohort_view.instructors:
        if instructor_user_id is not None and inst.instructor_user_id != instructor_user_id:
            continue
        if inst.outcome != "pending":
            continue
        await _upsert_decision(
            db,
            cohort_id=cohort_id,
            instructor_user_id=inst.instructor_user_id,
            decision="ignored",
            payment_letter_id=None,
            payment_session_id=None,
            role_name=inst.role_name,
            sessions_count=inst.sessions_count,
            hours=inst.hours,
            rate_aed=inst.rate_aed,
            total_aed=inst.total_aed,
            admin_user_id=admin_user_id,
        )

    await db.commit()
    refreshed = await list_completed_cohort_payments(db, cohort_id=cohort_id)
    return refreshed[0]


async def restore_cohort_payment(
    db: AsyncSession,
    cohort_id: uuid.UUID,
    instructor_user_id: uuid.UUID | None = None,
) -> CompletedCohortPaymentOut:
    stmt = delete(CohortPaymentDecision).where(
        CohortPaymentDecision.cohort_id == cohort_id,
        CohortPaymentDecision.decision == "ignored",
    )
    if instructor_user_id is not None:
        stmt = stmt.where(CohortPaymentDecision.instructor_user_id == instructor_user_id)
    await db.execute(stmt)
    await db.commit()

    refreshed = await list_completed_cohort_payments(db, cohort_id=cohort_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Completed cohort not found")
    return refreshed[0]


async def record_ignored_for_removed_line(
    db: AsyncSession,
    letter: PaymentLetter,
    session_row: PaymentSession,
    admin_user_id: uuid.UUID,
) -> None:
    """When a cohort-derived entry is removed from a draft letter (or an entire
    draft is ignored), mark it `ignored` so it never returns to Pending Cohorts
    or future drafts."""
    cohort_id = session_row.cohort_id
    if cohort_id is None and session_row.session_id is not None:
        sess = await db.get(Session, session_row.session_id)
        if sess is not None:
            cohort_id = sess.cohort_id
    if cohort_id is None:
        cov_cohort = await db.scalar(
            select(Session.cohort_id)
            .join(PaymentSessionCoverage, PaymentSessionCoverage.session_id == Session.id)
            .where(PaymentSessionCoverage.payment_session_id == session_row.id)
            .limit(1)
        )
        cohort_id = cov_cohort
    if cohort_id is None:
        return

    await _upsert_decision(
        db,
        cohort_id=cohort_id,
        instructor_user_id=letter.instructor_user_id,
        decision="ignored",
        payment_letter_id=None,
        payment_session_id=None,
        role_name=session_row.role,
        sessions_count=session_row.session_count,
        hours=session_row.duration_hours,
        rate_aed=session_row.rate_aed,
        total_aed=float(session_row.compensation_aed or 0),
        admin_user_id=admin_user_id,
    )


async def record_ignored_for_draft_letter(
    db: AsyncSession,
    letter: PaymentLetter,
    admin_user_id: uuid.UUID,
) -> None:
    sessions = (await db.execute(
        select(PaymentSession).where(PaymentSession.payment_letter_id == letter.id)
    )).scalars().all()
    for s in sessions:
        await record_ignored_for_removed_line(db, letter, s, admin_user_id)


def _letter_paid_month(letter: PaymentLetter) -> tuple[str, str]:
    dt = letter.paid_at
    if dt is None and letter.letter_date:
        try:
            dt = datetime.strptime(letter.letter_date.strip(), "%d/%m/%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            dt = None
    if dt is None:
        dt = letter.updated_at or letter.created_at or datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}", f"{_MONTH_ABBR[dt.month - 1]} {dt.year}"


async def compute_paid_analytics(
    db: AsyncSession,
    instructor_user_id: uuid.UUID | None = None,
) -> PaymentsAnalyticsOut:
    """Strictly derived from `status == 'paid'` payment letters."""
    stmt = select(PaymentLetter).where(PaymentLetter.status == PaymentLetterStatus.paid)
    if instructor_user_id is not None:
        stmt = stmt.where(PaymentLetter.instructor_user_id == instructor_user_id)
    paid_letters = (await db.execute(stmt)).scalars().all()
    if not paid_letters:
        return PaymentsAnalyticsOut(
            total_paid_aed=0.0,
            paid_letters_count=0,
            paid_sessions_count=0,
            paid_hours_count=0.0,
            paid_instructors_count=0,
            monthly_paid=[],
        )

    letter_ids = [l.id for l in paid_letters]
    sessions = (await db.execute(
        select(PaymentSession).where(PaymentSession.payment_letter_id.in_(letter_ids))
    )).scalars().all()
    addons = (await db.execute(
        select(PaymentAddon).where(PaymentAddon.payment_letter_id.in_(letter_ids))
    )).scalars().all()

    sess_by_letter: dict[uuid.UUID, list[PaymentSession]] = {}
    for s in sessions:
        sess_by_letter.setdefault(s.payment_letter_id, []).append(s)

    addon_by_letter: dict[uuid.UUID, list[PaymentAddon]] = {}
    for a in addons:
        addon_by_letter.setdefault(a.payment_letter_id, []).append(a)

    total_paid_aed = 0.0
    paid_sessions_count = 0
    paid_hours_count = 0.0
    monthly_buckets: dict[str, dict] = {}

    for l in paid_letters:
        l_sessions = sess_by_letter.get(l.id, [])
        l_addons = addon_by_letter.get(l.id, [])
        l_total = (
            sum(float(s.compensation_aed or 0) for s in l_sessions)
            + sum(float(a.amount_aed or 0) for a in l_addons)
        )
        total_paid_aed += l_total
        paid_sessions_count += sum(
            int(s.session_count) if s.session_count is not None else 1
            for s in l_sessions
        )
        paid_hours_count += sum(float(s.duration_hours or 0) for s in l_sessions)

        m_key, m_label = _letter_paid_month(l)
        bucket = monthly_buckets.setdefault(
            m_key,
            {"month_key": m_key, "month_label": m_label, "amount_aed": 0.0, "letters_count": 0},
        )
        bucket["amount_aed"] = round(bucket["amount_aed"] + l_total, 2)
        bucket["letters_count"] += 1

    monthly_paid = [
        MonthlyPaidPointOut(**monthly_buckets[k])
        for k in sorted(monthly_buckets.keys())
    ]

    return PaymentsAnalyticsOut(
        total_paid_aed=round(total_paid_aed, 2),
        paid_letters_count=len(paid_letters),
        paid_sessions_count=paid_sessions_count,
        paid_hours_count=round(paid_hours_count, 2),
        paid_instructors_count=len({l.instructor_user_id for l in paid_letters}),
        monthly_paid=monthly_paid,
    )


async def get_instructor_payment_history(
    db: AsyncSession,
    instructor_user_id: uuid.UUID,
) -> InstructorPaymentHistoryOut:
    user = await db.get(User, instructor_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Instructor not found")

    bank = (await db.execute(
        select(InstructorBankDetails).where(InstructorBankDetails.user_id == instructor_user_id)
    )).scalars().first()

    analytics = await compute_paid_analytics(db, instructor_user_id=instructor_user_id)
    avg_per_session = (
        round(analytics.total_paid_aed / analytics.paid_sessions_count, 2)
        if analytics.paid_sessions_count > 0
        else 0.0
    )

    letters = (await db.execute(
        select(PaymentLetter)
        .where(PaymentLetter.instructor_user_id == instructor_user_id)
        .order_by(PaymentLetter.created_at.desc())
    )).scalars().all()

    letter_ids = [l.id for l in letters]
    batch_ids = {l.batch_id for l in letters if l.batch_id is not None}
    batches_by_id: dict[uuid.UUID, str] = {}
    if batch_ids:
        for b in (await db.execute(select(PaymentBatch).where(PaymentBatch.id.in_(batch_ids)))).scalars().all():
            batches_by_id[b.id] = b.name

    sess_by_letter: dict[uuid.UUID, list[PaymentSession]] = {}
    addon_by_letter: dict[uuid.UUID, list[PaymentAddon]] = {}
    if letter_ids:
        for s in (await db.execute(
            select(PaymentSession).where(PaymentSession.payment_letter_id.in_(letter_ids)).order_by(PaymentSession.sort_order)
        )).scalars().all():
            sess_by_letter.setdefault(s.payment_letter_id, []).append(s)
        for a in (await db.execute(
            select(PaymentAddon).where(PaymentAddon.payment_letter_id.in_(letter_ids)).order_by(PaymentAddon.sort_order)
        )).scalars().all():
            addon_by_letter.setdefault(a.payment_letter_id, []).append(a)

    draft_count = 0
    published_count = 0
    signed_count = 0
    pending_payout_aed = 0.0
    letters_out: list[PaymentLetterOut] = []

    for l in letters:
        l_sessions = sess_by_letter.get(l.id, [])
        l_addons = addon_by_letter.get(l.id, [])
        l_total = (
            sum(float(s.compensation_aed or 0) for s in l_sessions)
            + sum(float(a.amount_aed or 0) for a in l_addons)
        )
        if l.status == PaymentLetterStatus.draft:
            draft_count += 1
            pending_payout_aed += l_total
        elif l.status == PaymentLetterStatus.published:
            published_count += 1
            pending_payout_aed += l_total
        elif l.status == PaymentLetterStatus.signed:
            signed_count += 1
            pending_payout_aed += l_total

        item = PaymentLetterOut.model_validate(l, from_attributes=True)
        item.instructor_name = user.full_name
        item.batch_name = batches_by_id.get(l.batch_id) if l.batch_id else None
        item.sessions = l_sessions
        item.addons = l_addons
        item.pdf_url = await storage.resolve_url("payment-letters", l.pdf_path, l.pdf_url)
        item.signed_pdf_url = await storage.resolve_url("payment-letters", l.signed_pdf_path, l.signed_pdf_url)
        letters_out.append(item)

    return InstructorPaymentHistoryOut(
        instructor_user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        bank_details_complete=bool(bank and bank.is_complete),
        bank_name=bank.bank_name if bank else None,
        total_paid_aed=analytics.total_paid_aed,
        paid_letters_count=analytics.paid_letters_count,
        paid_sessions_count=analytics.paid_sessions_count,
        paid_hours_count=analytics.paid_hours_count,
        avg_aed_per_session=avg_per_session,
        monthly_paid=analytics.monthly_paid,
        draft_letters_count=draft_count,
        published_letters_count=published_count,
        signed_letters_count=signed_count,
        pending_payout_aed=round(pending_payout_aed, 2),
        letters=letters_out,
    )
