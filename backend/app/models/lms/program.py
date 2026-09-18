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

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

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
    # Header/cover image shown on the student checklist page. Same
    # bucket/path-only shape as Course.image_bucket/image_path — the URL is
    # never stored, only resolved fresh at read time via storage.resolve_url.
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(512), nullable=True)
    # Gates the cohort's existing student_completion certificate on full
    # checklist completion (non-optional items only) when true. No new
    # certificate type — see services/sessions/delivery.py's
    # _issue_student_certificate.
    certificate_required = Column(Boolean, nullable=False, default=True, server_default="true")
    poster_template_url = Column(String(512), nullable=True)
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
    `external_url`/`submission_prompt`/`pdf_path`/`cohort_quiz_template_id`
    is populated, matching `item_type`; the service layer enforces this,
    not a CHECK constraint, same convention `module_items.content` already
    follows for its own type-keyed payload.
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
    # course|mission_run|external_link|submission|pdf|manual|session|quiz|team_setup
    item_type = Column(String(16), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    optional = Column(Boolean, nullable=False, default=False, server_default="false")
    # Only meaningful for manual/submission/external_link — when true,
    # completion needs an instructor/ops confirm click instead of the
    # student's own self-check. Self-check is the v1 default everywhere
    # else (operator call, 2026-08-21: "not everything can be trackable").
    requires_confirmation = Column(Boolean, nullable=False, default=False, server_default="false")
    # Competition domain (2026-08-24) — individual|team. individual (default)
    # tracks per-student, exactly as every item did before this column
    # existed. team means this item is one shared fact for a `Team`
    # (learner_teams) rather than per-student — a competition's link-only
    # deliverables (poster, video, circuit, CAD, dashboard). Progress for a
    # team-scoped item lives in `lms_program_team_item_progress`, not
    # `LmsProgramItemProgress` below — see services/lms/program.py's
    # resolver for which table a given item's progress actually reads/writes.
    scope = Column(String(16), nullable=False, default="individual", server_default="individual")

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
    # 2026-09-16 — the *single*-field submission's own type (link or text).
    # Only meaningful when submission_multi_link is False; a multi-link item
    # picks its type per field in submission_link_labels instead. Defaults
    # to "link", so every submission item authored before this existed (the
    # only kind there was) is unaffected. Which column the student's
    # paste-back lands in (submitted_url vs submitted_text) is decided by
    # this at submit time — see routers/lms/student.py::submit_program_item.
    submission_field_type = Column(String(8), nullable=False, default="link", server_default="link")
    # 2026-09-14: ops's own toggle for "one link, or several with optional
    # labels" (e.g. mem1/mem2/team link, all in one submission) — a
    # `submission`-only field (see validate_item_payload), off by default so
    # every existing single-link item is unaffected. Which column the
    # student's paste-back actually lands in (submitted_url vs
    # submitted_links) is decided by this flag at submit time — see
    # routers/lms/student.py::submit_program_item.
    submission_multi_link = Column(Boolean, nullable=False, default=False, server_default="false")
    # 2026-09-14: ops's own fixed label set for a submission_multi_link item
    # — `[{"label": str, "required": bool, "field_type": "link"|"text"},
    # ...]`, in the order ops entered them (e.g. "Member 1 link" required,
    # "Member 2 link" required, "Team link" optional, "Design writeup" as a
    # required text field). `field_type` (2026-09-16, defaults to "link" for
    # every row written before it existed) picks whether the student's form
    # shows a link input or a text area for that slot. NULL for a
    # non-multi-link item, or for a multi-link item authored before this
    # existed — that older shape (free-text, student-entered labels, none
    # required, link-only) still works unchanged; routers/lms/student.py::
    # submit_program_item and the frontend both fall back to it when this
    # is empty. Once set, this is the one source of truth for which slots
    # the student's form shows and which of them block submission — see
    # that same function's required-label check.
    submission_link_labels = Column(JSONB, nullable=True)
    # A `pdf` item's hosted file — same two-step shape as a module
    # `attachment` item (create the item, then a separate multipart upload
    # attaches the file): stored path in the `lms-attachments` bucket, NULL
    # until someone uploads one (routers/lms/admin.py's own item list shows
    # "no PDF uploaded" until then). Rendered through the same no-download
    # `PdfViewer` the Curriculum Library and module attachments already use
    # — see routers/lms/student.py's resolve-url endpoint for why the
    # signed URL is never baked into the checklist read payload.
    pdf_path = Column(String(512), nullable=True)
    # A `submission` item's optional cutoff — enforced only at submit time
    # (routers/lms/student.py's submit_program_item), not a DB constraint.
    # Confirming an already-submitted item past the deadline is untouched.
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    # A `session` item's own typed fields — always self-contained, never a
    # live FK to the Sessions domain's `Session` table: a program-level
    # checklist can span many cohorts with different session dates, so a
    # live link would be ambiguous, and `Session` itself has no
    # meeting-link field anyway. The authoring UI may optionally prefill
    # these from a real Session as a one-time copy (see LmsProgramAdmin's
    # ItemForm), but nothing here ever points back at that row.
    session_date = Column(Date, nullable=True)
    session_starts_at = Column(Time, nullable=True)
    session_location = Column(String(255), nullable=True)
    session_meeting_url = Column(String(512), nullable=True)

    # ── Roadmap board (2026-09) ─────────────────────────────────────────
    # For a `mission_run` item: which single Madar design phase this tile
    # targets — one of the DESIGN_STEP_LABELS keys, plus 'setup' and
    # 'report' (inferred completion, see services/lms/program.py's
    # `_mission_run_item_done`). NULL means "the whole mission" — today's
    # behaviour, unchanged. Never an `external_link`: the target URL needs
    # the student's own mission_attempt_id, resolved per assignment, so a
    # static authored link can't express it.
    mission_step_key = Column(String(24), nullable=True)
    # Locked until every earlier non-optional item on this checklist is
    # done — see compute_lock_states. Optional items never block and are
    # never themselves locked.
    gated = Column(Boolean, nullable=False, default=False, server_default="false")
    # pdf|link|video — the task drawer's "view the guideline" step. NULL
    # means no guideline configured. A `pdf` kind reuses this item's own
    # `pdf_path`/upload endpoint rather than a second file column; `link`/
    # `video` resolve from `guideline_url` below. `video` is a YouTube/
    # Vimeo URL rendered as an iframe embed (see lib/embed.ts) — no native
    # upload, see docs/HANDOFF_LMS.md §11's video-upload decision.
    guideline_kind = Column(String(8), nullable=True)
    guideline_url = Column(String(512), nullable=True)
    # Groups tiles into the board's row sections ("Checkpoint 1 — Learn &
    # plan"). Free text, not an id — matched by exact string, same
    # "authoring convenience, not a real entity" posture as everywhere
    # else in this table that isn't a real FK.
    checkpoint_label = Column(String(120), nullable=True)

    # A `quiz` item's fixed question set (2026-09) — see
    # `app/models/lms/cohort_quiz.py`. Every student assigned this checklist
    # item takes the same template; the per-student result lives in
    # `cohort_quiz_attempts`, keyed on this item's id, not on this column.
    # RESTRICT, not CASCADE (unlike course_id/mission_id above) — a quiz
    # template is retire-never-delete, same as `CohortQuizAttempt.
    # cohort_quiz_template_id`'s own FK; a checklist item pointing at one
    # must never silently disappear because the template row was deleted.
    cohort_quiz_template_id = Column(
        UUID(as_uuid=True), ForeignKey("cohort_quiz_templates.id", ondelete="RESTRICT"), nullable=True,
    )


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
    alone; for the manual/external/submission/pdf types it's the
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
    # shape as the Poster tab's link-paste-back flow. Used when the item is
    # NOT multi-link; a multi-link item's real answer lives in
    # `submitted_links` below instead, with this column mirroring the first
    # link's url so any older reader that only knows `submitted_url` still
    # sees *something* real rather than nothing.
    submitted_url = Column(String(512), nullable=True)
    # 2026-09-16 — the single-field submission's answer when the item's own
    # submission_field_type is "text" instead of "link". Text, not
    # String(512): a writeup can run well past that. Mutually exclusive with
    # submitted_url for a non-multi-link item — exactly one of the two is
    # ever populated, matching submission_field_type.
    submitted_text = Column(Text, nullable=True)
    # 2026-09-14: a `submission_multi_link` item's real answer — a list of
    # `{"label": str | None, "url": str | None, "text": str | None}`,
    # ops-controlled per item (e.g. "Member 1 link", "Member 2 link", "Team
    # link", "Design writeup" all in one submission). Exactly one of
    # url/text is ever set per entry, matching that label's own
    # `field_type` (2026-09-16) on `LmsProgramItem.submission_link_labels`.
    # NULL for every non-multi-link item.
    submitted_links = Column(JSONB, nullable=True)
    # When submitted_url (or status) last changed. No updated_by column —
    # unlike the team table below, an individual row only ever has one
    # possible author: the assignment's own user.
    updated_at = Column(DateTime(timezone=True), nullable=True)


class LmsProgramTeamItemProgress(Base):
    """The team-scoped twin of `LmsProgramItemProgress` above — same shape,
    keyed by `(item_id, team_id)` instead of `(item_id, assignment_id)`.

    Exists so a `scope="team"` item's progress is one row every team member
    reads and writes, without overloading the per-student table with a
    second, mutually-exclusive key (assignment_id nullable XOR team_id
    nullable is exactly the kind of one-table-two-meanings shape this
    codebase avoids elsewhere — see `LmsProgramItem.owner_type`'s own
    docstring on the same instinct). Which table a given item's progress
    lives in is decided once, by `item.scope`, in
    services/lms/program.py's resolver — never both."""

    __tablename__ = "lms_program_team_item_progress"
    __table_args__ = (
        UniqueConstraint("item_id", "team_id", name="uq_lms_program_team_item_progress_item_team"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("lms_program_items.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("learner_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    # pending|done|awaiting_confirmation — same vocabulary as the individual table.
    status = Column(String(24), nullable=False, default="pending", server_default="pending")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Set once, at first assignment time, for a team-scoped `mission_run`
    # item only (Phase 2/3, 2026-09) — the one shared MissionAttempt this
    # team's run tracks. Deliberately the single source of truth for "what
    # is this team's mission run" rather than duplicating the same attempt
    # id onto every teammate's own individual LmsProgramItemProgress row:
    # a per-student copy can silently go stale (e.g. a teammate registered
    # before the team existed and never got one written), and reading
    # "the team's" state then means guessing which teammate's copy to
    # trust. One row, one team, one answer.
    mission_attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("mission_attempts.id", ondelete="SET NULL"), nullable=True,
    )
    submitted_url = Column(String(512), nullable=True)
    # Same shape/purpose as LmsProgramItemProgress.submitted_text above.
    submitted_text = Column(Text, nullable=True)
    # Same shape/purpose as LmsProgramItemProgress.submitted_links above —
    # the team's shared multi-link answer, editable by any teammate.
    submitted_links = Column(JSONB, nullable=True)
    # Whichever teammate last pasted/edited submitted_url, and when — a team
    # row has no single "you", so the checklist shows "last updated by
    # [name]" here instead of the individual table's implicit "you".
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
