"""Competition judging (2026-08-24) — rubric authoring, blind per-judge
scoring, the publish gate, the leaderboard, and the Top 20 export.

Blindness is enforced here, not by the schema: `submit_score` never reads
another judge's row, and nothing in this module (or the routers that call
it) returns one judge's `criterion_scores` to a different judge — only the
aggregate (`leaderboard`) is ever shared, and only once published.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitions.judging import (
    CompetitionJudge, CompetitionResultPublication, CompetitionRubric, CompetitionRubricCriterion,
    CompetitionScore,
)
from app.models.sessions.cohort import Cohort
from app.models.team import Team
from app.models.user import User


# ── Rubric ───────────────────────────────────────────────────────────────

async def get_rubric(db: AsyncSession, *, program_id: uuid.UUID) -> tuple[CompetitionRubric, list[CompetitionRubricCriterion]] | None:
    rubric = await db.scalar(select(CompetitionRubric).where(CompetitionRubric.program_id == program_id))
    if rubric is None:
        return None
    criteria = (await db.execute(
        select(CompetitionRubricCriterion)
        .where(CompetitionRubricCriterion.rubric_id == rubric.id)
        .order_by(CompetitionRubricCriterion.position)
    )).scalars().all()
    return rubric, list(criteria)


async def upsert_rubric(
    db: AsyncSession, *, program_id: uuid.UUID, name: str,
    criteria: list[dict],
) -> tuple[CompetitionRubric, list[CompetitionRubricCriterion]]:
    """Declarative sync, not append-only: `criteria` is the full intended
    list (same "one call rewrites everything" idiom
    `LmsProgramItemReorderIn`/`reorder_program_items` already use for
    checklist positions) — a criterion whose `key` isn't in the list gets
    deleted, one whose `key` is already there gets updated in place, a new
    `key` gets inserted. Existing `competition_scores` rows referencing a
    deleted criterion's key simply stop being read for it; not retroactively
    rewritten, same "a later edit doesn't rewrite history" instinct
    `services/lms/program.py` uses for checklist items."""
    rubric = await db.scalar(select(CompetitionRubric).where(CompetitionRubric.program_id == program_id))
    if rubric is None:
        rubric = CompetitionRubric(id=uuid.uuid4(), program_id=program_id, name=name)
        db.add(rubric)
        await db.flush()
    else:
        rubric.name = name

    existing = {
        c.key: c for c in (await db.execute(
            select(CompetitionRubricCriterion).where(CompetitionRubricCriterion.rubric_id == rubric.id)
        )).scalars().all()
    }
    kept_keys = set()
    for position, item in enumerate(criteria):
        key = item["key"]
        kept_keys.add(key)
        row = existing.get(key)
        if row is None:
            db.add(CompetitionRubricCriterion(
                id=uuid.uuid4(), rubric_id=rubric.id, key=key,
                label=item["label"], max_points=item["max_points"], position=position,
            ))
        else:
            row.label = item["label"]
            row.max_points = item["max_points"]
            row.position = position
    for key, row in existing.items():
        if key not in kept_keys:
            await db.delete(row)

    await db.flush()
    result = await get_rubric(db, program_id=program_id)
    assert result is not None
    return result


# ── Scoring ──────────────────────────────────────────────────────────────

async def is_published(db: AsyncSession, *, cohort_id: uuid.UUID) -> bool:
    return await db.scalar(
        select(CompetitionResultPublication.id).where(CompetitionResultPublication.cohort_id == cohort_id)
    ) is not None


async def get_publication(db: AsyncSession, *, cohort_id: uuid.UUID) -> CompetitionResultPublication | None:
    """The current publish state on page load — `publish`/`unpublish` only
    ever return it as a side effect of the action just taken, so the
    Results tab had no way to show what's actually true before you click
    anything."""
    return await db.scalar(
        select(CompetitionResultPublication).where(CompetitionResultPublication.cohort_id == cohort_id)
    )


async def get_own_score(
    db: AsyncSession, *, rubric_id: uuid.UUID, team_id: uuid.UUID, judge_user_id: uuid.UUID, cohort_id: uuid.UUID,
) -> CompetitionScore | None:
    return await db.scalar(
        select(CompetitionScore).where(
            CompetitionScore.rubric_id == rubric_id, CompetitionScore.team_id == team_id,
            CompetitionScore.judge_user_id == judge_user_id, CompetitionScore.cohort_id == cohort_id,
        )
    )


async def submit_score(
    db: AsyncSession, *, rubric: CompetitionRubric, criteria: list[CompetitionRubricCriterion],
    team_id: uuid.UUID, judge_user_id: uuid.UUID, cohort_id: uuid.UUID,
    criterion_scores: dict[str, float],
    criterion_comments: dict[str, str] | None = None,
    bonus_points: float = 0.0,
    timing_adjustment: float = 0.0,
    total_points: float | None = None,
    notes: str | None = None,
    submitted: bool = False,
) -> CompetitionScore:
    if await is_published(db, cohort_id=cohort_id):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Results are published — scoring is closed for this stage")

    if bonus_points < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bonus can't be negative")

    by_key = {c.key: c for c in criteria}
    if total_points is None:
        if set(criterion_scores) != set(by_key):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Score every rubric criterion, and only rubric criteria")
        for key, points in criterion_scores.items():
            if not (0 <= points <= by_key[key].max_points):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"'{by_key[key].label}' must be between 0 and {by_key[key].max_points}",
                )
        total = float(sum(criterion_scores.values()) + bonus_points + timing_adjustment)
    else:
        for key, points in criterion_scores.items():
            if key in by_key and not (0 <= points <= by_key[key].max_points):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"'{by_key[key].label}' must be between 0 and {by_key[key].max_points}",
                )
        total = float(total_points)

    score = await get_own_score(db, rubric_id=rubric.id, team_id=team_id, judge_user_id=judge_user_id, cohort_id=cohort_id)
    if score is None:
        score = CompetitionScore(
            id=uuid.uuid4(), rubric_id=rubric.id, team_id=team_id, judge_user_id=judge_user_id, cohort_id=cohort_id,
            criterion_scores=criterion_scores,
            criterion_comments=criterion_comments or {},
            bonus_points=bonus_points,
            timing_adjustment=timing_adjustment,
            total_points=total,
            notes=notes,
            submitted=submitted,
        )
        db.add(score)
    else:
        score.criterion_scores = criterion_scores
        score.criterion_comments = criterion_comments or {}
        score.bonus_points = bonus_points
        score.timing_adjustment = timing_adjustment
        score.total_points = total
        score.notes = notes
        score.submitted_at = datetime.now(timezone.utc)
        # Ratchet-only: an autosaved draft (submitted=False) never clears a
        # team that's already been deliberately submitted.
        score.submitted = score.submitted or submitted
    await db.flush()
    return score


async def scored_team_ids(db: AsyncSession, *, judge_user_id: uuid.UUID, cohort_id: uuid.UUID) -> set[uuid.UUID]:
    """Which teams this specific judge has *deliberately submitted* a score
    for in this cohort — the judge roster's done/pending mark. Filters on
    `submitted`, not mere row existence, so a team with only an autosaved
    draft still reads as pending. Deliberately not rubric-scoped: a cohort
    has exactly one rubric in practice (`get_rubric` is program-scoped),
    so "scored in this cohort at all" is the same question as "scored
    against the current rubric"."""
    rows = (await db.execute(
        select(CompetitionScore.team_id).where(
            CompetitionScore.judge_user_id == judge_user_id, CompetitionScore.cohort_id == cohort_id,
            CompetitionScore.submitted.is_(True),
        )
    )).scalars().all()
    return set(rows)


