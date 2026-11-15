"""Automated tests for Operations Organizations Management (#3) endpoints."""

from datetime import datetime, timezone
import uuid

import pytest

from app.core.security import create_access_token
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.cohort_quiz import CohortQuizQuestion, CohortQuizTemplate
from app.models.lms.course import Course, CourseModule
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import WebsiteEvent
from app.schemas.lms_cohort_quiz import CohortQuizQuestionIn, CohortQuizQuestionOptionIn, CohortQuizTemplateCreate
from app.services.lms import cohort_quiz as cohort_quiz_service


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _make_user(
    db,
    *,
    roles: list[str],
    full_name: str = "Test User",
    email: str | None = None,
    organization_id=None,
    card_number: int | None = None,
) -> User:
    contact = Contact(
        id=uuid.uuid4(),
        full_name=full_name,
        email=email or f"c-{uuid.uuid4().hex[:8]}@example.com",
        contact_roles=[],
        secondary_phones=[],
        preferred_language="en",
        lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        full_name=full_name,
        email=email or f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=roles,
        status="active",
        contact_id=contact.id,
        organization_id=organization_id,
        card_number=card_number,
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_org_world(db):
    ops = await _make_user(db, roles=["operations"], full_name="Ops Coordinator")
    owner = await _make_user(
        db,
        roles=["organization"],
        full_name="Dr. Hessa Al Nahyan",
        email=f"owner-{uuid.uuid4().hex[:8]}@uni.ae",
        card_number=42,
    )

    org = Organization(
        id=uuid.uuid4(),
        name_latin="Khalifa Aerospace Partner",
        name_arabic="شريك خليفة للفضاء",
        org_type="university",
        country="uae",
        city="Abu Dhabi",
        owner_user_id=owner.id,
        is_approved=False,
        can_publish_events=True,
        can_author_courses=True,
        can_publish_courses=False,
        course_scope_all=False,
        allowed_course_ids=[],
        quiz_scope="own",
        allowed_quiz_template_ids=[],
        max_events=5,
        max_programs=4,
        max_cohorts=6,
        max_students_per_cohort=30,
        max_observers_per_cohort=3,
    )
    db.add(org)
    await db.flush()

    owner.organization_id = org.id
    await db.flush()

    # Shared SpacePoint platform course
    platform_course = Course(
        id=uuid.uuid4(),
        title="Space Systems Foundation",
        track="systems",
        level="beginner",
        created_by=ops.id,
        organization_id=None,
        is_published=True,
    )
    db.add(platform_course)
    await db.flush()
    org.allowed_course_ids = [str(platform_course.id)]

    # Org-authored course awaiting review
    authored_course = Course(
        id=uuid.uuid4(),
        title="Payload Thermal Analysis",
        track="payload",
        created_by=owner.id,
        organization_id=org.id,
        is_published=False,
        submitted_for_review_at=datetime.now(timezone.utc),
    )
    db.add(authored_course)
    await db.flush()
    db.add(
        CourseModule(
            id=uuid.uuid4(),
            course_id=authored_course.id,
            title="Thermal Nodes",
            position=1,
        )
    )

    # Program + Checklist + Cohort
    program = Program(
        id=uuid.uuid4(),
        code=f"ORGPRG-{uuid.uuid4().hex[:8]}",
        name="Orbital Robotics Fellowship",
        program_type="bootcamp",
        pricing_model="free",
        active=True,
        organization_id=org.id,
    )
    db.add(program)
    await db.flush()

    lms_program = LmsProgram(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Fellowship Checklist",
        certificate_required=True,
    )
    db.add(lms_program)
    await db.flush()

    db.add(
        LmsProgramItem(
            id=uuid.uuid4(),
            owner_type="program",
            owner_id=lms_program.id,
            position=1,
            title="Complete Payload Module",
            item_type="course",
            course_id=authored_course.id,
            optional=False,
            scope="individual",
        )
    )

    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        organization_id=org.id,
        name="Spring 2026 Cohort",
        status="running",
        capacity=25,
    )
    db.add(cohort)
    await db.flush()

    # Observer linked via LmsProgramAssignment (without organization_id on User)
    observer = await _make_user(db, roles=["student"], full_name="Cohort Observer", card_number=77)
    db.add(
        LmsProgramAssignment(
            id=uuid.uuid4(),
            lms_program_id=lms_program.id,
            user_id=observer.id,
            cohort_id=cohort.id,
            mode="observer",
        )
    )

    # Enrolled student in cohort
    student = await _make_user(db, roles=["student"], full_name="Mariam Al Suwaidi")
    db.add(
        Registration(
            id=uuid.uuid4(),
            cohort_id=cohort.id,
            contact_id=student.contact_id,
            status="registered",
            ticket_token=f"TK-{uuid.uuid4().hex[:12].upper()}",
            registered_via="invite_code",
        )
    )

    # Invite code batch linked to org owner & cohort
    invite = InvitationCode(
        id=uuid.uuid4(),
        code=f"ORG-{uuid.uuid4().hex[:6].upper()}",
        label="Spring Cohort Batch",
        kind="student",
        max_uses=20,
        used_count=1,
        is_active=True,
        created_by=owner.id,
    )
    db.add(invite)
    await db.flush()
    db.add(
        InvitationCodeGrant(
            id=uuid.uuid4(),
            invitation_code_id=invite.id,
            product_type="cohort",
            cohort_id=cohort.id,
        )
    )

    # Org Quiz Template & Question
    qt = await cohort_quiz_service.create_template(
        db,
        body=CohortQuizTemplateCreate(name="Thermal Pre-Lab Check"),
        created_by=owner.id,
    )
    qq = await cohort_quiz_service.create_question(
        db,
        body=CohortQuizQuestionIn(
            topic="Thermal",
            difficulty="Easy",
            time_limit_seconds=30,
            prompt="Which mode transfers heat through a vacuum?",
            options=[
                CohortQuizQuestionOptionIn(text="Conduction", is_correct=False),
                CohortQuizQuestionOptionIn(text="Radiation", is_correct=True),
            ],
        ),
        created_by=owner.id,
    )
    await cohort_quiz_service.add_template_question(db, template_id=qt.id, question_id=qq.id)
    qt_row = await db.get(CohortQuizTemplate, qt.id)
    qq_row = await db.get(CohortQuizQuestion, qq.id)
    assert qt_row is not None and qq_row is not None
    qt_row.organization_id = org.id
    qq_row.organization_id = org.id

    # Website landing page
    event = WebsiteEvent(
        id=uuid.uuid4(),
        slug=f"org-ev-{uuid.uuid4().hex[:8]}",
        country="uae",
        title="Orbital Robotics Demo Day",
        event_type="competition",
        organization_id=org.id,
        cohort_id=cohort.id,
        is_published=True,
    )
    db.add(event)
    await db.commit()

    return {
        "ops": ops,
        "owner": owner,
        "observer": observer,
        "student": student,
        "org": org,
        "program": program,
        "cohort": cohort,
        "authored_course": authored_course,
        "platform_course": platform_course,
        "quiz_template": qt,
        "invite": invite,
        "event": event,
    }


