"""Competition judging models (2026-08-24). See package docstring."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class CompetitionRubric(Base):
    """A competition's scoring rubric — program-scoped, not cohort-scoped,
    so the same criteria carry across a competition's stages unless a
    future need splits them. Ru'ya's is the PDF's 8 criteria + a bonus,
    105 pts total, authored by ops rather than hardcoded."""

    __tablename__ = "competition_rubrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CompetitionRubricCriterion(Base):
    __tablename__ = "competition_rubric_criteria"
    __table_args__ = (
        UniqueConstraint("rubric_id", "key", name="uq_competition_rubric_criteria_rubric_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rubric_id = Column(UUID(as_uuid=True), ForeignKey("competition_rubrics.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(64), nullable=False)
    label = Column(String(255), nullable=False)
    max_points = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)


class CompetitionScore(Base):
    """One judge's score for one team, for one cohort (stage) — a judge
    revises their own row by upsert until the cohort is published
    (`services/competitions/judging.py::submit_score`); never merged or
    averaged at write time, only at read time (`leaderboard()`), so every
    individual judge's numbers stay intact and re-computable.

    `submitted` (2026-08-27) separates the autosaved draft every keystroke
    writes from the judge's own deliberate "done with this team" — a row
    can exist and keep being overwritten by autosave with `submitted`
    still False; only an explicit submit flips it, and it only ratchets
    forward (`submit_score` never clears it back to False), so a team
    already marked scored can't be un-scored by the judge going back to
    tweak a number. `already_scored`/`leaderboard`/`judges_scored` all
    read this flag, not mere row existence, so an in-progress draft never
    counts toward standings.

    Blindness (a judge never sees another judge's score, even after
    publish — only the aggregate) is enforced by which endpoints expose
    this table, not by anything in its own shape."""

    __tablename__ = "competition_scores"
    __table_args__ = (
        UniqueConstraint(
            "rubric_id", "team_id", "judge_user_id", "cohort_id",
            name="uq_competition_scores_rubric_team_judge_cohort",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rubric_id = Column(UUID(as_uuid=True), ForeignKey("competition_rubrics.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("learner_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    judge_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    # {criterion_key: points} — validated against the rubric's own criteria
    # at write time in the service layer, not by a DB constraint.
    criterion_scores = Column(JSONB, nullable=False)
    bonus_points = Column(Integer, nullable=False, default=0)
    total_points = Column(Integer, nullable=False)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    submitted = Column(Boolean, nullable=False, default=False, server_default="false")


class CompetitionResultPublication(Base):
    """The blind-until-published gate for one cohort (stage). Row exists =
    published; delete it to unpublish. `unique=True` on `cohort_id` is the
    whole mechanism — a second publish call is just re-reading this row,
    not a second row."""

    __tablename__ = "competition_result_publications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, unique=True)
    published_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CompetitionJudge(Base):
    """A judge's cohort assignment — exact shape of `SessionInstructor`
    (`app/models/sessions/session.py`), same reasoning: a judge assigned to
    the Qualifier cohort has no row for Finalists and can't see it, and
    "assign to the whole competition" is a bulk ops action that writes one
    of these per cohort, not a separate data concept."""

    __tablename__ = "competition_judges"
    __table_args__ = (
        UniqueConstraint("cohort_id", "user_id", name="uq_competition_judges_cohort_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
