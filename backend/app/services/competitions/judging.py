"""Competition judging (2026-08-24) — rubric authoring, blind per-judge
scoring, the publish gate, the leaderboard, and the Top 20 export.

Blindness is enforced here, not by the schema: `submit_score` never reads
another judge's row, and nothing in this module (or the routers that call
it) returns one judge's `criterion_scores` to a different judge — only the
aggregate (`leaderboard`) is ever shared, and only once published.
"""

from __future__ import annotations

import logging
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
from app.services.competitions.timing_windows import resolve_team_timing

logger = logging.getLogger(__name__)


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
    """Standings for a cohort. Returns one row per team with final aggregated
    scores, timing adjustments (dynamic or overridden), and judge details."""
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort_id).order_by(Team.name))).scalars().all()
    advanced_to_by_name: dict[str, list[str]] = {}
    cohort = await db.scalar(select(Cohort).where(Cohort.id == cohort_id))
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
        select(CompetitionScore.team_id, CompetitionScore.judge_user_id, CompetitionScore.total_points, User.full_name, User.email)
        .outerjoin(User, User.id == CompetitionScore.judge_user_id)
        .where(CompetitionScore.cohort_id == cohort_id, CompetitionScore.submitted.is_(True))
        .order_by(User.full_name)
    )).all()
    judge_scores_by_team: dict[uuid.UUID, list[dict]] = {}
    team_normalized_percentages: dict[uuid.UUID, list[float]] = {}
    team_raw_points: dict[uuid.UUID, list[float]] = {}

    for team_id, judge_user_id, total_points, judge_name, judge_email in score_rows:
        try:
            pts = float(total_points) if total_points is not None else 0.0
        except (ValueError, TypeError):
            pts = 0.0

        safe_judge_name = (judge_name or "").strip() or "Judge"

        judge_scores_by_team.setdefault(team_id, []).append({
            "judge_user_id": judge_user_id,
            "judge_name": safe_judge_name,
            "total_points": pts,
        })
        team_raw_points.setdefault(team_id, []).append(pts)

        # Normalize each judge to their scale: Judge 1 = 110, Judge 2 = 95 (common 100% scale)
        email_str = (judge_email or "").lower()
        scale = 110.0 if "judge1" in email_str else (95.0 if "judge2" in email_str else (110.0 if pts > 100 else 100.0))
        pct = (pts / scale) * 100.0 if scale > 0 else 0.0
        team_normalized_percentages.setdefault(team_id, []).append(pct)

    out = []
    for team in teams:
        pts_list = team_raw_points.get(team.id, [])
        pct_list = team_normalized_percentages.get(team.id, [])
        count = len(pts_list)
        raw_judge_score = round(sum(pts_list) / count, 1) if count > 0 else None
        avg_pct = round(sum(pct_list) / count, 1) if count > 0 else None

        timing_info = resolve_team_timing(cohort, team)
        try:
            timing_pts = float(timing_info.get("points") or 0.0)
        except (ValueError, TypeError):
            timing_pts = 0.0
        final_score = round(raw_judge_score + timing_pts, 1) if raw_judge_score is not None else None

        out.append({
            "team_id": team.id,
            "team_name": team.name,
            "score": final_score,
            "raw_judge_score": raw_judge_score,
            "score_percent": avg_pct,
            "qualification": getattr(team, "qualification", None),
            "judges_scored": count,
            "status": "unscored" if count == 0 else "scored",
            "judge_scores": judge_scores_by_team.get(team.id, []),
            "advanced_to": ", ".join(advanced_to_by_name.get(team.name, [])) or None,
            "timing_adjustment": timing_pts,
            "timing_badge": timing_info.get("badge"),
            "timing_tier_name": timing_info.get("tier_name"),
            "is_timing_override": bool(timing_info.get("is_override")),
            "timing_override_notes": timing_info.get("override_notes"),
            "final_locked_at": getattr(team, "final_locked_at", None),
            "first_locked_at": getattr(team, "first_locked_at", None),
        })

    # Sort: scored teams first. Official TOP 10 qualifiers occupy the top 10 ranks.
    # Within each tier, ranked by combined normalized percentage.
    out.sort(key=lambda r: (
        r["score"] is None,
        0 if r.get("qualification") == "TOP 10" else 1,
        -(r["score_percent"] or 0),
        -(r["score"] or 0),
    ))
    for i, row in enumerate(out, start=1):
        row["rank"] = i
    return out