# ── Judges roster with progress (ops "Judges" tab) ──────────────────────

async def list_judges_with_progress(db: AsyncSession, *, cohort_id: uuid.UUID) -> list[dict]:
    team_count = await db.scalar(select(func.count(Team.id)).where(Team.cohort_id == cohort_id)) or 0
    judges = (await db.execute(
        select(User, CompetitionJudge.onboarding_sent_at).join(CompetitionJudge, CompetitionJudge.user_id == User.id)
        .where(CompetitionJudge.cohort_id == cohort_id).order_by(User.full_name)
    )).all()
    scored_counts = dict((await db.execute(
        select(CompetitionScore.judge_user_id, func.count(CompetitionScore.id))
        .where(CompetitionScore.cohort_id == cohort_id, CompetitionScore.submitted.is_(True))
        .group_by(CompetitionScore.judge_user_id)
    )).all())
    return [
        {"user_id": j.id, "full_name": j.full_name, "email": j.email,
         "scored_count": scored_counts.get(j.id, 0), "team_count": team_count,
         "onboarding_sent": onboarding_sent_at is not None}
        for j, onboarding_sent_at in judges
    ]


# ── Leaderboard, publish, export ────────────────────────────────────────

async def leaderboard(db: AsyncSession, *, cohort_id: uuid.UUID) -> list[dict]:
    """Every team in this cohort, ranked by the average of every judge's
    `total_points` — `None` (last, `status="unscored"`) for a team no judge
    has scored yet. Only counts `submitted=True` rows, so a judge's
    in-progress autosaved draft never moves the standings. Carries each
    individual judge's own score too (`judge_scores`) — ops reviewing a
    result needs to see who scored what, not just the blended average a
    judge themselves is blind to (see the model's own blindness note).
    Also carries `advanced_to` — there's no stored "this team advanced"
    flag (`advance_teams` is itself just idempotent re-resolution by
    name), so this is inferred for display: a same-named team in a
    sibling cohort under the same program, created *after* this one
    (`created_at`, a proxy for which stage is later since there's no
    explicit phase-order field) — so a Finalists team doesn't turn
    around and read as having "advanced to" its own Qualifier stage."""
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort_id))).scalars().all()

    cohort = await db.get(Cohort, cohort_id)
    advanced_to_by_name: dict[str, list[str]] = {}
    if cohort is not None:
        siblings = (await db.execute(
            select(Cohort).where(
                Cohort.program_id == cohort.program_id, Cohort.id != cohort_id,
                Cohort.created_at > cohort.created_at,
            )
        )).scalars().all()
        if siblings:
            sibling_names = {c.id: c.name for c in siblings}
            sibling_teams = (await db.execute(
                select(Team.cohort_id, Team.name).where(Team.cohort_id.in_(sibling_names))
            )).all()
            for sib_cohort_id, name in sibling_teams:
                advanced_to_by_name.setdefault(name, []).append(sibling_names[sib_cohort_id])
    agg_rows = (await db.execute(
        select(CompetitionScore.team_id, func.avg(CompetitionScore.total_points), func.count(CompetitionScore.id))
        .where(CompetitionScore.cohort_id == cohort_id, CompetitionScore.submitted.is_(True))
        .group_by(CompetitionScore.team_id)
    )).all()
    by_team = {team_id: (float(avg), count) for team_id, avg, count in agg_rows}

    score_rows = (await db.execute(
        select(CompetitionScore.team_id, CompetitionScore.judge_user_id, CompetitionScore.total_points, User.full_name)
        .join(User, User.id == CompetitionScore.judge_user_id)
        .where(CompetitionScore.cohort_id == cohort_id, CompetitionScore.submitted.is_(True))
        .order_by(User.full_name)
    )).all()
    judge_scores_by_team: dict[uuid.UUID, list[dict]] = {}
    for team_id, judge_user_id, total_points, judge_name in score_rows:
        judge_scores_by_team.setdefault(team_id, []).append({
            "judge_user_id": judge_user_id, "judge_name": judge_name, "total_points": total_points,
        })

    out = []
    for team in teams:
        avg, count = by_team.get(team.id, (None, 0))
        pct = round(100 * (avg / 110), 1) if avg is not None else None
        out.append({
            "team_id": team.id, "team_name": team.name,
            "score": round(avg, 1) if avg is not None else None,
            "score_percent": pct,
            "qualification": team.qualification,
            "judges_scored": count,
            "status": "unscored" if count == 0 else "scored",
            "judge_scores": judge_scores_by_team.get(team.id, []),
            "advanced_to": ", ".join(advanced_to_by_name.get(team.name, [])) or None,
        })
    out.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    for i, row in enumerate(out, start=1):
        row["rank"] = i
    return out


