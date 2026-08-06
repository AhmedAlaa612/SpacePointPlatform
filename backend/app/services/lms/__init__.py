"""LMS services (LM1-2) — the rules layer on top of the LM1-1 schema.

Enrollment (the access gate), progress and unlock, server-side quiz grading,
derived completion, and the student-view serializer. Nothing here touches
`contacts`; everything keys on `users`, so `MERGE_FK_REGISTRY` is untouched.
"""

from app.services.lms.checkpoint import submit_checkpoint_answer
from app.services.lms.enrollment import enroll
from app.services.lms.progress import course_completion, item_progress, unlock_state
from app.services.lms.quiz import submit_quiz
from app.services.lms.serialize import sanitize_checkpoint, student_view

__all__ = [
    "enroll",
    "unlock_state",
    "item_progress",
    "course_completion",
    "submit_quiz",
    "submit_checkpoint_answer",
    "student_view",
    "sanitize_checkpoint",
]