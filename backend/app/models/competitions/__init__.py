"""Competition domain (2026-08-24) — judging, on top of the LMS Program
domain's `is_competition` flag and `LmsProgramItem.scope` (see
`app/models/lms/program.py` and `HANDOFF_COMPETITIONS.md`).

- `competition_rubrics` / `competition_rubric_criteria` — a competition's
  scoring rubric, authored by ops per Program.
- `competition_scores` — one row per (rubric, team, judge, cohort). Blind
  by convention (enforced in services/competitions/judging.py, not by any
  column here) until a `competition_result_publications` row exists for
  that cohort.
- `competition_result_publications` — the publish gate itself.
- `competition_judges` — a judge's cohort assignment, exact shape of
  `session_instructors` (`app/models/sessions/session.py`).
"""

from app.models.competitions.judging import (
    CompetitionJudge, CompetitionResultPublication, CompetitionRubric, CompetitionRubricCriterion,
    CompetitionScore,
)

__all__ = [
    "CompetitionRubric",
    "CompetitionRubricCriterion",
    "CompetitionScore",
    "CompetitionResultPublication",
    "CompetitionJudge",
]
