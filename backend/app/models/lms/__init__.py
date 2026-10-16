"""LMS domain (LM1-1) — courses online + offline.

- `courses` / `course_modules` / `module_items` — the authored course tree
  (`module_items.content` JSONB carries every authored payload, §2)
- `module_videos` — the one async state row the transcode worker writes
- `enrollments` — the single access gate (D8)
- `item_progress` — per-student per-item raw rows; completion is derived
- `learning_paths` / `learning_path_steps` — self-paced ordered course
  sequences with their own progress rollup (LMS redesign, 2026-08-08)
- `lms_programs` / `lms_program_cohort_overrides` / `lms_program_items` /
  `lms_program_assignments` / `lms_program_item_progress` — the
  checklist-driven Program redesign (2026-08-21), replacing the old flat
  `program_curriculum`/`cohort_curriculum` course list entirely.
- `invitation_code_grants` — a standing "this invite-code batch gets these
  courses/paths free" rule (2026-08-21), applied to new and existing code
  holders alike.
- `lms_program_team_item_progress` — the Competition domain's team-scoped
  twin of `lms_program_item_progress` (2026-08-24), for `LmsProgramItem`
  rows with `scope="team"`. See `HANDOFF_COMPETITIONS.md`.
- `cohort_quiz_questions` / `cohort_quiz_templates` /
  `cohort_quiz_template_questions` / `cohort_quiz_attempts` /
  `cohort_quiz_answers` (2026-09) — the per-cohort timed knowledge quiz,
  a fixed cross-topic question set behind the checklist's `quiz` item
  type. See `app/models/lms/cohort_quiz.py`'s own docstring for how this
  differs from the in-course module quiz and the instructor-assessment
  domain.

Nothing here references `contacts`; everything keys on `users`, so
`MERGE_FK_REGISTRY` is untouched. A student is a `users` row with the
`student` role (LM0-2), linked to the spine via `users.contact_id`.
"""

from app.models.lms.author_profile import LmsAuthorProfile
from app.models.lms.cohort_quiz import (
    CohortQuizAnswer, CohortQuizAttempt, CohortQuizQuestion, CohortQuizTemplate, CohortQuizTemplateQuestion,
)
from app.models.lms.course import Course, CourseModule, ModuleItem, VideoCheckpoint
from app.models.lms.enrollment import Enrollment, ItemProgress
from app.models.lms.invite_grant import InvitationCodeGrant, UserInvitationCode
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.lms.points import PointEvent
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem, LmsProgramItemProgress,
    LmsProgramTeamItemProgress,
)
from app.models.lms.purchase import Purchase

__all__ = [
    "LmsAuthorProfile",
    "CohortQuizQuestion",
    "CohortQuizTemplate",
    "CohortQuizTemplateQuestion",
    "CohortQuizAttempt",
    "CohortQuizAnswer",
    "Course",
    "CourseModule",
    "ModuleItem",
    "VideoCheckpoint",
    "Enrollment",
    "ItemProgress",
    "InvitationCodeGrant",
    "UserInvitationCode",
    "LearningPath",
    "LearningPathStep",
    "PointEvent",
    "LmsProgram",
    "LmsProgramCohortOverride",
    "LmsProgramItem",
    "LmsProgramAssignment",
    "LmsProgramItemProgress",
    "LmsProgramTeamItemProgress",
    "Purchase",
]
