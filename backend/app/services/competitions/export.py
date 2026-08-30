"""Results export (2026-08-27) — one .xlsx with everything ops needs to
review a cohort's judging round off-platform: a Scores sheet (rank,
average, every judge's own score) and a Submissions sheet (every team's
link-only deliverables, who submitted them, and when). Reuses
`judging.leaderboard` and `lms.program.team_submission_items` rather than
re-querying — same numbers the Results tab and judge team-detail view
already show, never a second source of truth for either.
"""

import io
import uuid

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.services.competitions.judging import leaderboard
from app.services.lms.program import team_submission_items

MAX_COLUMN_WIDTH = 60


def _autosize(sheet: Worksheet) -> None:
    for col_cells in sheet.columns:
        length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=0)
        sheet.column_dimensions[col_cells[0].column_letter].width = min(length + 2, MAX_COLUMN_WIDTH)


async def export_results_workbook(db: AsyncSession, *, cohort_id: uuid.UUID) -> bytes:
    board = await leaderboard(db, cohort_id=cohort_id)
    # Stable column order across runs, not insertion order off a set.
    judge_names = sorted({js["judge_name"] for row in board for js in row["judge_scores"]})

    wb = openpyxl.Workbook()
    scores = wb.active
    scores.title = "Scores"
    scores.append(["Rank", "Team", "Avg Score", "Status", "Advanced To", *judge_names])
    for row in board:
        by_judge = {js["judge_name"]: js["total_points"] for js in row["judge_scores"]}
        scores.append([
            row["rank"], row["team_name"], row["score"], row["status"], row["advanced_to"] or "",
            *[by_judge.get(name, "") for name in judge_names],
        ])
    _autosize(scores)

    submissions = wb.create_sheet("Submissions")
    submissions.append(["Team", "Item", "Type", "Status", "Link", "Submitted At", "Submitted By"])
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort_id).order_by(Team.name))).scalars().all()
    for team in teams:
        for item in await team_submission_items(db, team_id=team.id):
            submissions.append([
                team.name, item["title"], item["item_type"], item["status"],
                item["submitted_url"] or "",
                item["updated_at"].strftime("%Y-%m-%d %H:%M") if item["updated_at"] else "",
                item["updated_by_name"] or "",
            ])
    _autosize(submissions)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
