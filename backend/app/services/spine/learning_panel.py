"""Learning panel (P3-1, LMS Phase 2 Stage 3, 2026-08-10) — "what is this
student's situation", assembled for the contact detail page.

Built on `contacts`, not a second `users`-keyed list (Stage 3's own
framing in PHASE2_EXECUTION_PLAN.md — "a second student list keyed on
users is the same feature built twice"). Reads across the LMS, sessions
and points domains for one contact; nothing here writes anything.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment
from app.models.lms.points import PointEvent
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.progress import course_completion


async def build_learning_panel(db: AsyncSession, contact: Contact) -> dict | None:
    """None for a contact that has never held the `student` role — the
    caller (routers/spine/contacts.py) skips calling this entirely for a
    non-student contact, so this guard is belt-and-suspenders, not the
    only check."""
    if "student" not in (contact.contact_roles or []):
        return None

    user = (await db.execute(
        select(User).where(User.contact_id == contact.id).order_by(User.created_at)
    )).scalars().first()

    if user is None:
        return {
            "has_account": False, "user_id": None, "email": None,
            "account_status": None, "must_change_password": None,
            "points_total": 0, "enrollments": [], "registrations": [], "certificates": [],
        }

    points_total = await db.scalar(
        select(func.coalesce(func.sum(PointEvent.points), 0)).where(PointEvent.user_id == user.id)
    )

    enrollment_rows = (await db.execute(
        select(Enrollment, Course)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Enrollment.user_id == user.id)
        .order_by(Enrollment.created_at.desc())
    )).all()
    granter_ids = {e.granted_by for e, _c in enrollment_rows if e.granted_by is not None}
    granters: dict[uuid.UUID, User] = {}
    if granter_ids:
        rows = (await db.execute(select(User).where(User.id.in_(granter_ids)))).scalars().all()
        granters = {u.id: u for u in rows}

    enrollments = []
    for enrollment, course in enrollment_rows:
        completion = await course_completion(db, user_id=user.id, course_id=course.id)
        modules_total = len(completion["modules"])
        modules_done = sum(1 for m in completion["modules"] if m["completed"])
        pct = round(100 * modules_done / modules_total) if modules_total else 0
        granter = granters.get(enrollment.granted_by) if enrollment.granted_by else None
        enrollments.append({
            "enrollment_id": enrollment.id, "course_id": course.id, "course_title": course.title,
            "status": enrollment.status, "source": enrollment.source,
            "granted_by_name": granter.full_name if granter else None,
            "expires_at": enrollment.expires_at, "progress_pct": pct,
        })

    registration_rows = (await db.execute(
        select(Registration, Cohort, Program)
        .join(Cohort, Cohort.id == Registration.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .where(Registration.contact_id == contact.id)
        .order_by(Registration.created_at.desc())
    )).all()

    registrations = []
    for registration, cohort, program in registration_rows:
        attendance_counts = (await db.execute(
            select(AttendanceRecord.att_status, func.count())
            .where(AttendanceRecord.registration_id == registration.id)
            .group_by(AttendanceRecord.att_status)
        )).all()
        counts = dict(attendance_counts)
        registrations.append({
            "id": registration.id, "cohort_id": cohort.id, "cohort_name": cohort.name,
            "program_name": program.name, "status": registration.status,
            "payment_status": registration.payment_status, "price_charged": registration.price_charged,
            "attended_sessions": counts.get("present", 0),
            "total_sessions": sum(counts.values()),
        })

    certificate_rows = (await db.execute(
        select(Certificate).where(Certificate.contact_id == contact.id).order_by(Certificate.generated_at.desc())
    )).scalars().all()
    certificates = [
        {"id": c.id, "type": c.type, "generated_at": c.generated_at} for c in certificate_rows
    ]

    return {
        "has_account": True,
        "user_id": user.id,
        "email": user.email,
        "account_status": user.status,
        "must_change_password": user.must_change_password,
        "points_total": int(points_total or 0),
        "enrollments": enrollments,
        "registrations": registrations,
        "certificates": certificates,
    }
