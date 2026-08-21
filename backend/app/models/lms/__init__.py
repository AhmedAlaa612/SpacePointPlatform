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

Nothing here references `contacts`; everything keys on `users`, so
`MERGE_FK_REGISTRY` is untouched. A student is a `users` row with the
`student` role (LM0-2), linked to the spine via `users.contact_id`.
"""

from app.models.lms.course import Course, CourseModule, ModuleItem, ModuleVideo, VideoCheckpoint
from app.models.lms.enrollment import Enrollment, ItemProgress
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.lms.points import PointEvent
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem, LmsProgramItemProgress,
)
from app.models.lms.purchase import Purchase

__all__ = [
    "Course",
    "CourseModule",
    "ModuleItem",
    "ModuleVideo",
    "VideoCheckpoint",
    "Enrollment",
    "ItemProgress",
    "InvitationCodeGrant",
    "LearningPath",
    "LearningPathStep",
    "PointEvent",
    "LmsProgram",
    "LmsProgramCohortOverride",
    "LmsProgramItem",
    "LmsProgramAssignment",
    "LmsProgramItemProgress",
    "Purchase",
]
