"""Instructor assessment & performance ranking domain (2026-09) — a
per-opportunity, randomized scenario MCQ instructors complete when applying
for a role, plus the post-program performance rating and ranking-weight
config that build on it.

- `assessment_configs` / `assessment_questions` — a facilitator-authored,
  reusable question bank (category + critical flag, unlike Live Games' or
  the LMS quiz's flat question lists).
- `assessment_cohort_assignments` — the on/off switch: which config (if any)
  gates a given cohort's open calls.
- `assessment_attempts` / `assessment_answers` — one instructor's randomized
  15-question draw for one opportunity, and their answers to it.
- `instructor_program_ratings` / `instructor_certification_tags` — the
  post-program 10-dimension rating and free-text certification tags.
- `ranking_weight_profiles` — the configurable blend behind the Priority
  Score shown on the instructor-selection screen.

Attaches to the existing staffing marketplace (`models/sessions/`) via
`cohort_id`/`cohort_call_id` rather than inventing a parallel
"opportunity"/"application" concept — see `services/sessions/staffing.py`'s
module docstring for why that marketplace is already the right home for
"instructor applies for a role".
"""

from app.models.instructor_assessment.config import AssessmentConfig, AssessmentQuestion
from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.attempt import AssessmentAttempt, AssessmentAnswer
from app.models.instructor_assessment.rating import (
    RATING_DIMENSIONS, InstructorProgramRating, InstructorCertificationTag,
)
from app.models.instructor_assessment.ranking import RANKING_FACTORS, RankingWeightProfile

__all__ = [
    "AssessmentConfig", "AssessmentQuestion",
    "AssessmentCohortAssignment",
    "AssessmentAttempt", "AssessmentAnswer",
    "RATING_DIMENSIONS", "InstructorProgramRating", "InstructorCertificationTag",
    "RANKING_FACTORS", "RankingWeightProfile",
]
