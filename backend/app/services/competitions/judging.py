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

def _leaf_key(parent_key: str, sub_key: str) -> str:
    """Storage key for one sub-criterion score, e.g. `mission.clarity`.
    Dotted so a leaf can never collide with a parent criterion key."""
    return f"{parent_key}.{sub_key}"


def _ops_parent_total(ops_criteria: list, ops_scores: dict) -> float:
    """Parent-level operations total. The stored dict carries both leaf
    (`mission.clarity`) and recomputed parent (`mission`) keys, so a naive
    sum would double-count — only parent keys contribute. Falls back to
    summing leaves when a parent key is absent (rows predating the
    parent-sum change)."""
    total = 0.0
    for c in ops_criteria:
        own = ops_scores.get(c.key)
        if isinstance(own, (int, float)):
            total += float(own)
            continue
        leaves = [ops_scores.get(_leaf_key(c.key, s["key"])) for s in _criterion_subs(c)]
        if leaves and all(isinstance(v, (int, float)) for v in leaves):
            total += float(sum(leaves))
    return total


def _criterion_subs(criterion) -> list[dict]:
    subs = getattr(criterion, "sub_criteria", None) or []
    return list(subs)


def _validate_sub_criteria(label: str, max_points: int, subs: list[dict]) -> list[dict]:
    """Normalizes + validates one criterion's sub-criteria: non-empty keys /
    labels, non-negative maxima, unique sub-keys, and the load-bearing rule —
    the sub maxima must sum exactly to the parent's own max_points, otherwise
    the parent total could never reach (or could exceed) its headline."""
    if not subs:
        return []
    seen: set[str] = set()
    total = 0
    for position, sub in enumerate(subs):
        s_key = (sub.get("key") or "").strip()
        s_label = (sub.get("label") or "").strip()
        try:
            s_max = int(sub.get("max_points", 0))
        except (TypeError, ValueError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"'{label}' has a sub-criterion with an invalid max_points")
        if not s_key or not s_label:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"'{label}' has a sub-criterion missing its key or label")
        if s_key in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"'{label}' repeats the sub-criterion key '{s_key}'")
        if s_max < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"'{s_label}' can't have negative max_points")
        seen.add(s_key)
        total += s_max
    if total != max_points:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"'{label}' is worth {max_points} pts but its sub-criteria sum to {total} pts — they must match",
        )
    return [
        {"key": s["key"].strip(), "label": s["label"].strip(), "max_points": int(s["max_points"]), "position": i}
        for i, s in enumerate(subs)
    ]

async def get_rubric(
    db: AsyncSession, *, cohort_id: uuid.UUID | None = None, program_id: uuid.UUID | None = None
) -> tuple[CompetitionRubric, list[CompetitionRubricCriterion]] | None:
    rubric = None
    if cohort_id is not None:
        rubric = await db.scalar(select(CompetitionRubric).where(CompetitionRubric.cohort_id == cohort_id))
        if rubric is None:
            cohort = await db.get(Cohort, cohort_id)
            if cohort is not None:
                program_id = cohort.program_id

    if rubric is None and program_id is not None:
        rubric = await db.scalar(
            select(CompetitionRubric)
            .where(CompetitionRubric.program_id == program_id, CompetitionRubric.cohort_id.is_(None))
        )
        if rubric is None:
            rubric = await db.scalar(
                select(CompetitionRubric)
                .where(CompetitionRubric.program_id == program_id)
                .order_by(CompetitionRubric.created_at)
            )

    if rubric is None:
        return None
    criteria = (await db.execute(
        select(CompetitionRubricCriterion)
        .where(CompetitionRubricCriterion.rubric_id == rubric.id)
        .order_by(CompetitionRubricCriterion.position)
    )).scalars().all()
    return rubric, list(criteria)


