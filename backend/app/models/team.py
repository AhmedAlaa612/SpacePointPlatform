"""Learner teams (2026-08-17) — a top-level, domain-agnostic team entity,
generalized out of the missions-only `MissionTeam`. This is the opening move
of the Competition domain (per the August Build Brief): Competition needs
teams too, and building its team logic against a missions-only table would
mean redoing it once Competition lands.

`__tablename__` is `learner_teams`, not `teams` — `models/interns/team.py`
already owns `teams` (a fully separate, unrelated internship-program
concept: a globally-unique `name`, NOT NULL `epics.team_id`, joined by
`project_teams`). Reusing that table would need a filter added to every
existing intern query, and one missed filter is a silent cross-domain leak
— same reasoning the original `MissionTeam` docstring gave for not reusing
`interns.Team`, now doubly true since this table is meant to be shared
across domains itself. `cohort_id` is NULL for a self-formed team from a
public catalog — cohort-scoped teams are named uniquely per cohort
(case-insensitively — enforced by a `lower(name)` expression unique index,
migration `b4f1c8e30a72_learner_teams_roster_id_ci_name`, not declarable as
a plain `UniqueConstraint` here), not globally, so two cohorts can both
have a "Team Alpha"; self-formed teams (`cohort_id` NULL) aren't
deduplicated by name at all — NULL never equals NULL in a unique
constraint/index.

`roster_team_id` (2026-09-14, competition roster import) is the *import's*
grouping key — an external id/code from ops's roster sheet, e.g. "T-014" —
kept deliberately separate from `name`: a roster import groups students
into a team well before that team necessarily has a real display name
(see `services/competitions/registration_import.py`). NULL for any team
not created through that import path (ops's ad-hoc "Add team", a
self-formed team, every team that predates this column). When a row's
sheet has no team name yet, `name` is seeded to this same value as a
literal placeholder — `name == roster_team_id` is how a team's "still
unnamed" state is detected, rather than a separate boolean/NULL name.
`UNIQUE(cohort_id, roster_team_id)` (NULLs excluded per Postgres's usual
distinct-NULL behavior) keeps a re-imported sheet idempotent: the same
team_id in the same cohort always resolves back to the same row.

Two membership tables, deliberately different lifetimes: `TeamMember` is
the current roster (changes over time); a *consumer* like
`MissionAttemptMember` (`models/missions/mission.py`) is a frozen per-
attempt snapshot — a team changing later must never rewrite a past grade.
That snapshot pattern stays domain-specific (mission attempts have their
own grading semantics); only the team identity/roster itself is shared here.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, PrimaryKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Team(Base):
    __tablename__ = "learner_teams"
    __table_args__ = (
        # The real, enforced name-uniqueness constraint is a case-insensitive
        # expression index (`lower(name)`), added by migration
        # b4f1c8e30a72 — SQLAlchemy's declarative UniqueConstraint can't
        # express `lower(...)`, so it isn't declared here; this table has no
        # plain-column uniqueness on `name` at all anymore.
        UniqueConstraint("cohort_id", "roster_team_id", name="uq_learner_teams_cohort_roster_team_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    # See module docstring — the roster import's grouping key, distinct
    # from `name`. NULL for any team not created via that import.
    roster_team_id = Column(String(64), nullable=True)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Final-submission lock (2026-09) — a team-scoped checklist "done, for
    # real" action a team member triggers once every required team-scoped
    # item is done (services/competitions/team_management.py::
    # finalize_team_submission). NULL means "still editable" — a nullable
    # timestamp doubling as the boolean, same idiom as
    # LmsProgramItemProgress.completed_at, rather than a separate bool
    # column. Deliberately one-way from the team's side: only ops can clear
    # it (unlock_team_submission), mirroring MissionStepGate's
    # instructor-controlled-unlock posture — a team cannot re-lock/re-open
    # its own submission at will.
    final_locked_at = Column(DateTime(timezone=True), nullable=True)
    final_locked_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    first_locked_at = Column(DateTime(timezone=True), nullable=True)
    timing_adjustment_override = Column(Float, nullable=True)
    timing_adjustment_notes = Column(String(255), nullable=True)
    qualification = Column(String(50), nullable=True)


class TeamMember(Base):
    """The current roster. Membership changes freely — grading never reads
    this table directly, only a domain's own per-attempt/per-entry freeze
    (e.g. `MissionAttemptMember`)."""

    __tablename__ = "learner_team_members"
    __table_args__ = (
        PrimaryKeyConstraint("team_id", "user_id", name="pk_learner_team_members"),
    )

    team_id = Column(UUID(as_uuid=True), ForeignKey("learner_teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
