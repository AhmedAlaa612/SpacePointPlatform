"""Instructor LMS progress schemas (LM1-10) — response shape for
`GET /sessions/{session_id}/lms-progress`."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ModuleProgressOut(BaseModel):
    module_id: UUID
    title: str | None = None
    position: int
    locked: bool
    mandatory_total: int
    mandatory_completed: int


class QuizProgressOut(BaseModel):
    item_id: UUID
    title: str | None = None
    status: str
    attempts: int
    best_score: float | None = None


class CourseProgressOut(BaseModel):
    course_id: UUID
    course_title: str | None = None
    completed: bool
    modules: list[ModuleProgressOut]
    quizzes: list[QuizProgressOut]


class StudentLmsProgressOut(BaseModel):
    contact_id: UUID
    student_name: str
    has_lms_account: bool
    courses: list[CourseProgressOut]


class SessionLmsProgressOut(BaseModel):
    session_id: UUID
    cohort_id: UUID
    program_name: str
    students: list[StudentLmsProgressOut]