@pytest.mark.asyncio
async def test_list_organizations_usage_rollups(db, client):
    seed = await _seed_org_world(db)
    resp = await client.get("/admin/website/organizations", headers=_headers(seed["ops"]))
    assert resp.status_code == 200
    rows = resp.json()
    match = next(r for r in rows if r["id"] == str(seed["org"].id))

    assert match["name_latin"] == "Khalifa Aerospace Partner"
    assert match["is_approved"] is False
    assert match["owner_card_id"] == "SP-ORG-0042-UAE"
    assert match["programs_count"] == 1
    assert match["cohorts_count"] == 1
    assert match["running_cohorts_count"] == 1
    assert match["enrolled_students_count"] == 1
    assert match["highest_cohort_students"] == 1
    assert match["highest_cohort_name"] == "Spring 2026 Cohort"
    assert match["highest_cohort_observers"] == 1
    assert match["authored_courses_count"] == 1
    assert match["pending_review_courses_count"] == 1
    assert match["shared_courses_count"] == 1
    assert match["invite_batches_active_count"] == 1
    assert match["invite_used_count"] == 1
    assert match["invite_max_count"] == 20
    assert match["quiz_templates_authored_count"] == 1
    assert match["quiz_questions_authored_count"] == 1
    assert match["events_count"] == 1
    assert match["published_events_count"] == 1