async def get_team_score_breakdown(
    db: AsyncSession, *, cohort_id: uuid.UUID, team_id: uuid.UUID
) -> dict:
    """Returns the full judge evaluation breakdown for a single team.
    Includes criteria scores, criteria comments, and judge notes."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    team = await db.get(Team, team_id)
    if team is None or team.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found in this cohort")

    rubric_tuple = await get_rubric(db, program_id=cohort.program_id)
    rubric_criteria = rubric_tuple[1] if rubric_tuple else []

    score_rows = (await db.execute(
        select(CompetitionScore, User)
        .join(User, User.id == CompetitionScore.judge_user_id)
        .where(
            CompetitionScore.cohort_id == cohort_id,
            CompetitionScore.team_id == team_id,
            CompetitionScore.submitted.is_(True),
        )
        .order_by(User.full_name)
    )).all()

    judge_evaluations = []
    judge_totals = []
    for comp_score, judge_user in score_rows:
        judge_totals.append(comp_score.total_points)
        crit_items = []
        crit_scores = comp_score.criterion_scores or {}
        crit_comments = comp_score.criterion_comments or {}

        if rubric_criteria:
            for c in rubric_criteria:
                crit_items.append({
                    "key": c.key,
                    "label": c.label,
                    "max_points": c.max_points,
                    "awarded_points": crit_scores.get(c.key),
                    "comment": crit_comments.get(c.key),
                })
        else:
            for k, pts in crit_scores.items():
                crit_items.append({
                    "key": k,
                    "label": k,
                    "max_points": 0,
                    "awarded_points": pts,
                    "comment": crit_comments.get(k),
                })

        judge_evaluations.append({
            "judge_user_id": judge_user.id,
            "judge_name": judge_user.full_name or judge_user.email,
            "judge_email": judge_user.email,
            "submitted_at": comp_score.submitted_at,
            "total_points": comp_score.total_points,
            "bonus_points": comp_score.bonus_points or 0.0,
            "timing_adjustment": comp_score.timing_adjustment or 0.0,
            "notes": comp_score.notes,
            "criteria": crit_items,
        })

    timing_info = resolve_team_timing(cohort, team)
    raw_judge_score = round(sum(judge_totals) / len(judge_totals), 1) if judge_totals else None
    final_score = round(raw_judge_score + timing_info["points"], 1) if raw_judge_score is not None else None

    return {
        "team_id": team.id,
        "team_name": team.name,
        "cohort_id": cohort_id,
        "status": "scored" if judge_totals else "unscored",
        "qualification": team.qualification,
        "raw_judge_score": raw_judge_score,
        "final_score": final_score,
        "score_percent": round(100 * (final_score / 110), 1) if final_score is not None else None,
        "timing_adjustment": timing_info["points"],
        "timing_badge": timing_info["badge"],
        "is_timing_override": timing_info["is_override"],
        "timing_override_notes": timing_info["override_notes"],
        "final_locked_at": team.final_locked_at,
        "first_locked_at": team.first_locked_at,
        "judges": judge_evaluations,
    }


async def get_student_team_result(
    db: AsyncSession, *, cohort_id: uuid.UUID, user_id: uuid.UUID,
) -> dict:
    """Student result view -- strictly their own team's result once published.
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

    cohort = await db.get(Cohort, cohort_id)
    timing_info = resolve_team_timing(cohort, team)
    try:
        timing_pts = float(timing_info.get("points") or 0.0)
    except (ValueError, TypeError):
        timing_pts = 0.0

    published = await is_published(db, cohort_id=cohort_id)
    if not published:
        return {
            "team_id": team.id,
            "team_name": team.name,
            "status": "pending_publication",
            "final_score": None,
            "score_percent": None,
            "qualification": None,
            "locked": getattr(team, "final_locked_at", None) is not None,
            "locked_at": getattr(team, "final_locked_at", None),
            "published": False,
            "timing_adjustment": timing_pts,
            "timing_badge": timing_info.get("badge"),
        }

    agg = (await db.execute(
        select(func.avg(CompetitionScore.total_points), func.count(CompetitionScore.id))
        .where(CompetitionScore.team_id == team.id, CompetitionScore.submitted.is_(True))
    )).first()

    avg_score = float(agg[0]) if agg and agg[0] is not None else None
    scored_count = agg[1] if agg else 0
    final_score = round(avg_score + timing_pts, 1) if avg_score is not None else None
    score_percent = round(100 * (final_score / 110), 1) if final_score is not None else None

    return {
        "team_id": team.id,
        "team_name": team.name,
        "status": "scored" if scored_count > 0 else "unscored",
        "final_score": final_score,
        "score_percent": score_percent,
        "qualification": getattr(team, "qualification", None),
        "locked": getattr(team, "final_locked_at", None) is not None,
        "locked_at": getattr(team, "final_locked_at", None),
        "published": True,
        "timing_adjustment": timing_pts,
        "timing_badge": timing_info.get("badge"),
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
