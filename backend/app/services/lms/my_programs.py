"""My Programs (P4-3, LMS Phase 2 Stage 4, 2026-08-10) — the cohort view a
student cannot currently see at all: dates, location, instructor,
attendance, courses. Pure composition over resolvers that already exist
(resolve_cohort_curriculum, resolve_session_location_display,
course_completion) — the highest student-visible value in the whole
Phase 2 plan for how little new logic it needed.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.user import User
from app.services.lms.program import resolve_cohort_program_course_ids
from app.services.lms.progress import course_completion
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES
from app.services.sessions.staffing import resolve_session_location_display


async def my_programs(db: AsyncSession, *, user: User) -> list[dict]:
    """Every active registration for the caller's own contact, newest
    first. Empty (not an error) for a user with no linked contact_id —
    there is nothing to have registered for."""
    if user.contact_id is None:
        return []

    rows = (await db.execute(
        select(Registration, Cohort, Program)
        .join(Cohort, Cohort.id == Registration.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .where(
            Registration.contact_id == user.contact_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
        .order_by(Registration.created_at.desc())
    )).all()

    result = []
    for registration, cohort, program in rows:
        location = await resolve_session_location_display(db, cohort=cohort)

        instructor_name = None
        if cohort.lead_instructor_user_id:
            instructor = await db.get(User, cohort.lead_instructor_user_id)
            instructor_name = instructor.full_name if instructor else None

        attendance_counts = dict((await db.execute(
            select(AttendanceRecord.att_status, func.count())
            .where(AttendanceRecord.registration_id == registration.id)
            .group_by(AttendanceRecord.att_status)
        )).all())

        course_ids = await resolve_cohort_program_course_ids(db, cohort.id)
        courses = []
        if course_ids:
            course_rows = (await db.execute(select(Course).where(Course.id.in_(course_ids)))).scalars().all()
            courses_by_id = {c.id: c for c in course_rows}
            enrolled_ids = set((await db.execute(
                select(Enrollment.course_id).where(
                    Enrollment.user_id == user.id, Enrollment.course_id.in_(course_ids),
                )
            )).scalars().all())
            for course_id in course_ids:
                course = courses_by_id.get(course_id)
                if course is None:
                    continue
                enrolled = course_id in enrolled_ids
                pct = 0
                if enrolled:
                    completion = await course_completion(db, user_id=user.id, course_id=course_id)
                    modules_total = len(completion["modules"])
                    modules_done = sum(1 for m in completion["modules"] if m["completed"])
                    pct = round(100 * modules_done / modules_total) if modules_total else 0
                courses.append({
                    "course_id": course.id, "title": course.title, "enrolled": enrolled, "progress_pct": pct,
                })

        result.append({
            "registration_id": registration.id,
            "cohort_id": cohort.id,
            "program_name": program.name,
            "cohort_name": cohort.name,
            "starts_on": cohort.starts_on,
            "ends_on": cohort.ends_on,
            "location_name": location["name"],
            "location_address": location["address"],
            "instructor_name": instructor_name,
            "attended_sessions": attendance_counts.get("present", 0),
            "total_sessions": sum(attendance_counts.values()),
            "courses": courses,
            # Stage 5 (missions) lands this key with real content; empty
            # until then rather than omitted, so the frontend never has to
            # branch on whether the key exists.
            "missions": [],
        })
    return result
