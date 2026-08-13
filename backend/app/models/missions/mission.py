"""Mission core schema (P5-1, Phase 2 Stage 5, 2026-08-11).

Template/instance split, same shape as `courses`/`enrollments`: a `Mission`
is authored once, a `MissionAttempt` is one student's run against it. Unlike
a course, a mission has difficulty — `MissionVariant` rows — and readiness
gating via `Prerequisite` (`models/curriculum.py`), a unified DAG edge table
shared with courses since 7B-2. `access_mode` (a grant, "can you see this
at all") and prerequisites (a computed rule, "have you earned the right to
attempt it") are two different mechanisms and both are correct; do not
collapse them (PHASE2_EXECUTION_PLAN.md §Stage 5 note ②).

`mission_attempts.user_id` XOR `mission_team_id` (P6-2, Stage 6) — a solo
attempt sets the former, a team attempt the latter, CHECK-enforced.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class Mission(Base):
    """A standalone challenge — the template every attempt runs against.

    `kind` is design|submission|quiz|checklist|external; only `submission`
    (P5-2) and `quiz` (P5-3) are built this stage. `team_policy` is
    solo|team|either — team attempts land in Stage 6, this column exists now
    so a mission authored today doesn't need a data migration later.
    `status` is draft|in_review|published|archived, same publish gate as
    `courses.is_published` but with a review step (`reviewed_by`) since a
    mission can be intern-authored. `access_mode` is open|invite — never
    `paid`: a mission is never sold standalone, only a course containing one
    is (§4 note, PHASE2_EXECUTION_PLAN.md).
    """

    __tablename__ = "missions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(128), nullable=False)
    slug = Column(String(160), nullable=False, unique=True)
    summary = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    # design|submission|quiz|checklist|external
    kind = Column(String(16), nullable=False)
    # solo|team|either
    team_policy = Column(String(8), nullable=False, default="solo", server_default="solo")
    # draft|in_review|published|archived
    status = Column(String(12), nullable=False, default="draft", server_default="draft")
    # open|invite (never 'paid' — see class docstring)
    access_mode = Column(String(12), nullable=False, default="open", server_default="open")
    authored_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(512), nullable=True)
    track = Column(String(80), nullable=True)  # free-text catalog grouping, matches courses.track
    # D8 (Design v2) — authored *explanatory* content: briefing copy,
    # handbook wording, advice text. Overrides only; anything absent falls
    # back to the code-authored defaults. Unlike `mission_variants.config`
    # this is always editable on a published mission, because changing an
    # explanation can't re-grade anybody.
    content = Column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MissionVariant(Base):
    """A difficulty level of one mission — every mission has at least one.
    `position` orders them easiest-first (Cadet/Engineer/Flight Director);
    `points` is absolute per variant, not derived (awarded on passing, never
    on submitting). `config` is kind-specific working data: for `quiz`, the
    exact `{pass_threshold, questions}` shape `AdminContentQuiz` already
    validates; for `design` (Stage 7), Madar's old `mission_constraints` row.
    """

    __tablename__ = "mission_variants"
    __table_args__ = (
        UniqueConstraint("mission_id", "position", name="uq_mission_variants_mission_position"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(24), nullable=False)
    position = Column(Integer, nullable=False)
    points = Column(Integer, nullable=False)
    config = Column(JSONB, nullable=False, default=dict)


class MissionAttempt(Base):
    """One student's run against one mission variant — the row a verifier
    grades. `attempt_no` is 1-based per (mission_id, user_id), computed by
    the service layer, never a DB default (mirrors `item_progress`'s own
    "no state machine" posture, just per-attempt instead of per-item).

    `status` is in_progress|submitted|passed|failed|abandoned. `payload` is
    verifier-specific working state — the submission kind's artifact
    URL/notes/review_comment, the quiz kind's answers. `score` is only
    meaningful once `decided_at` is set. Points are awarded on `passed`,
    keyed `(mission_id, variant_id)` in the points ledger's idempotency —
    passing the same variant twice doesn't re-award, but passing a *harder*
    variant of the same mission is a new idempotency key and does (mirrors
    "replay becomes meaningful" from MISSIONS_REPORT.md Ch.2).

    `mission_id`/`variant_id` are RESTRICT: an attempt has no meaning
    without knowing what it was attempted against, so neither can be
    deleted out from under grading history (there is no mission-delete
    endpoint this stage; archiving is `missions.status`, not a row delete).

    `user_id` XOR `mission_team_id` (P6-2, CHECK-enforced): a solo attempt
    sets `user_id`; a team attempt sets `mission_team_id` and snapshots the
    team's roster into `MissionAttemptMember` at start time — who's on the
    hook for this specific attempt's grade is frozen there, since the team
    itself (`MissionTeamMember`) can change membership afterward.
    """

    __tablename__ = "mission_attempts"
    __table_args__ = (
        UniqueConstraint("mission_id", "user_id", "attempt_no", name="uq_mission_attempts_mission_user_no"),
        UniqueConstraint("mission_id", "mission_team_id", "attempt_no", name="uq_mission_attempts_mission_team_no"),
        CheckConstraint(
            "(user_id IS NOT NULL AND mission_team_id IS NULL) OR (user_id IS NULL AND mission_team_id IS NOT NULL)",
            name="ck_mission_attempts_user_xor_team",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="RESTRICT"), nullable=False)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("mission_variants.id", ondelete="RESTRICT"), nullable=False)
    attempt_no = Column(Integer, nullable=False, default=1)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    # P6-2 — RESTRICT, not SET NULL: the XOR CHECK above means a team
    # attempt's mission_team_id can never actually go NULL (there's no
    # user_id to fall back on), so SET NULL would just turn "delete this
    # team" into a constraint-violation error instead of a clean RESTRICT
    # one. Same "can't delete out from under grading history" reasoning as
    # mission_id/variant_id above — a team with attempts isn't deletable.
    mission_team_id = Column(UUID(as_uuid=True), ForeignKey("mission_teams.id", ondelete="RESTRICT"), nullable=True)
    # in_progress|submitted|passed|failed|abandoned
    status = Column(String(12), nullable=False, default="in_progress", server_default="in_progress")
    score = Column(Numeric(5, 2), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class MissionAttemptMember(Base):
    """Snapshot of who was on the team for one specific attempt (P6-2),
    frozen at `start_attempt` time from `MissionTeamMember`'s roster at that
    moment. `MissionTeamMember` can change after this; this table is what
    the attempt's eventual grade and per-member point award actually mean —
    editing the team later never rewrites who earned what."""

    __tablename__ = "mission_attempt_members"
    __table_args__ = (
        PrimaryKeyConstraint("attempt_id", "user_id", name="pk_mission_attempt_members"),
    )

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("mission_attempts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
