"""LMS Program domain — the checklist-driven redesign (2026-08-21) that
replaces the old `program_curriculum`/`cohort_curriculum` flat course list.

A student in the boss's own words: "added to a cohort" and "assigned to
an LMS program" are two distinct steps, but structurally this attaches at
the same level `program_curriculum` did — `LmsProgram.program_id` binds
a checklist to a Sessions `Program`, and every cohort under that program
inherits it automatically. A cohort can instead define its own
`LmsProgramCohortOverride`, which replaces the program's checklist
outright for that cohort's assignees — same "nearest level with any rows
wins, never merges" idiom `CohortCurriculum` used, carried forward by
`resolve_cohort_program_items` (services/lms/program.py), the one place
that reads both.

`LmsProgramItem.owner_type`/`owner_id` is a polymorphic FK to either a
`lms_programs` row or a `lms_program_cohort_overrides` row, enforced at
the service layer rather than the DB — the same discriminator idiom
`Purchase.product_type` already uses in this codebase, needed here
because a checklist item can belong to either owner and Postgres has no
single-column FK that points at two tables.

Items are resolved and materialized ONCE per student, at assignment time
(mirrors `enroll_in_cohort_curriculum`'s "enroll everything up front, no
reconciliation on read" behavior) — `LmsProgramAssignment` is the
per-student instance, `LmsProgramItemProgress` is one row per assignment
per item. For auto-tracked types (`course`, `mission_run`) `status` is
reconciled from the real source of truth on read, never trusted as
stored fact alone — same instinct as `compute_dashboard`'s `all_valid`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class LmsProgram(Base):
    """A checklist template. `program_id` is nullable (a checklist doesn't
    strictly need a parent Program, for a future standalone case) but
    unique when set — a Sessions Program has at most one checklist."""

    __tablename__ = "lms_programs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=True, unique=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # Gates the cohort's existing student_completion certificate on full
    # checklist completion (non-optional items only) when true. No new
    # certificate type — see services/sessions/delivery.py's
    # _issue_student_certificate.
    certificate_required = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LmsProgramCohortOverride(Base):
    """A cohort's own checklist, replacing its program's outright. One per
    cohort — `cohort_id` is unique. Its own `lms_program_items` rows
    (owner_type='cohort_override', owner_id=this row's id) are a
    completely separate item list from the parent `lms_programs` row's."""

    __tablename__ = "lms_program_cohort_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(
        UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    lms_program_id = Column(
        UUID(as_uuid=True), ForeignKey("lms_programs.id", ondelete="CASCADE"), nullable=False,
    )


class LmsProgramItem(Base):
    """One checklist step. `owner_type` is 'program' or 'cohort_override';
    `owner_id` points at the matching `lms_programs.id` or
    `lms_program_cohort_overrides.id` — polymorphic, not DB-enforced (see
    module docstring). Exactly one of `course_id`/`mission_id`/
    `external_url`/`submission_prompt` is populated, matching `item_type`;
    the service layer enforces this, not a CHECK constraint, same
    convention `module_items.content` already follows for its own
    type-keyed payload.
    """

    __tablename__ = "lms_program_items"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", "position", name="uq_lms_program_items_owner_position"),
        # course_id is NULL for every non-course item type — Postgres treats
        # NULLs as distinct in a UNIQUE constraint, so this only actually
        # constrains course-type rows, same "can't list a course twice"
        # invariant `ProgramCurriculum` had.
        UniqueConstraint("owner_type", "owner_id", "course_id", name="uq_lms_program_items_owner_course"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # program|cohort_override
    owner_type = Column(String(16), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    position = Column(Integer, nullable=False)
    # course|mission_run|external_link|submission|article|manual
    item_type = Column(String(16), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    optional = Column(Boolean, nullable=False, default=False, server_default="false")
    # Only meaningful for manual/submission/external_link — when true,
    # completion needs an instructor/ops confirm click instead of the
    # student's own self-check. Self-check is the v1 default everywhere
    # else (operator call, 2026-08-21: "not everything can be trackable").
    requires_confirmation = Column(Boolean, nullable=False, default=False, server_default="false")

    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    # The template mission — the per-student MissionAttempt is created at
    # assignment time via services/missions/attempts.py::start_attempt(),
    # never self-served by the student (see routers/missions/admin.py's
    # assign-attempt endpoint). variant_id is nullable — NULL means "the
    # mission's easiest variant (lowest position)", resolved at assignment
    # time by services/lms/program.py, since most missions only need one.
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=True)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("mission_variants.id", ondelete="CASCADE"), nullable=True)
    external_url = Column(String(512), nullable=True)
    # What a `submission`-type item asks the student to paste back — same
    # shape as the Poster tab's link-paste-back flow.
    submission_prompt = Column(Text, nullable=True)


class LmsProgramAssignment(Base):
    """One student's instance of a program (or cohort override) checklist.
    `UNIQUE(user_id, cohort_id)` is idempotency for re-running the
    registration-time assignment, not a "one program at a time" limit —
    a student can hold assignments from different cohorts/programs
    concurrently (operator call, 2026-08-21: multiple programs allowed,
    no artificial constraint)."""

    __tablename__ = "lms_program_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "cohort_id", name="uq_lms_program_assignments_user_cohort"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lms_program_id = Column(
        UUID(as_uuid=True), ForeignKey("lms_programs.id", ondelete="CASCADE"), nullable=False,
    )
    # Provenance + the certificate gate's join key — SET NULL so the
    # assignment survives its cohort being deleted, same convention
    # Enrollment.program_id/registration_id already follow.
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)
    registration_id = Column(
        UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True,
    )
    assigned_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LmsProgramItemProgress(Base):
    """Per-student, per-item completion. For `course`/`mission_run` items
    `status` is reconciled from the real Enrollment/MissionAttempt state
    on read (services/lms/program.py) rather than trusted as stored fact
    alone; for the manual/external/submission/article types it's the
    literal record of a self-check or an ops/instructor confirmation."""

    __tablename__ = "lms_program_item_progress"
    __table_args__ = (
        UniqueConstraint("assignment_id", "item_id", name="uq_lms_program_item_progress_assignment_item"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(
        UUID(as_uuid=True), ForeignKey("lms_program_assignments.id", ondelete="CASCADE"), nullable=False,
    )
    item_id = Column(UUID(as_uuid=True), ForeignKey("lms_program_items.id", ondelete="CASCADE"), nullable=False)
    # pending|done|awaiting_confirmation
    status = Column(String(24), nullable=False, default="pending", server_default="pending")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Set once, at assignment time, for `mission_run` items only — the
    # specific ops-assigned attempt this checklist step tracks (there can
    # be several attempts on the same mission; this pins which one).
    mission_attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("mission_attempts.id", ondelete="SET NULL"), nullable=True,
    )
    # What the student pasted back for a `submission`-type item — same
    # shape as the Poster tab's link-paste-back flow.
    submitted_url = Column(String(512), nullable=True)
