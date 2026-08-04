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
    operations = "operations"
    # Inventory phase (I0-2). `coo` approves; `storekeeper` is deliberately
    # narrow — refill/receive/move stock only, no session assignments, no kit
    # create/edit/delete. See core/dependencies.py.
    coo = "coo"
    storekeeper = "storekeeper"
    # LMS phase (LM0-2). A learner surface, not an ops account: `student` must
    # be rejected by require_operations. Content access is gated by
    # `enrollments`, not by this role — see services/lms/.
    student = "student"


# ── Interns domain ───────────────────────────────────────────────────────────
class WorkStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class SubmissionStatus(str, enum.Enum):
    submitted = "submitted"
    reviewed = "reviewed"


# ── Instructors domain ──────────────────────────────────────────────────────
class ApplicationStatus(str, enum.Enum):
    in_progress = "in_progress"
    under_review = "under_review"
    phase_1_approved = "phase_1_approved"
    research_approved = "research_approved"  # Phase-2 research presentation gate (parity with the live VPS pipeline)
    approved = "approved"
    rejected = "rejected"


class VideoSubmissionStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"


class ModuleSubmissionStatus(str, enum.Enum):
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class PaymentLetterStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    signed = "signed"
    paid = "paid"


class PaymentSessionRole(str, enum.Enum):
    lead_facilitator = "Lead Facilitator"
    facilitator = "Facilitator"
    assistant_facilitator = "Assistant Facilitator"


# ── Shared documents (PLAN §4.5) ────────────────────────────────────────────
class CertificateType(str, enum.Enum):
    workshop_delivery = "workshop_delivery"
    internship_completion = "internship_completion"
    instructor_completion = "instructor_completion"
    student_completion = "student_completion"  # W5 S5-3 — cohort completion, contact-owned
