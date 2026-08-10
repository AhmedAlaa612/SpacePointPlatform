"""LMS domain (LM1-1) — courses online + offline.

Seven tables, one CHECK-free schema, no state machines:
- `courses` / `course_modules` / `module_items` — the authored course tree
  (`module_items.content` JSONB carries every authored payload, §2)
- `module_videos` — the one async state row the transcode worker writes
- `program_curriculum` — program → ordered courses (D5)
- `enrollments` — the single access gate (D8)
- `item_progress` — per-student per-item raw rows; completion is derived
- `learning_paths` / `learning_path_steps` — self-paced ordered course
  sequences with their own progress rollup (LMS redesign, 2026-08-08)

Nothing here references `contacts`; everything keys on `users`, so
`MERGE_FK_REGISTRY` is untouched. A student is a `users` row with the
`student` role (LM0-2), linked to the spine via `users.contact_id`.
"""

from app.models.lms.course import Course, CourseModule, ModuleItem, ModuleVideo, VideoCheckpoint
from app.models.lms.curriculum import CohortCurriculum, ProgramCurriculum
from app.models.lms.enrollment import Enrollment, ItemProgress
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.lms.points import PointEvent

__all__ = [
    "Course",
    "CourseModule",
    "ModuleItem",
    "ModuleVideo",
    "VideoCheckpoint",
    "ProgramCurriculum",
    "CohortCurriculum",
    "Enrollment",
    "ItemProgress",
    "LearningPath",
    "LearningPathStep",
    "PointEvent",
]
