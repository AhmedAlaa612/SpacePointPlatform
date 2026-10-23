from datetime import datetime, timedelta, timezone
import uuid
import pytest
from fastapi import HTTPException

from app.models.enums import UserRole
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment
from app.models.lms.invite_grant import InvitationCodeGrant, UserInvitationCode
from app.models.lms.program import LmsProgram, LmsProgramAssignment
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.invitations import resolve_invite_code
from app.services.lms.enrollment import enroll, enrollment_is_active
from app.services.lms.invite_grants import (
    apply_invite_code_grants_to_new_user,
    is_user_cohort_grant_expired,
    sync_invite_code_enrollments_expiry,
)
from app.services.lms.program import get_student_checklist, list_student_assignments


@pytest.mark.asyncio
async def test_invite_code_expiry_and_grant_loss(db):
    # 0. Create admin user
    admin_user = User(
        id=uuid.uuid4(),
        full_name="Admin Staff",
        email="admin.staff@test.local",
        password_hash="fake",
        roles=[UserRole.admin],
    )
    db.add(admin_user)
    await db.flush()

    # 1. Create a course
    course = Course(
        id=uuid.uuid4(),
        title="Orbital Mechanics",
        kind="online",
        access_mode="invite_only",
        created_by=admin_user.id,
    )
    db.add(course)

    # 2. Create a cohort & program
    sess_prog = Program(
        id=uuid.uuid4(),
        code="SP-TEST-01",
        name="Space Program",
        program_type="course",
        pricing_model="free",
    )
    db.add(sess_prog)
    await db.flush()

    cohort = Cohort(id=uuid.uuid4(), name="Alpha Cohort", program_id=sess_prog.id, status="open")
    db.add(cohort)
    lms_prog = LmsProgram(id=uuid.uuid4(), name="Alpha LMS Checklist")
    db.add(lms_prog)
    await db.flush()

    # 3. Create an invite code with expiry 1 hour in the future
    future_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    code = InvitationCode(
        id=uuid.uuid4(),
        code="EXPTEST1",
        kind="student",
        expires_at=future_expiry,
        is_active=True,
    )
    db.add(code)

    # Attach grants: Course grant & Cohort program grant
    grant_course = InvitationCodeGrant(
        id=uuid.uuid4(),
        invitation_code_id=code.id,
        product_type="course",
        course_id=course.id,
    )
    grant_cohort = InvitationCodeGrant(
        id=uuid.uuid4(),
        invitation_code_id=code.id,
        product_type="lms_program",
        cohort_id=cohort.id,
    )
    db.add_all([grant_course, grant_cohort])
    await db.flush()

    # 4. Create student user
    contact = Contact(id=uuid.uuid4(), full_name="Learner One", email="learner1@test.local", contact_roles=["student"])
    db.add(contact)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        full_name="Learner One",
        email="learner1@test.local",
        password_hash="fake",
        roles=[UserRole.student],
        contact_id=contact.id,
        invitation_code_used="EXPTEST1",
    )
    db.add(user)
    await db.flush()

    user_code = UserInvitationCode(
        id=uuid.uuid4(),
        user_id=user.id,
        invitation_code_id=code.id,
        code="EXPTEST1",
    )
    db.add(user_code)
    await db.flush()

    # 5. Apply grants to this user
    await apply_invite_code_grants_to_new_user(db, user_id=user.id, invitation_code_id=code.id)
    await db.flush()

    # Check course enrollment exists and has expires_at set to future_expiry
    enrollment = (await db.execute(
        select_enrollment(user.id, course.id)
    )).scalar_one_or_none()
    assert enrollment is not None
    assert enrollment.expires_at == future_expiry

    # Enrollment is currently active
    active_row = (await db.execute(
        select_enrollment(user.id, course.id).where(*enrollment_is_active())
    )).scalar_one_or_none()
    assert active_row is not None

    # Check program assignment grant status
    assert await is_user_cohort_grant_expired(db, user_id=user.id, cohort_id=cohort.id) is False

    # 6. Now simulate expiry passing: update code.expires_at to 1 hour in the past
    past_expiry = datetime.now(timezone.utc) - timedelta(hours=1)
    code.expires_at = past_expiry
    await sync_invite_code_enrollments_expiry(db, invitation_code=code)
    await db.flush()

    # 7. Check that the link is now invalid (resolve_invite_code raises 400)
    with pytest.raises(HTTPException) as exc_info:
        await resolve_invite_code(db, "EXPTEST1", kind="student")
    assert exc_info.value.status_code == 400
    assert "expired" in exc_info.value.detail.lower()

    # 8. Check that people lose course access
    # Enrollment.expires_at was synchronized to past_expiry
    await db.refresh(enrollment)
    assert enrollment.expires_at == past_expiry

    # *enrollment_is_active() predicate now rejects the enrollment!
    active_row_expired = (await db.execute(
        select_enrollment(user.id, course.id).where(*enrollment_is_active())
    )).scalar_one_or_none()
    assert active_row_expired is None, "Student must lose active course access after expiry"

    # 9. Check that student loses program checklist access
    assert await is_user_cohort_grant_expired(db, user_id=user.id, cohort_id=cohort.id) is True, \
        "Cohort program grant must be flagged as expired"


def select_enrollment(user_id, course_id):
    from sqlalchemy import select
    return select(Enrollment).where(
        Enrollment.user_id == user_id,
        Enrollment.course_id == course_id,
    )
