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
(`UNIQUE(cohort_id, name)`), not globally, so two cohorts can both have a
"Team Alpha"; self-formed teams (`cohort_id` NULL) aren't deduplicated by
name at all — NULL never equals NULL in a unique constraint.

Two membership tables, deliberately different lifetimes: `TeamMember` is
the current roster (changes over time); a *consumer* like
`MissionAttemptMember` (`models/missions/mission.py`) is a frozen per-
attempt snapshot — a team changing later must never rewrite a past grade.
That snapshot pattern stays domain-specific (mission attempts have their
own grading semantics); only the team identity/roster itself is shared here.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, PrimaryKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Team(Base):
    __tablename__ = "learner_teams"
    __table_args__ = (
        UniqueConstraint("cohort_id", "name", name="uq_learner_teams_cohort_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(80), nullable=False)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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