async def get_student_team_result(
    db: AsyncSession, *, cohort_id: uuid.UUID, user_id: uuid.UUID,
) -> dict:
    """Student result view — strictly their own team's result once published.
    Never exposes individual judge scores, judge identities, or other teams.
    """
    from app.models.team import TeamMember
    team = await db.scalar(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(Team.cohort_id == cohort_id, TeamMember.user_id == user_id)
    )
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="You are not in a team for this cohort")

    published = await is_published(db, cohort_id=cohort_id)
    if not published:
        return {
            "team_id": team.id,
            "team_name": team.name,
            "status": "pending_publication",
            "final_score": None,
            "score_percent": None,
            "qualification": None,
            "locked": team.final_locked_at is not None,
            "locked_at": team.final_locked_at,
            "published": False,
        }

    agg = (await db.execute(
        select(func.avg(CompetitionScore.total_points), func.count(CompetitionScore.id))
        .where(CompetitionScore.team_id == team.id, CompetitionScore.submitted.is_(True))
    )).first()

    avg_score = float(agg[0]) if agg and agg[0] is not None else None
    scored_count = agg[1] if agg else 0
    score_percent = round(100 * (avg_score / 110), 1) if avg_score is not None else None

    return {
        "team_id": team.id,
        "team_name": team.name,
        "status": "scored" if scored_count > 0 else "unscored",
        "final_score": round(avg_score, 1) if avg_score is not None else None,
        "score_percent": score_percent,
        "qualification": team.qualification,
        "locked": team.final_locked_at is not None,
        "locked_at": team.final_locked_at,
        "published": True,
    }


async def publish(db: AsyncSession, *, cohort_id: uuid.UUID, actor_user_id: uuid.UUID) -> CompetitionResultPublication:
    existing = await db.scalar(
        select(CompetitionResultPublication).where(CompetitionResultPublication.cohort_id == cohort_id)
    )
    if existing is not None:
        return existing
    row = CompetitionResultPublication(id=uuid.uuid4(), cohort_id=cohort_id, published_by=actor_user_id)
    db.add(row)
    await db.flush()
    return row


async def unpublish(db: AsyncSession, *, cohort_id: uuid.UUID) -> bool:
    existing = await db.scalar(
        select(CompetitionResultPublication).where(CompetitionResultPublication.cohort_id == cohort_id)
    )
    if existing is None:
        return False
    await db.delete(existing)
    await db.flush()
    return True


async def export_top(db: AsyncSession, *, cohort_id: uuid.UUID, limit: int = 20) -> list[dict]:
    board = await leaderboard(db, cohort_id=cohort_id)
    return board[:limit]
