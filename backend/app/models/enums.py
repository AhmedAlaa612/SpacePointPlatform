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
