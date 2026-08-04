"""LMS curriculum domain (LM1-1) — the program → ordered courses binding.

Every program gets an LMS view (V2 §A3 / LMS D5): `program_curriculum` is the
explicit ordered list of courses a program offers, replacing the
`programs.lms_enabled`/`lms_course_id` flag idea. Enrollments that are added
to a student at cohort-add time come from *this* list (LM1-7), so the table is
ops-facing as much as course-facing.

`position` here is course order inside a workshop — distinct from
`course_modules.position`, which is lesson order inside a course. No shared
counter (§2 note).
"""

import uuid

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ProgramCurriculum(Base):
    """Which courses a program's curriculum consists of, in order.

    Both unique constraints matter: a program can't list the same course
    twice (double-enroll would follow), and a program can't name two courses
    "3rd". Deleting a program or a course cascades the binding.
    """

    __tablename__ = "program_curriculum"
    __table_args__ = (
        UniqueConstraint("program_id", "course_id", name="uq_program_curriculum_program_course"),
        UniqueConstraint("program_id", "position", name="uq_program_curriculum_program_position"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False
    )
    course_id = Column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    position = Column(Integer, nullable=False)