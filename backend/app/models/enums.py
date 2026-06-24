import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    intern = "intern"
    leader = "leader"
    applicant = "applicant"
    instructor = "instructor"
    facilitator = "facilitator"
    ambassador = "ambassador"
    teacher = "teacher"


# ── Interns domain ───────────────────────────────────────────────────────────
class WorkStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class SubmissionStatus(str, enum.Enum):
    submitted = "submitted"
    reviewed = "reviewed"