async def upsert_rubric(
    db: AsyncSession, *, cohort_id: uuid.UUID | None = None, program_id: uuid.UUID | None = None,
    name: str, criteria: list[dict],
) -> tuple[CompetitionRubric, list[CompetitionRubricCriterion]]:
    """Declarative sync, scoped by cohort (or fallback program):
    `criteria` is the full intended list. Existing `competition_scores`
    rows referencing deleted criterion keys simply stop being read for them."""
    rubric = None
    if cohort_id is not None:
        cohort = await db.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
        program_id = cohort.program_id
        rubric = await db.scalar(select(CompetitionRubric).where(CompetitionRubric.cohort_id == cohort_id))
        if rubric is None:
            rubric = CompetitionRubric(id=uuid.uuid4(), program_id=program_id, cohort_id=cohort_id, name=name)
            db.add(rubric)
            await db.flush()
        else:
            rubric.name = name
    elif program_id is not None:
        rubric = await db.scalar(
            select(CompetitionRubric)
            .where(CompetitionRubric.program_id == program_id, CompetitionRubric.cohort_id.is_(None))
        )
        if rubric is None:
            rubric = await db.scalar(select(CompetitionRubric).where(CompetitionRubric.program_id == program_id))
        if rubric is None:
            rubric = CompetitionRubric(id=uuid.uuid4(), program_id=program_id, name=name)
            db.add(rubric)
            await db.flush()
        else:
            rubric.name = name
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Either cohort_id or program_id must be provided")

    existing = {
        c.key: c for c in (await db.execute(
            select(CompetitionRubricCriterion).where(CompetitionRubricCriterion.rubric_id == rubric.id)
        )).scalars().all()
    }
    kept_keys = set()
    for position, item in enumerate(criteria):
        key = item["key"]
        kept_keys.add(key)
        subs = _validate_sub_criteria(
            item["label"], item["max_points"], item.get("sub_criteria") or [],
        )
        row = existing.get(key)
        if row is None:
            db.add(CompetitionRubricCriterion(
                id=uuid.uuid4(), rubric_id=rubric.id, key=key,
                label=item["label"], max_points=item["max_points"], position=position,
                scored_by=item.get("scored_by", "judge"),
                sub_criteria=subs,
            ))
        else:
            row.label = item["label"]
            row.max_points = item["max_points"]
            row.position = position
            row.scored_by = item.get("scored_by", "judge")
            row.sub_criteria = subs
    for key, row in existing.items():
        if key not in kept_keys:
            await db.delete(row)

    await db.flush()
    result = await get_rubric(db, cohort_id=cohort_id, program_id=program_id)
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

    # Only judge-graded criteria are within scope for this function.
    # Operations criteria are stored separately on the team row.
    judge_criteria = [c for c in criteria if getattr(c, "scored_by", "judge") == "judge"]
    # Expected leaf keys: a flat criterion is its own leaf; a parent with
    # sub-criteria is scored through its leaves (`mission.clarity`, …) and
    # the parent total is recomputed server-side — never accepted from the
    # client. Comments stay per parent (criterion_comments keys are parent
    # keys), bonus_points is untouched.
    leaf_max: dict[str, int] = {}
    leaf_label: dict[str, str] = {}
    parent_of_leaf: dict[str, str] = {}
    for c in judge_criteria:
        subs = _criterion_subs(c)
        if subs:
            for s in subs:
                lk = _leaf_key(c.key, s["key"])
                leaf_max[lk] = int(s["max_points"])
                leaf_label[lk] = s["label"]
                parent_of_leaf[lk] = c.key
        else:
            leaf_max[c.key] = c.max_points
            leaf_label[c.key] = c.label
            parent_of_leaf[c.key] = c.key
    by_key = {c.key: c for c in judge_criteria}
    if total_points is None:
        if set(criterion_scores) != set(leaf_max):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Score every judge criterion, and only judge criteria")
        for key, points in criterion_scores.items():
            if not (0 <= points <= leaf_max[key]):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"'{leaf_label[key]}' must be between 0 and {leaf_max[key]}",
                )
        # Recompute every parent total from its leaves and store both: the
        # leaves (for the breakdown's sub rows) and the parent key (so all
        # downstream math keeps reading parent-level numbers, unchanged).
        stored_scores: dict[str, float] = dict(criterion_scores)
        parent_totals: dict[str, float] = {}
        for key, points in criterion_scores.items():
            parent_totals[parent_of_leaf[key]] = parent_totals.get(parent_of_leaf[key], 0.0) + float(points)
        stored_scores.update(parent_totals)
        criterion_scores = stored_scores
        total = float(sum(parent_totals.values()) + bonus_points + timing_adjustment)
    else:
        for key, points in criterion_scores.items():
            if key in leaf_max and not (0 <= points <= leaf_max[key]):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"'{leaf_label[key]}' must be between 0 and {leaf_max[key]}",
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
    scores, timing adjustments (dynamic or overridden), and judge details.

    Observer mode (2026-10): `is_observer=True` test teams never appear on
    official leaderboards — same partition as the judge queue and certs."""
    teams = (await db.execute(
        select(Team).where(Team.cohort_id == cohort_id, Team.is_observer.is_(False)).order_by(Team.name)
    )).scalars().all()
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

    # Compute ops_max_points from the rubric's operations criteria once
    rubric_tuple = await get_rubric(db, cohort_id=cohort.id) if cohort else None
    ops_criteria = [c for c in (rubric_tuple[1] if rubric_tuple else []) if getattr(c, "scored_by", "judge") == "operations"]
    ops_max_total = float(sum(c.max_points for c in ops_criteria))

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

        # Ops score: parent-level sum of the operations criterion scores
        # stored on the team (see _ops_parent_total — never a naive sum,
        # which would double-count leaves alongside their parent total).
        ops_scores: dict = getattr(team, "ops_criterion_scores", None) or {}
        ops_pts = _ops_parent_total(ops_criteria, ops_scores)
        ops_scored = bool(ops_scores)

        judge_base = raw_judge_score if raw_judge_score is not None else 0.0
        if raw_judge_score is not None or ops_scored:
            final_score = round(judge_base + ops_pts + timing_pts, 1)
        else:
            final_score = None

        out.append({
            "team_id": team.id,
            "team_name": team.name,
            "score": final_score,
            "raw_judge_score": raw_judge_score,
            "score_percent": avg_pct,
            "qualification": getattr(team, "qualification", None),
            "judges_scored": count,
            "status": "unscored" if (count == 0 and not ops_scored) else "scored",
            "judge_scores": judge_scores_by_team.get(team.id, []),
            "advanced_to": ", ".join(advanced_to_by_name.get(team.name, [])) or None,
            "timing_adjustment": timing_pts,
            "timing_badge": timing_info.get("badge"),
            "timing_tier_name": timing_info.get("tier_name"),
            "is_timing_override": bool(timing_info.get("is_override")),
            "timing_override_notes": timing_info.get("override_notes"),
            "final_locked_at": getattr(team, "final_locked_at", None),
            "first_locked_at": getattr(team, "first_locked_at", None),
            "ops_score": round(ops_pts, 1) if ops_scored else None,
            "ops_max_points": ops_max_total if ops_criteria else None,
            "ops_criterion_scores": ops_scores,
            "ops_criterion_notes": getattr(team, "ops_criterion_notes", None),
        })

    # Sort: ranked by final total, highest first. Unscored teams sort
    # last. (Previously this sorted by normalized percentage, which could
    # rank a lower total above a higher one.)
    out.sort(key=lambda r: (
        r["score"] is None,
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

    rubric_tuple = await get_rubric(db, cohort_id=cohort_id)
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
                subs = _criterion_subs(c)
                awarded = crit_scores.get(c.key)
                if awarded is None and subs:
                    # Rows stored before the parent-sum change (or hand-built)
                    # may carry only leaves — derive the parent for display.
                    leaf_vals = [crit_scores.get(_leaf_key(c.key, s["key"])) for s in subs]
                    if all(isinstance(v, (int, float)) for v in leaf_vals):
                        awarded = float(sum(leaf_vals))
                crit_items.append({
                    "key": c.key,
                    "label": c.label,
                    "max_points": c.max_points,
                    "awarded_points": awarded,
                    "comment": crit_comments.get(c.key),
                    "subs": [
                        {
                            "key": s["key"],
                            "label": s["label"],
                            "max_points": int(s["max_points"]),
                            "awarded_points": crit_scores.get(_leaf_key(c.key, s["key"])),
                        }
                        for s in subs
                    ],
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

    ops_scores: dict = getattr(team, "ops_criterion_scores", None) or {}
    ops_criteria = [c for c in rubric_criteria if getattr(c, "scored_by", "judge") == "operations"]
    ops_pts = _ops_parent_total(ops_criteria, ops_scores)
    ops_max_total = float(sum(c.max_points for c in ops_criteria))

    judge_base = raw_judge_score if raw_judge_score is not None else 0.0
    if raw_judge_score is not None or bool(ops_scores):
        final_score = round(judge_base + ops_pts + timing_info["points"], 1)
    else:
        final_score = None

    # Labeled operations rows for the inspector — same shape as one judge's
    # criteria rows, so the UI renders both identically.
    ops_breakdown = []
    for c in ops_criteria:
        subs = _criterion_subs(c)
        awarded = ops_scores.get(c.key)
        if awarded is None and subs:
            leaf_vals = [ops_scores.get(_leaf_key(c.key, s["key"])) for s in subs]
            if all(isinstance(v, (int, float)) for v in leaf_vals):
                awarded = float(sum(leaf_vals))
        ops_breakdown.append({
            "key": c.key,
            "label": c.label,
            "max_points": c.max_points,
            "awarded_points": awarded,
            "comment": None,
            "subs": [
                {
                    "key": s["key"],
                    "label": s["label"],
                    "max_points": int(s["max_points"]),
                    "awarded_points": ops_scores.get(_leaf_key(c.key, s["key"])),
                }
                for s in subs
            ],
        })

    return {
        "team_id": team.id,
        "team_name": team.name,
        "cohort_id": cohort_id,
        "status": "scored" if (judge_totals or ops_scores) else "unscored",
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
        "ops_score": round(ops_pts, 1) if ops_scores else None,
        "ops_max_points": ops_max_total if ops_criteria else None,
        "ops_criterion_scores": ops_scores,
        "ops_criterion_notes": getattr(team, "ops_criterion_notes", None),
        "ops_breakdown": ops_breakdown,
    }


async def get_student_team_result(
    db: AsyncSession, *, cohort_id: uuid.UUID, user_id: uuid.UUID,
) -> dict:
    """Student result view -- strictly their own team's result once published.
    Never exposes individual judge identities or other teams.
    Includes score, rank, criteria breakdown, operations criteria/comments, and judge comments
    according to publication visibility settings.
    """
    from app.models.team import TeamMember
    team = await db.scalar(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(Team.cohort_id == cohort_id, TeamMember.user_id == user_id)
    )
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="You are not in a team for this cohort")

    pub = await get_publication(db, cohort_id=cohort_id)
    if pub is None:
        cohort = await db.get(Cohort, cohort_id)
        timing_info = resolve_team_timing(cohort, team)
        try:
            timing_pts = float(timing_info.get("points") or 0.0)
        except (ValueError, TypeError):
            timing_pts = 0.0
        return {
            "team_id": team.id,
            "team_name": team.name,
            "status": "pending_publication",
            "final_score": None,
            "score_percent": None,
            "raw_judge_score": None,
            "rank": None,
            "total_teams": None,
            "qualification": getattr(team, "qualification", None),
            "locked": getattr(team, "final_locked_at", None) is not None,
            "locked_at": getattr(team, "final_locked_at", None),
            "published": False,
            "timing_adjustment": timing_pts,
            "timing_badge": timing_info.get("badge"),
            "criteria_breakdown": None,
            "ops_score": None,
            "ops_max_points": None,
            "ops_breakdown": None,
            "ops_comments": None,
            "judge_comments": None,
            "judge_criteria_comments": None,
            "visibility_settings": None,
        }

    raw_settings = pub.visibility_settings or {}
    show_score = raw_settings.get("show_score", True)
    show_rank = raw_settings.get("show_rank", True)
    show_breakdown = raw_settings.get("show_breakdown", True)
    show_ops_criteria = raw_settings.get("show_ops_criteria", True)
    show_ops_comments = raw_settings.get("show_ops_comments", True)
    show_judge_comments = raw_settings.get("show_judge_comments", True)
    visibility_settings_out = {
        "show_score": show_score,
        "show_rank": show_rank,
        "show_breakdown": show_breakdown,
        "show_ops_criteria": show_ops_criteria,
        "show_ops_comments": show_ops_comments,
        "show_judge_comments": show_judge_comments,
    }

    board = await leaderboard(db, cohort_id=cohort_id)
    my_row = next((r for r in board if r["team_id"] == team.id), None)
    total_teams = len(board)

    rank = (my_row["rank"] if my_row else None) if show_rank else None
    final_score = (my_row["score"] if my_row else None) if show_score else None
    score_percent = (my_row["score_percent"] if my_row else None) if show_score else None
    raw_judge_score = (my_row["raw_judge_score"] if my_row else None) if show_score else None
    status_str = my_row["status"] if my_row else "unscored"
    timing_pts = my_row["timing_adjustment"] if my_row else 0.0
    timing_badge = my_row["timing_badge"] if my_row else None

    cohort = await db.get(Cohort, cohort_id)
    rubric_tuple = await get_rubric(db, cohort_id=cohort_id) if cohort else None
    rubric_criteria = rubric_tuple[1] if rubric_tuple else []

    score_rows = (await db.execute(
        select(CompetitionScore)
        .where(
            CompetitionScore.cohort_id == cohort_id,
            CompetitionScore.team_id == team.id,
            CompetitionScore.submitted.is_(True),
        )
    )).scalars().all()

    # 1. Criteria score breakdown with average score on every criterion across judges
    criteria_breakdown = None
    if show_breakdown:
        criteria_breakdown = []
        judge_criteria = [c for c in rubric_criteria if getattr(c, "scored_by", "judge") != "operations"]
        for c in judge_criteria:
            subs = _criterion_subs(c)
            awarded_list = []
            sub_awarded_dict: dict[str, list[float]] = {s["key"]: [] for s in subs}
            for s_row in score_rows:
                crit_scores = s_row.criterion_scores or {}
                val = crit_scores.get(c.key)
                if val is None and subs:
                    leaf_vals = [crit_scores.get(_leaf_key(c.key, sub["key"])) for sub in subs]
                    if all(isinstance(v, (int, float)) for v in leaf_vals):
                        val = float(sum(leaf_vals))
                if isinstance(val, (int, float)):
                    awarded_list.append(float(val))
                for sub in subs:
                    sval = crit_scores.get(_leaf_key(c.key, sub["key"]))
                    if isinstance(sval, (int, float)):
                        sub_awarded_dict[sub["key"]].append(float(sval))

            avg_pts = round(sum(awarded_list) / len(awarded_list), 1) if awarded_list else None
            subs_out = []
            for sub in subs:
                sub_list = sub_awarded_dict[sub["key"]]
                sub_avg = round(sum(sub_list) / len(sub_list), 1) if sub_list else None
                subs_out.append({
                    "key": sub["key"],
                    "label": sub["label"],
                    "max_points": int(sub["max_points"]),
                    "awarded_points": sub_avg,
                })
            criteria_breakdown.append({
                "key": c.key,
                "label": c.label,
                "max_points": c.max_points,
                "average_points": avg_pts,
                "subs": subs_out,
            })

    # 2. Operations criteria
    ops_score = None
    ops_max_points = None
    ops_breakdown = None
    if show_ops_criteria:
        ops_scores: dict = getattr(team, "ops_criterion_scores", None) or {}
        ops_criteria = [c for c in rubric_criteria if getattr(c, "scored_by", "judge") == "operations"]
        ops_pts = _ops_parent_total(ops_criteria, ops_scores)
        ops_max_total = float(sum(c.max_points for c in ops_criteria))
        ops_breakdown = []
        for c in ops_criteria:
            subs = _criterion_subs(c)
            awarded = ops_scores.get(c.key)
            if awarded is None and subs:
                leaf_vals = [ops_scores.get(_leaf_key(c.key, s["key"])) for s in subs]
                if all(isinstance(v, (int, float)) for v in leaf_vals):
                    awarded = float(sum(leaf_vals))
            ops_breakdown.append({
                "key": c.key,
                "label": c.label,
                "max_points": c.max_points,
                "awarded_points": awarded,
                "comment": None,
                "subs": [
                    {
                        "key": s["key"],
                        "label": s["label"],
                        "max_points": int(s["max_points"]),
                        "awarded_points": ops_scores.get(_leaf_key(c.key, s["key"])),
                    }
                    for s in subs
                ],
            })
        ops_score = round(ops_pts, 1) if ops_scores else None
        ops_max_points = ops_max_total if ops_criteria else None

    # 3. Operations comments
    ops_comments = None
    if show_ops_comments:
        notes = getattr(team, "ops_criterion_notes", None)
        ops_comments = notes.strip() if notes and notes.strip() else None

    # 4. Judges comments
    judge_comments = None
    judge_criteria_comments = None
    if show_judge_comments:
        judge_comments = []
        judge_criteria_comments = []
        for s_row in score_rows:
            if s_row.notes and s_row.notes.strip():
                judge_comments.append(s_row.notes.strip())
            crit_comments = s_row.criterion_comments or {}
            for crit_key, comment_text in crit_comments.items():
                if comment_text and comment_text.strip():
                    matching_c = next((c for c in rubric_criteria if c.key == crit_key), None)
                    lbl = matching_c.label if matching_c else crit_key
                    judge_criteria_comments.append({
                        "criterion": lbl,
                        "comment": comment_text.strip(),
                    })

    return {
        "team_id": team.id,
        "team_name": team.name,
        "status": status_str,
        "final_score": final_score,
        "score_percent": score_percent,
        "raw_judge_score": raw_judge_score,
        "rank": rank,
        "total_teams": total_teams if show_rank else None,
        "qualification": getattr(team, "qualification", None),
        "locked": getattr(team, "final_locked_at", None) is not None,
        "locked_at": getattr(team, "final_locked_at", None),
        "published": True,
        "timing_adjustment": timing_pts,
        "timing_badge": timing_badge,
        "criteria_breakdown": criteria_breakdown,
        "ops_score": ops_score,
        "ops_max_points": ops_max_points,
        "ops_breakdown": ops_breakdown,
        "ops_comments": ops_comments,
        "judge_comments": judge_comments,
        "judge_criteria_comments": judge_criteria_comments,
        "visibility_settings": visibility_settings_out,
    }


async def publish(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    visibility_settings: dict | None = None,
) -> CompetitionResultPublication:
    existing = await db.scalar(
        select(CompetitionResultPublication).where(CompetitionResultPublication.cohort_id == cohort_id)
    )
    if existing is not None:
        if visibility_settings is not None:
            existing.visibility_settings = visibility_settings
            existing.published_by = actor_user_id
            await db.flush()
        return existing
    settings = visibility_settings if visibility_settings is not None else {
        "show_score": True,
        "show_rank": True,
        "show_breakdown": True,
        "show_ops_criteria": True,
        "show_ops_comments": True,
        "show_judge_comments": True,
    }
    row = CompetitionResultPublication(
        id=uuid.uuid4(),
        cohort_id=cohort_id,
        published_by=actor_user_id,
        visibility_settings=settings,
    )
    db.add(row)
    await db.flush()
    return row


async def update_publication_settings(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    visibility_settings: dict,
) -> CompetitionResultPublication:
    row = await db.scalar(
        select(CompetitionResultPublication).where(CompetitionResultPublication.cohort_id == cohort_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Results are not published for this cohort")
    row.visibility_settings = visibility_settings
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
