import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class DeliveryChecklistItem(Base):
    """One line of the daily checklist an instructor works through on the day
    (operations process doc §5) — "kits distributed", "student posters
    reviewed", "tables cleaned", and so on.

    Attached at exactly one of program / cohort / session, and resolved
    **override, not merge**: the nearest level that has any rows wins outright.
    That is the same rule and the same CHECK shape as `Material`
    (`models/sessions/material.py`), for the same reason its docstring gives —
    merging would make it impossible to *remove* a program-level item for one
    cohort, which is exactly what "overridable" has to mean.

    Deliberately **not** built on `checklist_modules` / `checklist_items` /
    `user_checklist_progress` (`models/instructors/checklist.py`). Those are the
    applicant-onboarding pipeline: facilitator-authored, scoped per user, owned
    by another domain and wired into the application review flow. Adding a
    scope discriminator to live tables another flow depends on would buy
    nothing here — the resolution rule this needs is the materials one, not
    theirs.

    `requires_proof` is what makes the checklist worth more than a set of
    ticks: §5 asks for a photo against specific items (the setup, students
    working, the cleaned tables), and a day cannot be submitted until every
    proof-required item actually carries a file.

    `role_id` (2026-08-28) is a second, independent axis on top of the
    program/cohort/session level: NULL means "general" (every role sees it),
    a role means "only that role's checklist." Resolution overrides here too,
    same shape as the level: at whichever level has anything at all, a role
    with its own rows sees *only* those, never the general ones too — see
    `resolve_checklist`. A role is never deleted (`DeliveryRole.is_active`),
    so RESTRICT rather than SET NULL: a role-specific checklist silently
    becoming "general" the moment a role went away would change who owes
    proof for what without anyone deciding that.
    """

    __tablename__ = "delivery_checklist_items"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_delivery_checklist_exactly_one_owner",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=True, index=True)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    # NULL = general (applies to every role at this level). Set = only that
    # role sees this item, replacing the general list rather than adding to it.
    role_id = Column(UUID(as_uuid=True), ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # §5: some items must carry a photo/screenshot before the day can be sent.
    requires_proof = Column(Boolean, nullable=False, default=False, server_default="false")
    # A non-required item is a prompt, not a gate — it never blocks submission.
    is_required = Column(Boolean, nullable=False, default=True, server_default="true")
    sort_order = Column(Integer, nullable=False, default=1)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class InstructorSessionDay(Base):
    """One instructor's day on one session: whether they turned up, what they
    did, and whether ops has signed it off.

    Attendance and the day submission are **one row, not two tables**, because
    they are the same object from two angles — "was Muna here on Tuesday" and
    "has Tuesday been approved" are answered together, and splitting them would
    mean keeping two rows per instructor per day consistent for no gain.

    **`status='approved'` AND `att_status='present'` is the definition of a
    paid day** (operations doc §18/§19, and the operator's voice note: "the
    operations or project manager confirms the instructor actually attended
    that day... that's locked in the system"). Approved + absent is an
    acknowledged absence: on the record, not paid. Nothing else in the system
    gets to decide what counts as delivered.

    `att_status` is `present|absent` only. `late`/`excused` were deliberately
    removed from student attendance in `a1d7f36c0013` for being counted
    inconsistently in different places — don't reintroduce them here.

    NULL `att_status` means the instructor hasn't answered yet, which is
    genuinely different from either answer: it is what the ops queue shows as
    "no check-in" on a morning somebody has gone quiet.
    """

    __tablename__ = "instructor_session_days"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_instructor_session_day"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # present|absent, or NULL until they answer. See the class docstring.
    att_status = Column(String(16), nullable=True)
    absence_reason = Column(Text, nullable=True)
    checked_in_at = Column(DateTime(timezone=True), nullable=True)

    # draft|submitted|changes_required|approved (operations doc §12). "Under
    # review" from the doc is not a stored state: it is what `submitted` means
    # from the ops side, and a status nobody transitions into is a status that
    # rots.
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # What ops wrote when returning it — "checklist item 6 needs evidence".
    review_comment = Column(Text, nullable=True)

    # §8's end-of-day feedback, one free-text blob. Deliberately not seven
    # named columns: the doc lists prompts, not fields, and an instructor
    # typing into one box at 3pm is the behaviour we actually want.
    instructor_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class InstructorChecklistProgress(Base):
    """One instructor's answer to one checklist item on one day.

    Proof files **reuse `session_reports`** rather than a second upload path:
    the bucket (`session-reports`), `services/sessions/reports.py::upload_report`,
    its assigned-instructor check, `resolve_report_url` and the ops "Uploaded
    Reports & Photos" list all already exist and already work. The only new
    thing needed was a foreign key pointing at one.

    SET NULL on the proof, not CASCADE: deleting an uploaded file should leave
    the tick and its history readable, showing the proof is gone rather than
    erasing that the item was ever done.
    """

    __tablename__ = "instructor_checklist_progress"
    __table_args__ = (
        UniqueConstraint("day_id", "checklist_item_id", name="uq_instructor_checklist_progress"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day_id = Column(
        UUID(as_uuid=True), ForeignKey("instructor_session_days.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    checklist_item_id = Column(
        UUID(as_uuid=True), ForeignKey("delivery_checklist_items.id", ondelete="CASCADE"), nullable=False
    )
    is_done = Column(Boolean, nullable=False, default=False, server_default="false")
    proof_report_id = Column(
        UUID(as_uuid=True), ForeignKey("session_reports.id", ondelete="SET NULL"), nullable=True
    )
    note = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
