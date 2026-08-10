"""Mission teams (P6-1, Phase 2 Stage 6, 2026-08-11) — student teams for
team-policy missions. A separate table from `models/interns/team.py::Team`
on purpose: that table's `name` is globally UNIQUE (two cohorts could not
both have a "Team Alpha"), `epics.team_id` is NOT NULL, and `project_teams`
joins teams to projects — reusing it would need a filter added to every
existing intern query, and one missed filter is a silent cross-domain leak
(MISSIONS_REPORT.md Ch.2 idea 5, corrected per LMS_DESIGN_AUDIT.md Q-M3).

Two membership tables, deliberately different lifetimes: `MissionTeamMember`
is the current roster (changes over time); `MissionAttemptMember` (P6-2) is
a frozen snapshot of who was on the team for one specific attempt — a team
changing later must never rewrite a past grade.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, PrimaryKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class MissionTeam(Base):
    """A team of students attempting team-policy missions together.
    `cohort_id` is NULL for a self-formed team from the public catalog
    (MISSIONS_REPORT.md §Q5) — cohort-scoped teams are named uniquely per
    cohort (`UNIQUE(cohort_id, name)`), not globally, so two cohorts can
    both have a "Team Alpha"; self-formed teams (`cohort_id` NULL) aren't
    deduplicated by name at all — NULL never equals NULL in a unique
    constraint, and there's no natural scope to dedupe them against.
    """

    __tablename__ = "mission_teams"
    __table_args__ = (
        UniqueConstraint("cohort_id", "name", name="uq_mission_teams_cohort_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(80), nullable=False)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MissionTeamMember(Base):
    """The current roster. Membership changes freely — grading never reads
    this table directly, only `MissionAttemptMember`'s per-attempt freeze
    (P6-2, `models/missions/mission.py`)."""

    __tablename__ = "mission_team_members"
    __table_args__ = (
        PrimaryKeyConstraint("mission_team_id", "user_id", name="pk_mission_team_members"),
    )

    mission_team_id = Column(UUID(as_uuid=True), ForeignKey("mission_teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