@pytest.mark.asyncio
async def test_get_organization_detail_360(db, client):
    seed = await _seed_org_world(db)
    resp = await client.get(
        f"/admin/website/organizations/{seed['org'].id}/detail",
        headers=_headers(seed["ops"]),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["organization"]["id"] == str(seed["org"].id)
    assert len(data["programs"]) == 1
    assert data["programs"][0]["checklist_items"][0]["title"] == "Complete Payload Module"
    assert len(data["cohorts"]) == 1
    assert data["cohorts"][0]["enrolled_count"] == 1
    assert data["cohorts"][0]["observers_count"] == 1
    assert len(data["students"]) == 1
    assert data["students"][0]["full_name"] == "Mariam Al Suwaidi"
    assert len(data["invite_batches"]) == 1
    assert data["invite_batches"][0]["code"] == seed["invite"].code
    assert len(data["authored_courses"]) == 1
    assert data["authored_courses"][0]["submitted_for_review_at"] is not None
    assert len(data["shared_courses"]) == 1
    assert data["shared_courses"][0]["id"] == str(seed["platform_course"].id)
    assert len(data["quiz_templates"]) == 1
    assert data["quiz_templates"][0]["questions_count"] == 1
    assert len(data["landing_pages"]) == 1
    assert data["landing_pages"][0]["registrations_count"] == 1

    roles_by_uid = {m["user_id"]: m["role"] for m in data["team"]}
    assert roles_by_uid[str(seed["owner"].id)] == "Owner"
    assert roles_by_uid[str(seed["observer"].id)] == "Observer"


@pytest.mark.asyncio
async def test_update_org_quotas_quiz_scope_and_approval(db, client):
    seed = await _seed_org_world(db)
    resp = await client.put(
        f"/admin/website/organizations/{seed['org'].id}",
        headers=_headers(seed["ops"]),
        json={
            "org_name_latin": "Khalifa Aerospace Partner",
            "is_approved": True,
            "quiz_scope": "selected",
            "allowed_quiz_template_ids": [str(seed["quiz_template"].id)],
            "max_cohorts": 12,
            "max_students_per_cohort": 60,
        },
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["is_approved"] is True
    assert updated["quiz_scope"] == "selected"
    assert updated["allowed_quiz_template_ids"] == [str(seed["quiz_template"].id)]
    assert updated["max_cohorts"] == 12
    assert updated["max_students_per_cohort"] == 60


@pytest.mark.asyncio
async def test_toggle_org_authored_course_publish_and_member_reset_link(db, client):
    seed = await _seed_org_world(db)

    # Publish org course
    pub_resp = await client.post(
        f"/admin/website/organizations/{seed['org'].id}/courses/{seed['authored_course'].id}/publish",
        headers=_headers(seed["ops"]),
        json={"is_published": True},
    )
    assert pub_resp.status_code == 200
    assert pub_resp.json()["is_published"] is True

    # Cannot publish non-org platform course via this endpoint
    wrong_course_resp = await client.post(
        f"/admin/website/organizations/{seed['org'].id}/courses/{seed['platform_course'].id}/publish",
        headers=_headers(seed["ops"]),
        json={"is_published": True},
    )
    assert wrong_course_resp.status_code == 404

    # Member reset link works for observer associated via cohort
    reset_resp = await client.post(
        f"/admin/website/organizations/{seed['org'].id}/members/{seed['observer'].id}/reset-link",
        headers=_headers(seed["ops"]),
    )
    assert reset_resp.status_code == 200
    payload = reset_resp.json()
    assert payload["user_id"] == str(seed["observer"].id)
    assert "/set-password?token=" in payload["reset_url"]

    # Rejects unrelated user
    stranger = await _make_user(db, roles=["student"], full_name="Outside User")
    bad_reset = await client.post(
        f"/admin/website/organizations/{seed['org'].id}/members/{stranger.id}/reset-link",
        headers=_headers(seed["ops"]),
    )
    assert bad_reset.status_code == 404


@pytest.mark.asyncio
async def test_ops_organizations_role_guard(db, client):
    seed = await _seed_org_world(db)
    student_headers = _headers(seed["student"])

    r1 = await client.get("/admin/website/organizations", headers=student_headers)
    r2 = await client.get(f"/admin/website/organizations/{seed['org'].id}/detail", headers=student_headers)
    r3 = await client.post(
        f"/admin/website/organizations/{seed['org'].id}/courses/{seed['authored_course'].id}/publish",
        headers=student_headers,
        json={"is_published": True},
    )
    assert r1.status_code == 403
    assert r2.status_code == 403
    assert r3.status_code == 403
