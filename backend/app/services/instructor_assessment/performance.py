"""Instructor Performance Profile — every number here is computed live from
source tables, never stored as a running total (the "derive, never cache"
convention every other leaderboard/aggregate in this codebase follows —
`services/sessions/openings.py::openings_for_session`, the games/competition
leaderboards, etc.).

"Delivered" means present + approved (`InstructorSessionDay.att_status ==
'present' and status == 'approved'`) — the platform's own existing
definition of "a paid day" (see that model's docstring) — not merely
assigned. One decision answers sessions/hours delivered and the reliability
ratio consistently.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructor_assessment.attempt import AssessmentAttempt
from app.models.instructor_assessment.rating import (
    RATING_DIMENSIONS,
    InstructorCertificationTag,
    InstructorProgramRating,
)
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.instructor_document import InstructorDocument
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.inventory.city import City
from app.models.inventory.location import Location
from app.models.sessions.checklist import InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_assignment import CohortInstructorAssignment
from app.models.sessions.cohort_call import CohortCall
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services import storage
from app.services.documents.card_id import format_card_id
from app.services.documents.compliance import evaluate_instructor_compliance
from app.services.documents.id_card import ensure_card_number
from app.services.sessions.openings import resolve_duration


def overall_rating(dimension_scores: dict[str, int]) -> float:
    values = [dimension_scores.get(k) for k in RATING_DIMENSIONS if dimension_scores.get(k) is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _compute_dimension_averages(ratings: list[InstructorProgramRating]) -> dict[str, float]:
    """Per-dimension mean across submitted cohort ratings."""
    if not ratings:
        return {}
    averages: dict[str, float] = {}
    for key in RATING_DIMENSIONS:
        vals = [
            float(r.dimension_scores[key])
            for r in ratings
            if r.dimension_scores and r.dimension_scores.get(key) is not None
        ]
        if vals:
            averages[key] = round(sum(vals) / len(vals), 2)
    return averages


def _session_duration_hours(session: Session, cohort: Cohort | None, program: Program | None) -> float:
    if session.duration_hours is not None:
        return float(session.duration_hours)
    if cohort is not None and cohort.duration_hours is not None:
        return float(cohort.duration_hours)
    if program is not None and program.duration_hours is not None:
        return float(program.duration_hours)
    return 0.0


def _certified_tag_for(tags: list[InstructorCertificationTag]) -> InstructorCertificationTag | None:
    for tag in tags:
        if (tag.label or "").strip().lower() == "certified":
            return tag
    return None


async def _resolve_photo_url(user: User) -> str | None:
    if not user.photo_path and not user.photo_url:
        return None
    return await storage.resolve_url("profile_pictures", user.photo_path, user.photo_url)


def _build_identity_fields(
    user: User,
    app_prof: ApplicantProfile | None,
    inst_prof: InstructorProfile | None,
    docs: list[InstructorDocument],
    cities_by_id: dict[UUID, City],
) -> dict[str, Any]:
    """Shared identity, delivery-readiness, and privacy-bounded docs status."""
    city_id = user.city_id or (app_prof.city_of_residence_id if app_prof else None)
    residence_city = cities_by_id.get(city_id) if city_id else None
    deliver_ids = list(app_prof.deliver_city_ids or []) if app_prof else []
    deliver_city_ids = [str(cid) for cid in deliver_ids if cid in cities_by_id]
    deliver_city_names = [cities_by_id[cid].name for cid in deliver_ids if cid in cities_by_id]

    nationality = (
        (inst_prof.nationality if inst_prof and inst_prof.nationality else None)
        or (app_prof.nationality if app_prof and app_prof.nationality else None)
    )
    graduated_university = (
        (inst_prof.graduated_university if inst_prof and inst_prof.graduated_university else None)
        or (app_prof.graduated_university if app_prof and app_prof.graduated_university else None)
        or (app_prof.university if app_prof and app_prof.university else None)
    )
    fluent_languages = list(
        (inst_prof.fluent_languages if inst_prof and inst_prof.fluent_languages else None)
        or (app_prof.fluent_languages if app_prof and app_prof.fluent_languages else None)
        or []
    )

    compliance = evaluate_instructor_compliance(
        user,
        docs,
        city_country=residence_city.country if residence_city else None,
        nationality=nationality,
    )

    return {
        "card_id": format_card_id(user.card_number, user.roles) if user.card_number is not None else None,
        "city_id": str(city_id) if city_id else None,
        "city_name": residence_city.name if residence_city else user.city_other,
        "deliver_city_ids": deliver_city_ids,
        "deliver_city_names": deliver_city_names,
        "has_own_transportation": app_prof.has_own_transportation if app_prof else None,
        "nationality": nationality,
        "graduated_university": graduated_university,
        "fluent_languages": fluent_languages,
        "docs_complete": bool(compliance["is_complete"]),
    }


async def _delivered_session_ids(db: AsyncSession, user_id: UUID) -> list[UUID]:
    """Sessions this instructor actually delivered — present, and the day
    approved by ops. Assigned-but-never-checked-in or sent-back days don't
    count."""
    return list((await db.execute(
        select(InstructorSessionDay.session_id).where(
            InstructorSessionDay.user_id == user_id,
            InstructorSessionDay.att_status == "present",
            InstructorSessionDay.status == "approved",
        )
    )).scalars().all())


async def get_performance(db: AsyncSession, user_id: UUID) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")

    if user.card_number is None:
        await ensure_card_number(db, user)
        await db.commit()
        await db.refresh(user)

    app_prof = (await db.execute(
        select(ApplicantProfile).where(ApplicantProfile.user_id == user_id)
    )).scalars().first()
    inst_prof = (await db.execute(
        select(InstructorProfile).where(InstructorProfile.user_id == user_id)
    )).scalars().first()
    docs = (await db.execute(
        select(InstructorDocument).where(InstructorDocument.user_id == user_id)
    )).scalars().all()

    city_ids_needed: set[UUID] = set()
    if user.city_id:
        city_ids_needed.add(user.city_id)
    if app_prof and app_prof.city_of_residence_id:
        city_ids_needed.add(app_prof.city_of_residence_id)
    if app_prof and app_prof.deliver_city_ids:
        city_ids_needed.update(app_prof.deliver_city_ids)

    delivered_session_ids = await _delivered_session_ids(db, user_id)
    delivered_set = set(delivered_session_ids)

    si_rows = (await db.execute(
        select(SessionInstructor, Session, DeliveryRole)
        .join(Session, Session.id == SessionInstructor.session_id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(SessionInstructor.user_id == user_id)
    )).all()
    total_assigned_ids = [si.session_id for si, _, _ in si_rows]

    assignment_rows = (await db.execute(
        select(CohortInstructorAssignment, DeliveryRole)
        .join(DeliveryRole, DeliveryRole.id == CohortInstructorAssignment.role_id)
        .where(
            CohortInstructorAssignment.user_id == user_id,
            CohortInstructorAssignment.status == "active",
        )
    )).all()

    rating_rows = (await db.execute(
        select(InstructorProgramRating, Cohort.name, Program.name, User.full_name)
        .join(Cohort, Cohort.id == InstructorProgramRating.cohort_id)
        .outerjoin(Program, Program.id == Cohort.program_id)
        .outerjoin(User, User.id == InstructorProgramRating.rater_user_id)
        .where(
            InstructorProgramRating.instructor_user_id == user_id,
            InstructorProgramRating.submitted.is_(True),
        )
        .order_by(
            InstructorProgramRating.submitted_at.asc().nullslast(),
            InstructorProgramRating.created_at.asc(),
        )
    )).all()

    attempts = (await db.execute(
        select(AssessmentAttempt)
        .where(AssessmentAttempt.user_id == user_id, AssessmentAttempt.status == "submitted")
        .order_by(AssessmentAttempt.submitted_at.desc())
    )).scalars().all()

    # Gather all cohorts the instructor touched (assigned, call-staffed, or rated)
    cohort_ids_involved: set[UUID] = set()
    for _, sess, _ in si_rows:
        cohort_ids_involved.add(sess.cohort_id)
    for assign, _ in assignment_rows:
        cohort_ids_involved.add(assign.cohort_id)
    for r, _, _, _ in rating_rows:
        cohort_ids_involved.add(r.cohort_id)

    cohorts_by_id: dict[UUID, Cohort] = {}
    programs_by_id: dict[UUID, Program] = {}
    locations_by_id: dict[UUID, Location] = {}
    if cohort_ids_involved:
        cohorts = (await db.execute(
            select(Cohort).where(Cohort.id.in_(cohort_ids_involved))
        )).scalars().all()
        cohorts_by_id = {c.id: c for c in cohorts}
        prog_ids = {c.program_id for c in cohorts if c.program_id}
        if prog_ids:
            programs_by_id = {
                p.id: p for p in (await db.execute(select(Program).where(Program.id.in_(prog_ids)))).scalars().all()
            }
        loc_ids = {c.location_id for c in cohorts if c.location_id}
        if loc_ids:
            locations_by_id = {
                loc.id: loc for loc in (await db.execute(select(Location).where(Location.id.in_(loc_ids)))).scalars().all()
            }
            city_ids_needed.update(loc.city_id for loc in locations_by_id.values() if loc.city_id)

    cities_by_id: dict[UUID, City] = {}
    if city_ids_needed:
        cities_by_id = {
            c.id: c for c in (await db.execute(select(City).where(City.id.in_(city_ids_needed)))).scalars().all()
        }

    # Resolve delivered session hours globally and per cohort
    total_hours = 0.0
    program_ids: set[UUID] = set()
    hours_by_cohort: dict[UUID, float] = defaultdict(float)
    assigned_by_cohort: dict[UUID, int] = defaultdict(int)
    delivered_by_cohort: dict[UUID, int] = defaultdict(int)
    direct_role_by_cohort: dict[UUID, str] = {}

    for _, sess, role in si_rows:
        assigned_by_cohort[sess.cohort_id] += 1
        direct_role_by_cohort.setdefault(sess.cohort_id, role.name)
        if sess.id in delivered_set:
            delivered_by_cohort[sess.cohort_id] += 1
            hours = await resolve_duration(db, sess)
            if hours is not None:
                h_val = float(hours)
                total_hours += h_val
                hours_by_cohort[sess.cohort_id] += h_val
            cohort_obj = cohorts_by_id.get(sess.cohort_id)
            if cohort_obj and cohort_obj.program_id:
                program_ids.add(cohort_obj.program_id)

    # Also handle edge case where InstructorSessionDay has an approved session not matching si_rows
    si_session_ids = {sess.id for _, sess, _ in si_rows}
    extra_delivered = [sid for sid in delivered_session_ids if sid not in si_session_ids]
    if extra_delivered:
        extra_rows = (await db.execute(
            select(Session, Cohort.program_id)
            .join(Cohort, Cohort.id == Session.cohort_id)
            .where(Session.id.in_(extra_delivered))
        )).all()
        for sess, prog_id in extra_rows:
            hours = await resolve_duration(db, sess)
            if hours is not None:
                h_val = float(hours)
                total_hours += h_val
                hours_by_cohort[sess.cohort_id] += h_val
            delivered_by_cohort[sess.cohort_id] += 1
            if prog_id is not None:
                program_ids.add(prog_id)

    reliability_ratio: Optional[float] = None
    if total_assigned_ids:
        reliability_ratio = round(len(delivered_session_ids) / len(total_assigned_ids), 3)

    submitted_ratings = [rating for rating, _, _, _ in rating_rows]
    rating_history = [
        {
            "rating_id": rating.id,
            "cohort_id": rating.cohort_id,
            "program_name": program_name or cohort_name,
            "rater_name": rater_name,
            "overall_rating": overall_rating(rating.dimension_scores),
            "dimension_scores": dict(rating.dimension_scores or {}),
            "recommended": rating.recommended,
            "flag": rating.flag,
            "strengths": rating.strengths,
            "areas_for_improvement": rating.areas_for_improvement,
            "submitted_at": rating.submitted_at,
        }
        for rating, cohort_name, program_name, rater_name in rating_rows
    ]
    recent_trend = [r["overall_rating"] for r in rating_history[-6:]]
    average_rating = (
        round(sum(r["overall_rating"] for r in rating_history) / len(rating_history), 2)
        if rating_history else None
    )
    dimension_averages = _compute_dimension_averages(submitted_ratings)

    latest_rating_by_cohort: dict[UUID, dict[str, Any]] = {}
    for rating, _, _, rater_name in rating_rows:
        latest_rating_by_cohort[rating.cohort_id] = {
            "rating_id": rating.id,
            "overall_rating": overall_rating(rating.dimension_scores),
            "dimension_scores": dict(rating.dimension_scores or {}),
            "recommended": rating.recommended,
            "flag": rating.flag,
            "strengths": rating.strengths,
            "areas_for_improvement": rating.areas_for_improvement,
            "rater_name": rater_name,
            "submitted_at": rating.submitted_at,
        }

    # Pre-session quiz history and per-cohort latest quiz attempt
    call_ids = {a.cohort_call_id for a in attempts if a.cohort_call_id}
    calls_by_id: dict[UUID, CohortCall] = {}
    if call_ids:
        calls_by_id = {
            c.id: c for c in (await db.execute(select(CohortCall).where(CohortCall.id.in_(call_ids)))).scalars().all()
        }

    quiz_history = []
    latest_quiz_by_cohort: dict[UUID, dict[str, Any]] = {}
    for attempt in attempts:
        call = calls_by_id.get(attempt.cohort_call_id)
        cohort = cohorts_by_id.get(call.cohort_id) if call else None
        if cohort is None and call is not None:
            cohort = await db.get(Cohort, call.cohort_id)
        program = programs_by_id.get(cohort.program_id) if cohort and cohort.program_id else None
        if program is None and cohort and cohort.program_id:
            program = await db.get(Program, cohort.program_id)

        quiz_history.append({
            "attempt_id": attempt.id,
            "cohort_id": cohort.id if cohort else None,
            "program_name": (program.name if program else None) or (cohort.name if cohort else ""),
            "score": attempt.score,
            "total": attempt.total,
            "critical_correct": attempt.critical_correct,
            "critical_total": attempt.critical_total,
            "submitted_at": attempt.submitted_at,
        })
        if cohort and cohort.id not in latest_quiz_by_cohort:
            latest_quiz_by_cohort[cohort.id] = {
                "quiz_attempt_id": attempt.id,
                "quiz_score": attempt.score,
                "quiz_total": attempt.total,
                "quiz_submitted_at": attempt.submitted_at,
            }

    assignment_by_cohort = {a.cohort_id: (a, r) for a, r in assignment_rows}

    cohort_history: list[dict[str, Any]] = []
    for cid in cohort_ids_involved:
        cohort = cohorts_by_id.get(cid)
        if cohort is None:
            continue
        prog = programs_by_id.get(cohort.program_id) if cohort.program_id else None
        loc = locations_by_id.get(cohort.location_id) if cohort.location_id else None
        city_obj = cities_by_id.get(loc.city_id) if loc and loc.city_id else None

        assign_pair = assignment_by_cohort.get(cid)
        role_name = assign_pair[1].name if assign_pair else direct_role_by_cohort.get(cid)
        staffing_source = (
            "Cohort Call"
            if assign_pair and assign_pair[0].source == "call"
            else "Direct Assigned"
        )
        quiz_meta = latest_quiz_by_cohort.get(cid, {})
        cohort_history.append({
            "cohort_id": cid,
            "cohort_name": cohort.name,
            "program_id": cohort.program_id,
            "program_name": prog.name if prog else None,
            "starts_on": cohort.starts_on,
            "ends_on": cohort.ends_on,
            "city_name": city_obj.name if city_obj else cohort.location,
            "role_name": role_name,
            "staffing_source": staffing_source,
            "sessions_assigned": assigned_by_cohort.get(cid, 0),
            "sessions_delivered": delivered_by_cohort.get(cid, 0),
            "hours_delivered": round(hours_by_cohort.get(cid, 0.0), 1),
            "quiz_attempt_id": quiz_meta.get("quiz_attempt_id"),
            "quiz_score": quiz_meta.get("quiz_score"),
            "quiz_total": quiz_meta.get("quiz_total"),
            "quiz_submitted_at": quiz_meta.get("quiz_submitted_at"),
            "rating": latest_rating_by_cohort.get(cid),
        })

    cohort_history.sort(
        key=lambda c: (
            c["starts_on"].isoformat() if c["starts_on"] else "",
            c["cohort_name"].lower(),
        ),
        reverse=True,
    )

    certifications = list((await db.execute(
        select(InstructorCertificationTag)
        .where(InstructorCertificationTag.user_id == user_id)
        .order_by(InstructorCertificationTag.created_at.desc())
    )).scalars().all())
    certified_tag = _certified_tag_for(certifications)

    identity = _build_identity_fields(user, app_prof, inst_prof, docs, cities_by_id)
    photo_url = await _resolve_photo_url(user)

    return {
        "user_id": user_id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "photo_url": photo_url,
        "linkedin_url": user.linkedin_url,
        **identity,
        "is_certified": certified_tag is not None,
        "certified_tag_id": certified_tag.id if certified_tag else None,
        "total_sessions_assigned": len(total_assigned_ids),
        "total_sessions_delivered": len(delivered_session_ids),
        "total_hours_delivered": round(total_hours, 1),
        "programs_participated_in": len(program_ids),
        "cohorts_participated_in": len(cohort_history),
        "unrated_cohorts_count": sum(1 for c in cohort_history if c["rating"] is None),
        "average_rating": average_rating,
        "recent_rating_trend": recent_trend,
        "reliability_ratio": reliability_ratio,
        "dimension_averages": dimension_averages,
        "certifications": certifications,
        "quiz_history": quiz_history,
        "rating_history": rating_history,
        "cohort_history": cohort_history,
    }


async def list_ops_instructors(db: AsyncSession) -> list[dict[str, Any]]:
    """Batch-loaded Operations instructor directory with delivery readiness,
    card ID, Certified state, privacy-bounded single-chip compliance boolean,
    and live aggregated performance metrics."""
    rows = (await db.execute(
        select(User, ApplicantProfile, InstructorProfile)
        .outerjoin(ApplicantProfile, ApplicantProfile.user_id == User.id)
        .outerjoin(InstructorProfile, InstructorProfile.user_id == User.id)
        .where(User.roles.any("instructor"))
        .order_by(User.full_name.asc())
    )).all()
    if not rows:
        return []

    user_ids = [u.id for u, _, _ in rows]

    needed_city_ids: set[UUID] = set()
    for u, ap, _ in rows:
        if u.city_id:
            needed_city_ids.add(u.city_id)
        if ap and ap.city_of_residence_id:
            needed_city_ids.add(ap.city_of_residence_id)
        if ap and ap.deliver_city_ids:
            needed_city_ids.update(ap.deliver_city_ids)

    cities_by_id: dict[UUID, City] = {}
    if needed_city_ids:
        cities_by_id = {
            c.id: c
            for c in (await db.execute(select(City).where(City.id.in_(needed_city_ids)))).scalars().all()
        }

    docs_by_user: dict[UUID, list[InstructorDocument]] = defaultdict(list)
    for d in (await db.execute(select(InstructorDocument).where(InstructorDocument.user_id.in_(user_ids)))).scalars().all():
        docs_by_user[d.user_id].append(d)

    tags_by_user: dict[UUID, list[InstructorCertificationTag]] = defaultdict(list)
    for tag in (await db.execute(
        select(InstructorCertificationTag)
        .where(InstructorCertificationTag.user_id.in_(user_ids))
        .order_by(InstructorCertificationTag.created_at.desc())
    )).scalars().all():
        tags_by_user[tag.user_id].append(tag)

    si_all = (await db.execute(
        select(SessionInstructor.user_id, Session)
        .join(Session, Session.id == SessionInstructor.session_id)
        .where(SessionInstructor.user_id.in_(user_ids))
    )).all()

    assigned_count_by_user: dict[UUID, int] = defaultdict(int)
    cohorts_by_user: dict[UUID, set[UUID]] = defaultdict(set)
    session_by_id: dict[UUID, Session] = {}
    for uid, sess in si_all:
        assigned_count_by_user[uid] += 1
        cohorts_by_user[uid].add(sess.cohort_id)
        session_by_id[sess.id] = sess

    active_assignments = (await db.execute(
        select(CohortInstructorAssignment)
        .where(
            CohortInstructorAssignment.user_id.in_(user_ids),
            CohortInstructorAssignment.status == "active",
        )
    )).scalars().all()
    for a in active_assignments:
        cohorts_by_user[a.user_id].add(a.cohort_id)

    delivered_rows = (await db.execute(
        select(InstructorSessionDay.user_id, InstructorSessionDay.session_id)
        .where(
            InstructorSessionDay.user_id.in_(user_ids),
            InstructorSessionDay.att_status == "present",
            InstructorSessionDay.status == "approved",
        )
    )).all()

    extra_session_ids = {sid for _, sid in delivered_rows if sid not in session_by_id}
    if extra_session_ids:
        for sess in (await db.execute(select(Session).where(Session.id.in_(extra_session_ids)))).scalars().all():
            session_by_id[sess.id] = sess

    cohort_ids_needed = {s.cohort_id for s in session_by_id.values()}
    cohorts_map: dict[UUID, Cohort] = {}
    programs_map: dict[UUID, Program] = {}
    if cohort_ids_needed:
        cohorts_list = (await db.execute(select(Cohort).where(Cohort.id.in_(cohort_ids_needed)))).scalars().all()
        cohorts_map = {c.id: c for c in cohorts_list}
        prog_ids = {c.program_id for c in cohorts_list if c.program_id}
        if prog_ids:
            programs_map = {
                p.id: p for p in (await db.execute(select(Program).where(Program.id.in_(prog_ids)))).scalars().all()
            }

    delivered_count_by_user: dict[UUID, int] = defaultdict(int)
    hours_by_user: dict[UUID, float] = defaultdict(float)
    for uid, sid in delivered_rows:
        delivered_count_by_user[uid] += 1
        sess = session_by_id.get(sid)
        if sess is not None:
            cohort = cohorts_map.get(sess.cohort_id)
            prog = programs_map.get(cohort.program_id) if cohort and cohort.program_id else None
            hours_by_user[uid] += _session_duration_hours(sess, cohort, prog)

    ratings_by_user: dict[UUID, list[InstructorProgramRating]] = defaultdict(list)
    for rating in (await db.execute(
        select(InstructorProgramRating).where(
            InstructorProgramRating.instructor_user_id.in_(user_ids),
            InstructorProgramRating.submitted.is_(True),
        )
    )).scalars().all():
        ratings_by_user[rating.instructor_user_id].append(rating)
        cohorts_by_user[rating.instructor_user_id].add(rating.cohort_id)

    out: list[dict[str, Any]] = []
    for user, app_prof, inst_prof in rows:
        identity = _build_identity_fields(user, app_prof, inst_prof, docs_by_user[user.id], cities_by_id)
        tags = tags_by_user[user.id]
        cert_tag = _certified_tag_for(tags)

        total_assigned = assigned_count_by_user[user.id]
        total_delivered = delivered_count_by_user[user.id]
        reliability = round(total_delivered / total_assigned, 3) if total_assigned > 0 else None

        user_ratings = ratings_by_user[user.id]
        avg_rating = (
            round(sum(overall_rating(r.dimension_scores) for r in user_ratings) / len(user_ratings), 2)
            if user_ratings
            else None
        )
        rated_cohorts = {r.cohort_id for r in user_ratings}
        user_cohorts = cohorts_by_user[user.id]
        unrated_count = sum(1 for cid in user_cohorts if cid not in rated_cohorts)
        flags = sorted({r.flag for r in user_ratings if r.flag and r.flag != "none"})

        out.append({
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "status": user.status,
            "photo_url": await _resolve_photo_url(user),
            "linkedin_url": user.linkedin_url,
            "created_at": user.created_at,
            **identity,
            "is_certified": cert_tag is not None,
            "certified_tag_id": cert_tag.id if cert_tag else None,
            "certifications": tags,
            "total_sessions_assigned": total_assigned,
            "total_sessions_delivered": total_delivered,
            "total_hours_delivered": round(hours_by_user[user.id], 1),
            "reliability_ratio": reliability,
            "cohorts_count": len(user_cohorts),
            "unrated_cohorts_count": unrated_count,
            "average_rating": avg_rating,
            "flags": flags,
        })

    return out
