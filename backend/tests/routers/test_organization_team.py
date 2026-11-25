"""Organization self-service team management (`/organization/team`).

Regression coverage for the "Add Team Member" blank screen:
- the password is optional in the UI, so the API must accept a missing one
  instead of returning a 422 whose `detail` is a list.
- adding a member emails them a set-password link (best effort).
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.spine.organization import Organization
from app.models.user import User


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.fixture
def sent_emails(monkeypatch):
    """Capture outbound mail instead of reaching SMTP."""
    outbox: list[tuple[str, str, str]] = []

    async def fake_send_email(to, subject, body, **kwargs):
        outbox.append((to, subject, body))

    monkeypatch.setattr("app.services.email.send_email", fake_send_email)
    return outbox


async def _make_user(db, *, roles: list[str], email: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Org Owner",
        email=email or f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=roles,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_org(db) -> tuple[User, Organization]:
    owner = await _make_user(db, roles=["organization"])
    org = Organization(
        id=uuid.uuid4(),
        name_latin="Test Partner Org",
        org_type="university",
        country="uae",
        owner_user_id=owner.id,
    )
    db.add(org)
    await db.flush()
    owner.organization_id = org.id
    await db.flush()
    return owner, org


async def test_add_team_member_without_password(db, client, sent_emails):
    owner, org = await _seed_org(db)
    member_email = f"sarah-{uuid.uuid4().hex[:8]}@example.com"

    resp = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={"full_name": "Sarah Jenkins", "email": member_email},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["full_name"] == "Sarah Jenkins"
    assert body["is_owner"] is False
    assert body["invite_email_sent"] is True

    assert len(sent_emails) == 1
    to, subject, mail_body = sent_emails[0]
    assert to == member_email
    assert "Test Partner Org" in subject
    assert "/set-password?token=" in mail_body


async def test_add_team_member_with_password(db, client, sent_emails):
    owner, org = await _seed_org(db)

    resp = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={
            "full_name": "Sarah Jenkins",
            "email": f"sarah-{uuid.uuid4().hex[:8]}@example.com",
            "password": "Initial-Pass-123",
        },
    )

    assert resp.status_code == 201, resp.text
    created = await db.get(User, uuid.UUID(resp.json()["id"]))
    assert verify_password("Initial-Pass-123", created.password_hash)
    assert created.organization_id == org.id


async def test_team_member_reset_link_emails_seven_day_link(db, client, sent_emails):
    owner, org = await _seed_org(db)
    member_email = f"sarah-{uuid.uuid4().hex[:8]}@example.com"

    added = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={"full_name": "Sarah Jenkins", "email": member_email},
    )
    assert added.status_code == 201, added.text
    sent_emails.clear()

    resp = await client.post(
        f"/organization/team/{added.json()['id']}/reset-link",
        headers=_headers(owner),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == added.json()["id"]
    assert body["email_sent"] is True
    assert "/set-password?token=" in body["reset_url"]

    assert len(sent_emails) == 1
    to, subject, mail_body = sent_emails[0]
    assert to == member_email
    assert "Set your SpacePoint password" in subject
    assert "valid for 7 days" in mail_body

    token = body["reset_url"].split("token=", 1)[1]
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    remaining_days = (payload["exp"] - datetime.now(timezone.utc).timestamp()) / 86400
    assert 6.9 < remaining_days <= 7.0


async def test_team_member_reset_link_rejects_outsider(db, client, sent_emails):
    owner, org = await _seed_org(db)
    outsider = await _make_user(db, roles=["organization"])

    resp = await client.post(
        f"/organization/team/{outsider.id}/reset-link",
        headers=_headers(owner),
    )

    assert resp.status_code == 404, resp.text


async def test_ops_can_invite_member_and_track_join_status(db, client, sent_emails):
    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])
    member_email = f"coord-{uuid.uuid4().hex[:8]}@example.com"

    created = await client.post(
        f"/admin/website/organizations/{org.id}/members",
        headers=_headers(ops),
        json={"full_name": "Ops Invited Coordinator", "email": member_email},
    )

    assert created.status_code == 201, created.text
    assert created.json()["invite_email_sent"] is True

    assert len(sent_emails) == 1
    to, subject, mail_body = sent_emails[0]
    assert to == member_email
    assert "Test Partner Org" in subject
    assert "valid for 7 days" in mail_body

    detail = await client.get(
        f"/admin/website/organizations/{org.id}/detail", headers=_headers(ops)
    )
    assert detail.status_code == 200, detail.text
    row = next(m for m in detail.json()["team"] if m["email"] == member_email)
    assert row["invite_pending"] is True

    # The emailed link works and flips the row from "invite pending" to joined.
    token = mail_body.split("set-password?token=", 1)[1].split()[0].strip()
    set_password = await client.post(
        "/auth/set-password", json={"token": token, "new_password": "Joined-Pass-123"}
    )
    assert set_password.status_code == 200, set_password.text

    detail = await client.get(
        f"/admin/website/organizations/{org.id}/detail", headers=_headers(ops)
    )
    row = next(m for m in detail.json()["team"] if m["email"] == member_email)
    assert row["invite_pending"] is False


async def test_org_account_cannot_use_admin_invite_endpoint(db, client, sent_emails):
    owner, org = await _seed_org(db)

    resp = await client.post(
        f"/admin/website/organizations/{org.id}/members",
        headers=_headers(owner),
        json={"full_name": "Nope", "email": f"nope-{uuid.uuid4().hex[:8]}@example.com"},
    )

    assert resp.status_code == 403, resp.text


async def test_invite_attaches_existing_lms_account(db, client, sent_emails):
    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])
    student = await _make_user(db, roles=["student"])
    old_hash = student.password_hash

    resp = await client.post(
        f"/admin/website/organizations/{org.id}/members",
        headers=_headers(ops),
        json={"full_name": "Existing Student", "email": student.email},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["existing_account"] is True
    assert body["invite_email_sent"] is True

    await db.refresh(student)
    assert "organization" in student.role_values
    assert student.organization_id == org.id
    # Existing credentials are untouched.
    assert student.password_hash == old_hash
    assert student.must_change_password is False

    assert len(sent_emails) == 1
    _, subject, mail_body = sent_emails[0]
    assert "You've been added to Test Partner Org on SpacePoint" == subject
    assert "/login" in mail_body
    assert "set-password" not in mail_body


async def test_invite_moves_account_from_another_org(db, client, sent_emails):
    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])

    other_org = Organization(
        id=uuid.uuid4(),
        name_latin="Other University",
        org_type="university",
        country="uae",
    )
    db.add(other_org)
    await db.flush()

    student = await _make_user(db, roles=["student"])
    student.organization_id = other_org.id
    await db.flush()

    resp = await client.post(
        f"/admin/website/organizations/{org.id}/members",
        headers=_headers(ops),
        json={"full_name": "Other Uni Student", "email": student.email},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["existing_account"] is True
    await db.refresh(student)
    # Last-in-wins: the new assignment overrides the previous organization.
    assert student.organization_id == org.id
    assert "organization" in student.role_values
    assert len(sent_emails) == 1


# -- Sandbox roles & staffing (2026-11-18) ------------------------------------

from app.models.competitions.judging import CompetitionJudge
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.pre_session_quiz import PreSessionQuizAssignment, PreSessionQuizPreset
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor


async def _seed_cohort(db, org: Organization, *, sessions: int = 1):
    from sqlalchemy import select

    role = (await db.execute(select(DeliveryRole).limit(1))).scalars().first()
    if role is None:
        role = DeliveryRole(id=uuid.uuid4(), name=f"Lead {uuid.uuid4().hex[:6]}", sort_order=1, is_active=True)
        db.add(role)
        await db.flush()

    program = Program(
        id=uuid.uuid4(),
        code=f"ORG-{uuid.uuid4().hex[:6]}",
        name="Partner Program",
        program_type="workshop",
        pricing_model="free",
        organization_id=org.id,
    )
    db.add(program)
    await db.flush()

    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Partner Cohort",
        status="registration_open",
        organization_id=org.id,
    )
    db.add(cohort)
    await db.flush()

    session_rows = []
    for idx in range(sessions):
        s = Session(
            id=uuid.uuid4(),
            cohort_id=cohort.id,
            title=f"Session {idx + 1}",
            meeting_date=date.today(),
            staffing_status="unstaffed",
        )
        db.add(s)
        session_rows.append(s)
    await db.flush()
    return program, cohort, session_rows


async def _add_member(db, client, owner, *, org_role: str, email: str | None = None):
    email = email or f"member-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={"full_name": "Sandbox Member", "email": email, "org_role": org_role},
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), email


async def test_add_instructor_grants_org_role_without_global_instructor(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, _email = await _add_member(db, client, owner, org_role="instructor")

    assert body["org_role"] == "instructor"
    from sqlalchemy import select

    member = (await db.execute(select(User).where(User.id == uuid.UUID(body["id"])))).scalars().first()
    assert member.org_role == "instructor"
    assert "organization" in member.role_values
    assert "instructor" not in member.role_values


async def test_add_judge_grants_org_role_without_global_judge(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, _email = await _add_member(db, client, owner, org_role="judge")

    from sqlalchemy import select

    member = (await db.execute(select(User).where(User.id == uuid.UUID(body["id"])))).scalars().first()
    assert member.org_role == "judge"
    assert "organization" in member.role_values
    assert "judge" not in member.role_values


async def test_team_list_hides_students_who_are_merely_affiliated(db, client):
    owner, org = await _seed_org(db)
    student = await _make_user(db, roles=["student"])
    student.organization_id = org.id
    await db.flush()

    resp = await client.get("/organization/team", headers=_headers(owner))
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    assert str(owner.id) in ids
    assert str(student.id) not in ids
    owner_row = next(row for row in resp.json() if row["id"] == str(owner.id))
    assert owner_row["org_role"] == "owner"


async def test_patch_team_member_role(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, _email = await _add_member(db, client, owner, org_role="coordinator")

    resp = await client.patch(
        f"/organization/team/{body['id']}",
        headers=_headers(owner),
        json={"org_role": "judge"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["org_role"] == "judge"

    from sqlalchemy import select

    member = (await db.execute(select(User).where(User.id == uuid.UUID(body["id"])))).scalars().first()
    assert member.org_role == "judge"
    assert "organization" in member.role_values
    assert "judge" not in member.role_values


async def test_instructor_cannot_manage_team(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, member_email = await _add_member(db, client, owner, org_role="instructor")
    from sqlalchemy import select

    member = (await db.execute(select(User).where(User.id == uuid.UUID(body["id"])))).scalars().first()

    resp = await client.post(
        "/organization/team",
        headers=_headers(member),
        json={"full_name": "Nope", "email": f"nope-{uuid.uuid4().hex[:6]}@example.com"},
    )
    assert resp.status_code == 403


async def test_remove_member_detaches_instead_of_deleting(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, _email = await _add_member(db, client, owner, org_role="instructor")

    resp = await client.delete(f"/organization/team/{body['id']}", headers=_headers(owner))
    assert resp.status_code == 204, resp.text

    from sqlalchemy import select

    member = (await db.execute(select(User).where(User.id == uuid.UUID(body["id"])))).scalars().first()
    assert member is not None  # account survives
    assert member.organization_id is None
    assert member.org_role is None
    assert "organization" not in member.role_values
    assert "instructor" not in member.role_values
    assert member.role_values == ["student"]


async def test_assign_instructor_to_cohort_and_sessions(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, _email = await _add_member(db, client, owner, org_role="instructor")
    instructor_id = uuid.UUID(body["id"])
    _program, cohort, sessions = await _seed_cohort(db, org, sessions=2)

    resp = await client.post(
        f"/organization/cohorts/{cohort.id}/instructors",
        headers=_headers(owner),
        json={"user_id": str(instructor_id)},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["assigned"] == 2

    from sqlalchemy import func, select

    count = await db.scalar(
        select(func.count(SessionInstructor.id)).where(SessionInstructor.user_id == instructor_id)
    )
    assert count == 2

    staff = await client.get(f"/organization/cohorts/{cohort.id}/staff", headers=_headers(owner))
    assert staff.status_code == 200, staff.text
    row = next(r for r in staff.json()["instructors"] if r["user_id"] == str(instructor_id))
    assert row["sessions_count"] == 2


async def test_assign_judge_to_cohort(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, _email = await _add_member(db, client, owner, org_role="judge")
    _program, cohort, _sessions = await _seed_cohort(db, org)

    resp = await client.post(
        f"/organization/cohorts/{cohort.id}/judges",
        headers=_headers(owner),
        json={"user_id": body["id"]},
    )
    assert resp.status_code == 201, resp.text

    from sqlalchemy import select

    row = (
        await db.execute(
            select(CompetitionJudge).where(
                CompetitionJudge.cohort_id == cohort.id,
                CompetitionJudge.user_id == uuid.UUID(body["id"]),
            )
        )
    ).scalars().first()
    assert row is not None


async def test_set_and_read_cohort_readiness(db, client, sent_emails):
    owner, org = await _seed_org(db)
    _program, cohort, _sessions = await _seed_cohort(db, org)
    preset = PreSessionQuizPreset(id=uuid.uuid4(), name="Readiness", question_ids=[], organization_id=org.id)
    db.add(preset)
    await db.flush()

    resp = await client.put(
        f"/organization/cohorts/{cohort.id}/readiness",
        headers=_headers(owner),
        json={"preset_id": str(preset.id)},
    )
    assert resp.status_code == 200, resp.text

    from sqlalchemy import select

    assign = (
        await db.execute(
            select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.cohort_id == cohort.id)
        )
    ).scalars().first()
    assert assign is not None and assign.preset_id == preset.id

    read = await client.get(f"/organization/cohorts/{cohort.id}/readiness", headers=_headers(owner))
    assert read.status_code == 200, read.text
    assert read.json()["preset"]["name"] == "Readiness"


async def test_spacepoint_instructor_keeps_payouts_and_splits_sessions_by_scope(db, client, sent_emails):
    owner, org = await _seed_org(db)
    sp_instructor = await _make_user(db, roles=["instructor"])

    from sqlalchemy import select

    role = (await db.execute(select(DeliveryRole).limit(1))).scalars().first()
    if role is None:
        role = DeliveryRole(id=uuid.uuid4(), name=f"Lead {uuid.uuid4().hex[:6]}", sort_order=1, is_active=True)
        db.add(role)
        await db.flush()

    sp_program = Program(
        id=uuid.uuid4(),
        code=f"SP-{uuid.uuid4().hex[:6]}",
        name="SpacePoint Program",
        program_type="workshop",
        pricing_model="free",
    )
    db.add(sp_program)
    await db.flush()
    sp_cohort = Cohort(id=uuid.uuid4(), program_id=sp_program.id, name="SP Cohort", status="running")
    db.add(sp_cohort)
    await db.flush()
    sp_session = Session(
        id=uuid.uuid4(),
        cohort_id=sp_cohort.id,
        title="SpacePoint Day 1",
        meeting_date=date.today(),
        staffing_status="staffed",
    )
    db.add(sp_session)
    await db.flush()
    db.add(SessionInstructor(session_id=sp_session.id, user_id=sp_instructor.id, role_id=role.id))
    await db.flush()

    _org_program, org_cohort, org_sessions = await _seed_cohort(db, org, sessions=1)

    invite = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={"full_name": sp_instructor.full_name, "email": sp_instructor.email, "org_role": "instructor"},
    )
    assert invite.status_code == 201, invite.text

    assign = await client.post(
        f"/organization/cohorts/{org_cohort.id}/instructors",
        headers=_headers(owner),
        json={"user_id": str(sp_instructor.id)},
    )
    assert assign.status_code == 201, assign.text

    await db.refresh(sp_instructor)
    assert "instructor" in sp_instructor.role_values
    assert "organization" in sp_instructor.role_values
    assert sp_instructor.org_role == "instructor"

    org_mine = await client.get("/sessions/mine?scope=org", headers=_headers(sp_instructor))
    assert org_mine.status_code == 200, org_mine.text
    assert [row["session_id"] for row in org_mine.json()] == [str(org_sessions[0].id)]

    sp_mine = await client.get("/sessions/mine?scope=spacepoint", headers=_headers(sp_instructor))
    assert sp_mine.status_code == 200, sp_mine.text
    assert [row["session_id"] for row in sp_mine.json()] == [str(sp_session.id)]

    pay = await client.get("/instructors/payments/summary", headers=_headers(sp_instructor))
    assert pay.status_code == 200, pay.text

    detach = await client.delete(f"/organization/team/{sp_instructor.id}", headers=_headers(owner))
    assert detach.status_code == 204, detach.text
    await db.refresh(sp_instructor)
    assert "organization" not in sp_instructor.role_values
    assert "instructor" in sp_instructor.role_values
    assert sp_instructor.org_role is None


async def test_org_only_instructor_delivery_and_sandbox_isolation(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, _email = await _add_member(db, client, owner, org_role="instructor")
    instructor_id = uuid.UUID(body["id"])
    _program, cohort, sessions = await _seed_cohort(db, org, sessions=1)

    assign = await client.post(
        f"/organization/cohorts/{cohort.id}/instructors",
        headers=_headers(owner),
        json={"user_id": str(instructor_id)},
    )
    assert assign.status_code == 201, assign.text

    from sqlalchemy import select

    org_inst = (await db.execute(select(User).where(User.id == instructor_id))).scalars().first()

    mine = await client.get("/sessions/mine?scope=org", headers=_headers(org_inst))
    assert mine.status_code == 200, mine.text
    assert [row["session_id"] for row in mine.json()] == [str(sessions[0].id)]

    delivery = await client.get(f"/sessions/{sessions[0].id}/delivery", headers=_headers(org_inst))
    assert delivery.status_code == 200, delivery.text

    pay = await client.get("/instructors/payments/summary", headers=_headers(org_inst))
    assert pay.status_code == 403

    avail = await client.get("/sessions/available", headers=_headers(org_inst))
    assert avail.status_code == 403


async def test_org_only_judge_scoped_and_blocked_from_admin(db, client, sent_emails):
    owner, org = await _seed_org(db)
    body, _email = await _add_member(db, client, owner, org_role="judge")
    judge_id = uuid.UUID(body["id"])
    _program, cohort, _sessions = await _seed_cohort(db, org)

    assign = await client.post(
        f"/organization/cohorts/{cohort.id}/judges",
        headers=_headers(owner),
        json={"user_id": str(judge_id)},
    )
    assert assign.status_code == 201, assign.text

    # Add an external SpacePoint competition assignment; scope=org must exclude it.
    ext_prog = Program(
        id=uuid.uuid4(),
        code=f"EXT-{uuid.uuid4().hex[:6]}",
        name="External Comp",
        program_type="competition",
        pricing_model="free",
    )
    db.add(ext_prog)
    await db.flush()
    ext_cohort = Cohort(id=uuid.uuid4(), program_id=ext_prog.id, name="Ext Cohort", status="running")
    db.add(ext_cohort)
    await db.flush()
    db.add(CompetitionJudge(cohort_id=ext_cohort.id, user_id=judge_id))
    await db.flush()

    from sqlalchemy import select

    org_judge = (await db.execute(select(User).where(User.id == judge_id))).scalars().first()

    cohorts_resp = await client.get("/competitions/judge/cohorts?scope=org", headers=_headers(org_judge))
    assert cohorts_resp.status_code == 200, cohorts_resp.text
    assert [c["id"] for c in cohorts_resp.json()] == [str(cohort.id)]

    admin_rubric = await client.get(f"/competitions/admin/cohorts/{cohort.id}/rubric", headers=_headers(org_judge))
    assert admin_rubric.status_code == 403


async def test_org_assignable_students_scoped_to_own_org(db, client):
    """Assign tab must never expose the platform user table to an org.

    An org manager sees only accounts already tied to their org; a stranger's
    student account stays invisible, and its UUID can't be force-registered
    into the org's cohort either.
    """
    owner, org = await _seed_org(db)
    _program, cohort, _ = await _seed_cohort(db, org)
    own = await _make_user(db, roles=["student"], email=f"own-{uuid.uuid4().hex[:8]}@example.com")
    own.organization_id = org.id
    outsider = await _make_user(db, roles=["student"], email=f"out-{uuid.uuid4().hex[:8]}@example.com")
    staff = await _make_user(db, roles=["organization"], email=f"staff-{uuid.uuid4().hex[:8]}@example.com")
    staff.organization_id = org.id
    staff.org_role = "instructor"
    observer = await _make_user(db, roles=["organization"], email=f"obs-{uuid.uuid4().hex[:8]}@example.com")
    observer.organization_id = org.id
    observer.org_role = "observer"
    await db.commit()

    resp = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "student", "page_size": 100}, headers=_headers(owner),
    )
    assert resp.status_code == 200, resp.text
    ids = {r["id"] for r in resp.json()["items"]}
    assert str(own.id) in ids
    assert str(outsider.id) not in ids

    # Org sandbox roles live in `org_role`, not the global `roles` array.
    staff_resp = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "staff", "page_size": 100}, headers=_headers(owner),
    )
    assert staff_resp.status_code == 200, staff_resp.text
    staff_ids = {r["id"] for r in staff_resp.json()["items"]}
    assert str(staff.id) in staff_ids
    assert str(observer.id) not in staff_ids
    assert str(outsider.id) not in staff_ids

    narrowed = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "staff", "role": "instructor", "page_size": 100},
        headers=_headers(owner),
    )
    assert narrowed.status_code == 200, narrowed.text
    assert {r["id"] for r in narrowed.json()["items"]} == {str(staff.id)}

    obs_resp = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "observer", "page_size": 100}, headers=_headers(owner),
    )
    assert obs_resp.status_code == 200, obs_resp.text
    obs_ids = {r["id"] for r in obs_resp.json()["items"]}
    assert str(observer.id) in obs_ids
    assert str(staff.id) not in obs_ids
    assert str(outsider.id) not in obs_ids

    add = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/register-users",
        headers=_headers(owner), json={"user_ids": [str(outsider.id)]},
    )
    assert add.status_code == 404, add.text


async def test_org_cohort_assignable_students_scoped_even_for_ops_and_admin(db, client):
    """Partner organization cohorts must never leak portal-wide users in Assign,
    even when opened by SpacePoint Admin/Operations or a dual-role caller, and
    even if an admin previously clicked 'Try as Observer' on that cohort.
    """
    from app.models.lms.program import LmsProgram, LmsProgramAssignment

    owner, org = await _seed_org(db)
    other_owner, other_org = await _seed_org(db)
    program, cohort, _ = await _seed_cohort(db, org)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Org Checklist")
    db.add(lms_program)
    await db.flush()

    admin = await _make_user(db, roles=["admin", "observer"], email=f"adm-{uuid.uuid4().hex[:8]}@example.com")
    dual_role_owner = await _make_user(
        db, roles=["admin", "organization"], email=f"dual-{uuid.uuid4().hex[:8]}@example.com"
    )
    dual_role_owner.organization_id = org.id
    dual_role_owner.org_role = "coordinator"

    portal_instructor = await _make_user(db, roles=["instructor"], email=f"spinst-{uuid.uuid4().hex[:8]}@example.com")
    portal_student = await _make_user(db, roles=["student"], email=f"spstu-{uuid.uuid4().hex[:8]}@example.com")

    other_org_staff = await _make_user(db, roles=["organization"], email=f"otherstaff-{uuid.uuid4().hex[:8]}@example.com")
    other_org_staff.organization_id = other_org.id
    other_org_staff.org_role = "instructor"

    own_student = await _make_user(db, roles=["student"], email=f"ownstu-{uuid.uuid4().hex[:8]}@example.com")
    own_student.organization_id = org.id
    own_staff = await _make_user(db, roles=["organization"], email=f"ownstaff-{uuid.uuid4().hex[:8]}@example.com")
    own_staff.organization_id = org.id
    own_staff.org_role = "instructor"
    own_observer = await _make_user(db, roles=["organization"], email=f"ownobs-{uuid.uuid4().hex[:8]}@example.com")
    own_observer.organization_id = org.id
    own_observer.org_role = "observer"

    # Simulate SpacePoint admin having used "Try as Observer" on this org cohort.
    db.add(
        LmsProgramAssignment(
            id=uuid.uuid4(),
            lms_program_id=lms_program.id,
            user_id=admin.id,
            cohort_id=cohort.id,
            mode="observer",
        )
    )
    await db.commit()

    for caller in (admin, dual_role_owner):
        staff_resp = await client.get(
            f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
            params={"mode": "staff", "page_size": 100}, headers=_headers(caller),
        )
        assert staff_resp.status_code == 200, staff_resp.text
        staff_ids = {r["id"] for r in staff_resp.json()["items"]}
        assert str(own_staff.id) in staff_ids
        assert str(dual_role_owner.id) in staff_ids
        assert str(owner.id) in staff_ids
        assert str(admin.id) not in staff_ids
        assert str(portal_instructor.id) not in staff_ids
        assert str(other_org_staff.id) not in staff_ids
        assert str(other_owner.id) not in staff_ids

        stu_resp = await client.get(
            f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
            params={"mode": "student", "page_size": 100}, headers=_headers(caller),
        )
        assert stu_resp.status_code == 200, stu_resp.text
        stu_ids = {r["id"] for r in stu_resp.json()["items"]}
        assert str(own_student.id) in stu_ids
        assert str(portal_student.id) not in stu_ids

        obs_resp = await client.get(
            f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
            params={"mode": "observer", "page_size": 100}, headers=_headers(caller),
        )
        assert obs_resp.status_code == 200, obs_resp.text
        obs_ids = {r["id"] for r in obs_resp.json()["items"]}
        assert str(own_observer.id) in obs_ids
        assert str(admin.id) not in obs_ids

    forbid_reg = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/register-users",
        headers=_headers(admin), json={"user_ids": [str(portal_student.id)]},
    )
    assert forbid_reg.status_code == 404, forbid_reg.text


async def test_org_lms_students_and_assign_scoped_to_org_cohorts_and_invite_codes(db, client):
    """Org Students page (/lms/admin/students) and Assign tab only expose students
    in the org's cohorts or who redeemed an org invite code — never portal-wide
    students, CRM-contact-only links, or SpacePoint-admin batches, even when a
    multi-role admin switches active role to 'organization'.
    """
    from app.models.instructors.invitation_code import InvitationCode
    from app.models.lms.invite_grant import InvitationCodeGrant, UserInvitationCode
    from app.models.sessions.registration import Registration
    from app.models.spine.contact import Contact

    owner, org = await _seed_org(db)
    _program, cohort, _ = await _seed_cohort(db, org)

    dual_admin = await _make_user(
        db, roles=["admin", "organization"], email=f"dualadm-{uuid.uuid4().hex[:8]}@example.com"
    )
    dual_admin.organization_id = org.id
    dual_admin.org_role = "coordinator"

    # 1. Student registered in one of the org's cohorts
    cohort_contact = Contact(
        id=uuid.uuid4(), full_name="Cohort Student", email=f"cstu-{uuid.uuid4().hex[:8]}@example.com",
        contact_roles=["student"],
    )
    db.add(cohort_contact)
    await db.flush()
    cohort_student = await _make_user(db, roles=["student"], email=cohort_contact.email)
    cohort_student.contact_id = cohort_contact.id
    db.add(Registration(
        id=uuid.uuid4(), cohort_id=cohort.id, contact_id=cohort_contact.id,
        status="registered", ticket_token=f"TK-{uuid.uuid4().hex[:10]}",
        registered_via="desk", payment_status="waived",
    ))

    # 2. Student who used an organization-created invite code (no cohort registration yet)
    org_code = InvitationCode(
        id=uuid.uuid4(), code=f"ORGBATCH-{uuid.uuid4().hex[:6].upper()}",
        kind="student", label="Org Batch", is_active=True, max_uses=20, created_by=owner.id,
    )
    db.add(org_code)
    await db.flush()
    code_student = await _make_user(db, roles=["student"], email=f"codestu-{uuid.uuid4().hex[:8]}@example.com")
    code_student.invitation_code_used = org_code.code
    db.add(UserInvitationCode(
        id=uuid.uuid4(), user_id=code_student.id, invitation_code_id=org_code.id, code=org_code.code,
    ))

    # 3. Student who used a grant-linked org cohort invite code
    grant_code = InvitationCode(
        id=uuid.uuid4(), code=f"GRANT-{uuid.uuid4().hex[:6].upper()}",
        kind="student", label="Granted Batch", is_active=True, max_uses=20, created_by=dual_admin.id,
    )
    db.add(grant_code)
    await db.flush()
    db.add(InvitationCodeGrant(
        id=uuid.uuid4(), invitation_code_id=grant_code.id, product_type="lms_program", cohort_id=cohort.id,
    ))
    grant_student = await _make_user(db, roles=["student"], email=f"gstu-{uuid.uuid4().hex[:8]}@example.com")
    grant_student.invitation_code_used = grant_code.code

    # 4. SpacePoint platform invite code + student + CRM-contact-only student (must stay hidden)
    sp_code = InvitationCode(
        id=uuid.uuid4(), code=f"SPBATCH-{uuid.uuid4().hex[:6].upper()}",
        kind="student", label="SP Batch", is_active=True, max_uses=20, created_by=dual_admin.id,
    )
    db.add(sp_code)
    sp_student = await _make_user(db, roles=["student"], email=f"spbatch-{uuid.uuid4().hex[:8]}@example.com")
    sp_student.invitation_code_used = sp_code.code

    crm_contact = Contact(
        id=uuid.uuid4(), full_name="CRM Only", email=f"crm-{uuid.uuid4().hex[:8]}@example.com",
        contact_roles=["student"], organization_id=org.id,
    )
    db.add(crm_contact)
    await db.flush()
    crm_only_student = await _make_user(db, roles=["student"], email=crm_contact.email)
    crm_only_student.contact_id = crm_contact.id

    await db.commit()

    org_headers_cases = [
        _headers(owner),
        {**_headers(dual_admin), "X-Active-Role": "organization"},
    ]
    for hdrs in org_headers_cases:
        resp = await client.get("/lms/admin/students", headers=hdrs)
        assert resp.status_code == 200, resp.text
        ids = {r["id"] for r in resp.json()}
        assert str(cohort_student.id) in ids
        assert str(code_student.id) in ids
        assert str(grant_student.id) in ids
        assert str(sp_student.id) not in ids
        assert str(crm_only_student.id) not in ids

        detail = await client.get(f"/lms/admin/students/{sp_student.id}", headers=hdrs)
        assert detail.status_code == 404

        codes_resp = await client.get("/lms/admin/invite-codes", headers=hdrs)
        assert codes_resp.status_code == 200, codes_resp.text
        code_names = {c["code"] for c in codes_resp.json()}
        assert org_code.code in code_names
        assert grant_code.code in code_names
        assert sp_code.code not in code_names

    assign_resp = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "student", "page_size": 100},
        headers=_headers(dual_admin),
    )
    assert assign_resp.status_code == 200, assign_resp.text
    assign_ids = {r["id"] for r in assign_resp.json()["items"]}
    assert str(cohort_student.id) in assign_ids
    assert str(code_student.id) in assign_ids
    assert str(grant_student.id) in assign_ids
    assert str(sp_student.id) not in assign_ids
    assert str(crm_only_student.id) not in assign_ids

    assign_codes = await client.get(
        "/lms/admin/invite-codes", params={"cohort_id": str(cohort.id)}, headers=_headers(dual_admin),
    )
    assert assign_codes.status_code == 200, assign_codes.text
    assign_code_names = {c["code"] for c in assign_codes.json()}
    assert org_code.code in assign_code_names
    assert grant_code.code in assign_code_names
    assert sp_code.code not in assign_code_names


async def test_org_cohorts_excluded_from_ops_main_lists(db, client):
    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])
    org_program, org_cohort, _ = await _seed_cohort(db, org)

    sp_program = Program(
        id=uuid.uuid4(),
        code=f"SP-{uuid.uuid4().hex[:6]}",
        name="SpacePoint Core",
        program_type="workshop",
        pricing_model="free",
    )
    db.add(sp_program)
    await db.flush()
    sp_cohort = Cohort(id=uuid.uuid4(), program_id=sp_program.id, name="SP Cohort", status="running")
    db.add(sp_cohort)
    await db.flush()

    cohorts_resp = await client.get("/sessions/cohorts", headers=_headers(ops))
    assert cohorts_resp.status_code == 200, cohorts_resp.text
    cohort_ids = {c["id"] for c in cohorts_resp.json()}
    assert str(sp_cohort.id) in cohort_ids
    assert str(org_cohort.id) not in cohort_ids

    programs_resp = await client.get("/sessions/programs", headers=_headers(ops))
    assert programs_resp.status_code == 200, programs_resp.text
    prog_ids = {p["id"] for p in programs_resp.json()}
    assert str(sp_program.id) in prog_ids
    assert str(org_program.id) not in prog_ids


async def test_ops_co_managing_org_cohort_resolves_cohort_org_and_staff(db, client, sent_emails):
    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])
    inst_unassigned, _ = await _add_member(db, client, owner, org_role="instructor")
    inst_assigned, _ = await _add_member(db, client, owner, org_role="instructor")
    _program, cohort, sessions = await _seed_cohort(db, org, sessions=1)

    assign = await client.post(
        f"/organization/cohorts/{cohort.id}/instructors",
        headers=_headers(ops),
        json={"user_id": inst_assigned["id"], "session_ids": [str(sessions[0].id)]},
    )
    assert assign.status_code == 201, assign.text

    staff = await client.get(f"/organization/cohorts/{cohort.id}/staff", headers=_headers(ops))
    assert staff.status_code == 200, staff.text
    staff_body = staff.json()
    assert [i["user_id"] for i in staff_body["instructors"]] == [inst_assigned["id"]]
    assert [i["user_id"] for i in staff_body["sessions"][0]["instructors"]] == [inst_assigned["id"]]
    assert staff_body["sessions"][0]["attendance_total"] == 0

    team_resp = await client.get(f"/organization/team?cohort_id={cohort.id}", headers=_headers(ops))
    assert team_resp.status_code == 200, team_resp.text
    team_ids = {m["id"] for m in team_resp.json()}
    assert inst_unassigned["id"] in team_ids
    assert inst_assigned["id"] in team_ids


async def test_org_manager_can_access_progress_tab_roster(db, client):
    owner, org = await _seed_org(db)
    _program, cohort, _ = await _seed_cohort(db, org)

    roster = await client.get(f"/lms/instructor/cohorts/{cohort.id}/program-progress", headers=_headers(owner))
    assert roster.status_code == 200, roster.text


async def test_invite_judge_on_org_cohort_stays_in_org_sandbox(db, client, sent_emails):
    owner, org = await _seed_org(db)
    _program, cohort, _ = await _seed_cohort(db, org)
    judge_email = f"org-judge-{uuid.uuid4().hex[:8]}@example.com"

    resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/judges",
        headers=_headers(owner),
        json={"name": "Org Sandbox Judge", "email": judge_email, "send_email": False},
    )
    assert resp.status_code == 201, resp.text

    from sqlalchemy import select

    judge = (await db.execute(select(User).where(User.email == judge_email))).scalars().first()
    assert judge is not None
    assert judge.organization_id == org.id
    assert judge.org_role == "judge"
    assert "organization" in judge.role_values
    assert "judge" not in judge.role_values


async def test_admin_can_update_and_remove_org_only_member_and_observer(db, client, sent_emails):
    from sqlalchemy import select
    from app.models.lms.program import CohortLmsEditor, LmsProgram, LmsProgramAssignment

    owner, org = await _seed_org(db)
    admin = await _make_user(db, roles=["admin"])
    program, cohort, _ = await _seed_cohort(db, org)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Org Checklist")
    db.add(lms_program)
    await db.flush()

    # 1. Org-only member (organization was their only role)
    body, _email = await _add_member(db, client, owner, org_role="coordinator")
    member_id = uuid.UUID(body["id"])
    db.add(CohortLmsEditor(cohort_id=cohort.id, user_id=member_id))
    await db.flush()

    patch_resp = await client.patch(
        f"/admin/website/organizations/{org.id}/members/{member_id}",
        headers=_headers(admin),
        json={"org_role": "judge"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["org_role"] == "judge"

    del_resp = await client.delete(
        f"/admin/website/organizations/{org.id}/members/{member_id}",
        headers=_headers(admin),
    )
    assert del_resp.status_code == 204, del_resp.text

    member = (await db.execute(select(User).where(User.id == member_id))).scalars().first()
    assert member is not None
    assert member.organization_id is None
    assert member.org_role is None
    assert "organization" not in member.role_values
    assert member.role_values == ["student"]
    assert (
        await db.execute(select(CohortLmsEditor).where(CohortLmsEditor.user_id == member_id))
    ).scalars().first() is None

    # 2. Observer linked only via cohort observer assignment (without organization_id)
    obs = await _make_user(db, roles=["observer"])
    db.add(
        LmsProgramAssignment(
            id=uuid.uuid4(),
            lms_program_id=lms_program.id,
            user_id=obs.id,
            cohort_id=cohort.id,
            mode="observer",
        )
    )
    await db.flush()

    obs_patch = await client.patch(
        f"/admin/website/organizations/{org.id}/members/{obs.id}",
        headers=_headers(admin),
        json={"org_role": "instructor"},
    )
    assert obs_patch.status_code == 200, obs_patch.text
    assert obs_patch.json()["org_role"] == "instructor"

    obs_del = await client.delete(
        f"/admin/website/organizations/{org.id}/members/{obs.id}",
        headers=_headers(admin),
    )
    assert obs_del.status_code == 204, obs_del.text

    await db.refresh(obs)
    assert obs.organization_id is None
    assert obs.org_role is None
    assert obs.role_values == ["student"]


async def test_admin_create_org_account_and_readiness_assessment_scoping(db, client, sent_emails):
    admin = await _make_user(db, roles=["admin"])

    sp_allowed = PreSessionQuizPreset(id=uuid.uuid4(), name="SP Allowed Readiness", question_ids=[])
    sp_hidden = PreSessionQuizPreset(id=uuid.uuid4(), name="SP Hidden Readiness", question_ids=[])
    db.add_all([sp_allowed, sp_hidden])
    await db.flush()

    create_resp = await client.post(
        "/admin/website/organizations/account",
        headers=_headers(admin),
        json={
            "org_name_latin": "Readiness Partner Org",
            "org_type": "university",
            "country": "uae",
            "city": "Abu Dhabi",
            "full_name": "Org Lead",
            "email": f"readiness-org-{uuid.uuid4().hex[:8]}@example.com",
            "password": "StrongPassword123",
            "is_approved": True,
            "readiness_scope": "selected",
            "allowed_readiness_preset_ids": [str(sp_allowed.id)],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    org_body = create_resp.json()
    assert org_body["readiness_scope"] == "selected"
    assert org_body["allowed_readiness_preset_ids"] == [str(sp_allowed.id)]

    org = await db.get(Organization, uuid.UUID(org_body["id"]))
    owner = await db.get(User, uuid.UUID(org_body["owner_user_id"]))
    _program, cohort, _ = await _seed_cohort(db, org)

    # Org sees only sp_allowed (not sp_hidden)
    presets_resp = await client.get(
        f"/organization/readiness-presets?cohort_id={cohort.id}",
        headers=_headers(owner),
    )
    assert presets_resp.status_code == 200, presets_resp.text
    preset_ids = {p["id"] for p in presets_resp.json()}
    assert str(sp_allowed.id) in preset_ids
    assert str(sp_hidden.id) not in preset_ids

    # Assigning sp_hidden is forbidden for org
    forbid_resp = await client.put(
        f"/organization/cohorts/{cohort.id}/readiness",
        headers=_headers(owner),
        json={"preset_id": str(sp_hidden.id)},
    )
    assert forbid_resp.status_code == 403

    # Org can create its own readiness assessment and assign it
    own_resp = await client.post(
        "/organization/readiness-presets",
        headers=_headers(owner),
        json={
            "name": "Partner Custom Safety Check",
            "description": "Custom org quiz",
            "passing_score_percent": 80,
            "cohort_id": str(cohort.id),
            "questions": [
                {
                    "prompt": "What is the safe ESD practice?",
                    "question_type": "mcq",
                    "options": [
                        {"text": "Use an ESD wrist strap", "is_correct": True},
                        {"text": "Touch pins directly", "is_correct": False},
                    ],
                }
            ],
        },
    )
    assert own_resp.status_code == 201, own_resp.text
    own_preset = own_resp.json()
    assert own_preset["is_own"] is True
    assert own_preset["question_count"] == 1

    assign_own = await client.put(
        f"/organization/cohorts/{cohort.id}/readiness",
        headers=_headers(owner),
        json={"preset_id": own_preset["id"]},
    )
    assert assign_own.status_code == 200, assign_own.text


async def test_org_shared_courses_visible_and_read_only(db, client, sent_emails):
    from app.models.lms.course import Course

    owner, org = await _seed_org(db)
    admin = await _make_user(db, roles=["admin"])

    shared_course = Course(
        id=uuid.uuid4(),
        title="Shared Platform Course",
        created_by=admin.id,
        organization_id=None,
        is_published=True,
    )
    hidden_course = Course(
        id=uuid.uuid4(),
        title="Hidden Platform Course",
        created_by=admin.id,
        organization_id=None,
        is_published=True,
    )
    db.add_all([shared_course, hidden_course])
    await db.flush()

    org.allowed_course_ids = [str(shared_course.id)]
    org.can_author_courses = True
    org_course = Course(
        id=uuid.uuid4(),
        title="Org Own Course",
        created_by=owner.id,
        organization_id=org.id,
        is_published=False,
    )
    db.add(org_course)
    await db.flush()

    list_resp = await client.get("/lms/admin/courses", headers=_headers(owner))
    assert list_resp.status_code == 200, list_resp.text
    by_id = {c["id"]: c for c in list_resp.json()}
    assert str(shared_course.id) in by_id
    assert str(hidden_course.id) not in by_id
    assert by_id[str(shared_course.id)]["can_edit"] is False
    assert by_id[str(org_course.id)]["can_edit"] is True

    detail_resp = await client.get(f"/lms/admin/courses/{shared_course.id}", headers=_headers(owner))
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["can_edit"] is False

    mods_resp = await client.get(f"/lms/admin/courses/{shared_course.id}/modules", headers=_headers(owner))
    assert mods_resp.status_code == 200, mods_resp.text

    patch_resp = await client.patch(
        f"/lms/admin/courses/{shared_course.id}",
        headers=_headers(owner),
        json={"title": "Hacked"},
    )
    assert patch_resp.status_code == 404

    # Invite email copy no longer mentions managing programs, cohorts and landing pages
    await _add_member(db, client, owner, org_role="instructor")
    assert len(sent_emails) == 1
    assert "programs, cohorts and landing pages" not in sent_emails[0][2]


async def test_multi_role_org_member_create_patch_staffing_and_delete(db, client, sent_emails):
    from sqlalchemy import select

    owner, org = await _seed_org(db)
    _program, cohort, sessions = await _seed_cohort(db, org, sessions=2)
    email = f"multi-{uuid.uuid4().hex[:8]}@example.com"

    # Create with multiple org roles (sent unsorted; API canonicalizes order).
    create_resp = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={
            "full_name": "Multi Role Member",
            "email": email,
            "org_roles": ["judge", "instructor", "coordinator"],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["org_roles"] == ["coordinator", "instructor", "judge"]
    assert created["org_role"] == "coordinator"
    member_id = uuid.UUID(created["id"])

    member = (await db.execute(select(User).where(User.id == member_id))).scalars().first()
    assert member is not None
    assert member.org_roles == ["coordinator", "instructor", "judge"]
    assert member.org_role == "coordinator"
    # Never leaks SpacePoint freelance global instructor/judge roles.
    assert "organization" in member.role_values
    assert "instructor" not in member.role_values
    assert "judge" not in member.role_values

    # Team management is owner-only (coordinators are blocked from /organization/team
    # so they cannot change other members' roles), while /organization/coordinators is
    # readable, and instructor session staffing + cohort judge assignment still work.
    coord_team_resp = await client.get("/organization/team", headers=_headers(member))
    assert coord_team_resp.status_code == 403
    coords_resp = await client.get("/organization/coordinators", headers=_headers(member))
    assert coords_resp.status_code == 200, coords_resp.text
    assert any(r["id"] == str(member_id) for r in coords_resp.json())

    team_resp = await client.get("/organization/team", headers=_headers(owner))
    assert team_resp.status_code == 200, team_resp.text
    member_row = next(r for r in team_resp.json() if r["id"] == str(member_id))
    assert member_row["org_roles"] == ["coordinator", "instructor", "judge"]

    inst_resp = await client.post(
        f"/organization/cohorts/{cohort.id}/instructors",
        headers=_headers(owner),
        json={"user_id": str(member_id)},
    )
    assert inst_resp.status_code == 201, inst_resp.text
    assert inst_resp.json()["assigned"] == len(sessions)

    judge_resp = await client.post(
        f"/organization/cohorts/{cohort.id}/judges",
        headers=_headers(owner),
        json={"user_id": str(member_id)},
    )
    assert judge_resp.status_code == 201, judge_resp.text
    assert judge_resp.json()["assigned"] is True

    # Empty org_roles rejected; assigning owner to non-owner rejected.
    empty_patch = await client.patch(
        f"/organization/team/{member_id}",
        headers=_headers(owner),
        json={"org_roles": []},
    )
    assert empty_patch.status_code == 422

    owner_patch = await client.patch(
        f"/organization/team/{member_id}",
        headers=_headers(owner),
        json={"org_roles": ["owner", "instructor"]},
    )
    assert owner_patch.status_code == 422

    # Update via multi-role PATCH and legacy single org_role PATCH.
    multi_patch = await client.patch(
        f"/organization/team/{member_id}",
        headers=_headers(owner),
        json={"org_roles": ["observer", "instructor"]},
    )
    assert multi_patch.status_code == 200, multi_patch.text
    assert multi_patch.json()["org_roles"] == ["instructor", "observer"]
    assert multi_patch.json()["org_role"] == "instructor"

    legacy_patch = await client.patch(
        f"/organization/team/{member_id}",
        headers=_headers(owner),
        json={"org_role": "judge"},
    )
    assert legacy_patch.status_code == 200, legacy_patch.text
    assert legacy_patch.json()["org_roles"] == ["judge"]
    assert legacy_patch.json()["org_role"] == "judge"

    # Detach clears both org_role and org_roles.
    del_resp = await client.delete(f"/organization/team/{member_id}", headers=_headers(owner))
    assert del_resp.status_code == 204
    await db.refresh(member)
    assert member.org_role is None
    assert member.org_roles == []


async def test_primary_owner_extra_roles_locked_owner_and_ops_detail(db, client):
    from app.services.sessions.staffing import list_eligible_instructors

    owner, org = await _seed_org(db)
    admin = await _make_user(db, roles=["admin"])
    _program, cohort, sessions = await _seed_cohort(db, org, sessions=1)

    # Org self-service PATCH allows owner to add instructor/judge while keeping owner locked.
    patch_owner = await client.patch(
        f"/organization/team/{owner.id}",
        headers=_headers(owner),
        json={"org_roles": ["instructor", "coordinator"]},
    )
    assert patch_owner.status_code == 200, patch_owner.text
    body = patch_owner.json()
    assert body["is_owner"] is True
    assert body["org_roles"] == ["owner", "instructor"]
    assert body["org_role"] == "owner"

    # Passing empty list to owner still retains locked "owner" without stripping it.
    clear_attempt = await client.patch(
        f"/organization/team/{owner.id}",
        headers=_headers(owner),
        json={"org_roles": []},
    )
    assert clear_attempt.status_code == 200, clear_attempt.text
    assert clear_attempt.json()["org_roles"] == ["owner"]

    # Ops PATCH can add instructor + judge onto the primary owner.
    ops_patch = await client.patch(
        f"/admin/website/organizations/{org.id}/members/{owner.id}",
        headers=_headers(admin),
        json={"org_roles": ["judge", "instructor"]},
    )
    assert ops_patch.status_code == 200, ops_patch.text
    assert ops_patch.json()["is_owner"] is True
    assert ops_patch.json()["org_roles"] == ["owner", "instructor", "judge"]
    assert ops_patch.json()["org_role"] == "owner"

    # Owner with instructor role can be staffed on cohort sessions and appears in staffing candidates.
    inst_assign = await client.post(
        f"/organization/cohorts/{cohort.id}/instructors",
        headers=_headers(owner),
        json={"user_id": str(owner.id)},
    )
    assert inst_assign.status_code == 201, inst_assign.text
    assert inst_assign.json()["assigned"] == 1

    candidates = await list_eligible_instructors(db, sessions[0].id)
    assert owner.id in {u.id for u, *_ in candidates}

    # Ops detail serializes multi-role owner accurately.
    detail_resp = await client.get(
        f"/admin/website/organizations/{org.id}/detail",
        headers=_headers(admin),
    )
    assert detail_resp.status_code == 200, detail_resp.text
    owner_detail = next(m for m in detail_resp.json()["team"] if m["user_id"] == str(owner.id))
    assert owner_detail["is_owner"] is True
    assert owner_detail["org_roles"] == ["owner", "instructor", "judge"]
    assert owner_detail["org_role"] == "owner"

    # Primary owner still cannot be deleted/detached.
    del_owner = await client.delete(f"/organization/team/{owner.id}", headers=_headers(owner))
    assert del_owner.status_code == 400


async def test_invite_judge_appends_to_existing_org_roles_without_overwriting(db, client):
    from sqlalchemy import select

    owner, org = await _seed_org(db)
    _program, cohort, _ = await _seed_cohort(db, org)

    coord = await _add_member(db, client, owner, org_role="coordinator")
    coord_id = uuid.UUID(coord[0]["id"])
    coord_email = coord[1]

    # Upgrade coordinator to coordinator + instructor, then invite as cohort judge.
    await client.patch(
        f"/organization/team/{coord_id}",
        headers=_headers(owner),
        json={"org_roles": ["coordinator", "instructor"]},
    )

    resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/judges",
        headers=_headers(owner),
        json={"name": "Coord Instructor", "email": coord_email, "send_email": False},
    )
    assert resp.status_code == 201, resp.text

    user = (await db.execute(select(User).where(User.id == coord_id))).scalars().first()
    assert user is not None
    assert user.org_roles == ["coordinator", "instructor", "judge"]
    assert user.org_role == "coordinator"

    # Inviting the primary owner as judge also preserves "owner" and appends "judge".
    owner_resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/judges",
        headers=_headers(owner),
        json={"name": owner.full_name, "email": owner.email, "send_email": False},
    )
    assert owner_resp.status_code == 201, owner_resp.text
    await db.refresh(owner)
    assert owner.org_roles == ["owner", "judge"]
    assert owner.org_role == "owner"


async def test_auth_me_assign_tab_search_and_lms_editors_with_multi_role(db, client):
    owner, org = await _seed_org(db)
    program, cohort, _ = await _seed_cohort(db, org)

    # Regular student affiliated with the org must report empty org_roles and still show under mode=student.
    student = await _make_user(db, roles=["student"])
    student.organization_id = org.id
    await db.flush()

    student_me = await client.get("/auth/me", headers=_headers(student))
    assert student_me.status_code == 200, student_me.text
    assert student_me.json()["org_role"] is None
    assert student_me.json()["org_roles"] == []

    # Member with coordinator + instructor + observer.
    add_resp = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={
            "full_name": "Dual Staff Observer",
            "email": f"dual-{uuid.uuid4().hex[:8]}@example.com",
            "org_roles": ["coordinator", "instructor", "observer"],
        },
    )
    assert add_resp.status_code == 201, add_resp.text
    dual_id = uuid.UUID(add_resp.json()["id"])
    dual_user = await db.get(User, dual_id)

    dual_me = await client.get("/auth/me", headers=_headers(dual_user))
    assert dual_me.status_code == 200, dual_me.text
    assert dual_me.json()["org_role"] == "coordinator"
    assert dual_me.json()["org_roles"] == ["coordinator", "instructor", "observer"]

    # Owner /auth/me includes ["owner"] even before any explicit PATCH.
    owner_me = await client.get("/auth/me", headers=_headers(owner))
    assert owner_me.status_code == 200, owner_me.text
    assert owner_me.json()["org_role"] == "owner"
    assert owner_me.json()["org_roles"] == ["owner"]

    # mode=student does NOT drop regular student due to SQL NULL three-valued logic.
    student_search = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "student", "page_size": 100},
        headers=_headers(owner),
    )
    assert student_search.status_code == 200, student_search.text
    student_ids = {item["id"] for item in student_search.json()["items"]}
    assert str(student.id) in student_ids

    # Multi-role staff matches BOTH role=coordinator and role=instructor in Assign tab.
    for role_q in ("coordinator", "instructor"):
        staff_search = await client.get(
            f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
            params={"mode": "staff", "role": role_q, "page_size": 100},
            headers=_headers(owner),
        )
        assert staff_search.status_code == 200, staff_search.text
        staff_ids = {item["id"] for item in staff_search.json()["items"]}
        assert str(dual_id) in staff_ids

    # Also visible under mode=observer.
    obs_search = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "observer", "page_size": 100},
        headers=_headers(owner),
    )
    assert obs_search.status_code == 200, obs_search.text
    assert str(dual_id) in {item["id"] for item in obs_search.json()["items"]}

    # LMS cohort editors picks up multi-role members and owner.
    inst_judge = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={
            "full_name": "Inst Judge",
            "email": f"ij-{uuid.uuid4().hex[:8]}@example.com",
            "org_roles": ["instructor", "judge"],
        },
    )
    assert inst_judge.status_code == 201, inst_judge.text
    ij_id = inst_judge.json()["id"]

    editors_resp = await client.get(
        f"/lms/admin/cohorts/{cohort.id}/editors",
        headers=_headers(owner),
    )
    assert editors_resp.status_code == 200, editors_resp.text
    eligible_ids = {i["id"] for i in editors_resp.json()["eligible_instructors"]}
    assert ij_id in eligible_ids
    assert str(dual_id) in eligible_ids
    assert str(owner.id) in eligible_ids


async def test_team_tab_restricted_to_owner_and_coordinators_roster_open(db, client):
    owner, org = await _seed_org(db)
    coord = await _make_user(db, roles=["organization"])
    coord.full_name = "Teacher Coordinator"
    coord.organization_id = org.id
    coord.org_role = "coordinator"
    coord.org_roles = ["coordinator"]
    inst = await _make_user(db, roles=["organization"])
    inst.full_name = "Class Instructor"
    inst.organization_id = org.id
    inst.org_role = "instructor"
    inst.org_roles = ["instructor"]
    await db.commit()

    # /organization/me reflects owner vs non-owner coordinator
    owner_me = await client.get("/organization/me", headers=_headers(owner))
    coord_me = await client.get("/organization/me", headers=_headers(coord))
    assert owner_me.status_code == 200 and owner_me.json()["is_owner"] is True
    assert coord_me.status_code == 200 and coord_me.json()["is_owner"] is False

    # Owner accesses /organization/team normally
    assert (await client.get("/organization/team", headers=_headers(owner))).status_code == 200

    # Coordinator is blocked from all /organization/team* routes (Decision #4)
    assert (await client.get("/organization/team", headers=_headers(coord))).status_code == 403
    assert (
        await client.post(
            "/organization/team",
            headers=_headers(coord),
            json={"full_name": "Unauthorized", "email": f"u-{uuid.uuid4().hex[:6]}@example.com"},
        )
    ).status_code == 403
    assert (
        await client.patch(
            f"/organization/team/{inst.id}",
            headers=_headers(coord),
            json={"org_roles": ["coordinator"]},
        )
    ).status_code == 403
    assert (
        await client.post(f"/organization/team/{inst.id}/reset-link", headers=_headers(coord))
    ).status_code == 403
    assert (await client.delete(f"/organization/team/{inst.id}", headers=_headers(coord))).status_code == 403

    # Read-only /organization/coordinators is accessible to coordinators and lists coordinators + owner
    roster_resp = await client.get("/organization/coordinators", headers=_headers(coord))
    assert roster_resp.status_code == 200, roster_resp.text
    ids = {r["id"] for r in roster_resp.json()}
    assert str(owner.id) in ids
    assert str(coord.id) in ids
    assert str(inst.id) not in ids


async def test_cohort_coordinator_scoping_assigned_vs_general(db, client):
    from sqlalchemy import select
    from app.models.instructors.invitation_code import InvitationCode
    from app.models.lms.book import LmsBook, LmsBookEdition, LmsBookEnrollment
    from app.models.lms.invite_grant import InvitationCodeGrant
    from app.models.lms.program import LmsProgram
    from app.models.sessions.program import Program
    from app.models.sessions.registration import Registration
    from app.services.lms.invite_grants import apply_invite_code_grants_to_new_user

    owner, org = await _seed_org(db)
    org.is_approved = True
    org.book_scope = "all"

    coord_a = await _make_user(db, roles=["organization"])
    coord_b = await _make_user(db, roles=["organization"])
    coord_c = await _make_user(db, roles=["organization"])
    for idx, c in enumerate((coord_a, coord_b, coord_c), start=1):
        c.full_name = f"Teacher {idx}"
        c.organization_id = org.id
        c.org_role = "coordinator"
        c.org_roles = ["coordinator"]

    program = Program(
        id=uuid.uuid4(),
        code=f"SC-{uuid.uuid4().hex[:6]}",
        name="School Science Track",
        program_type="workshop",
        pricing_model="free",
        organization_id=org.id,
        active=True,
    )
    book = LmsBook(
        id=uuid.uuid4(),
        slug=f"org-sc-book-{uuid.uuid4().hex[:6]}",
        title="School Lab Book",
        access_mode="invite",
        is_published=True,
        bundle_version=1,
        outline=[{"key": "u1", "code": "U1", "title_en": "Intro", "lessons": []}],
        created_by=owner.id,
    )
    db.add_all([program, book])
    await db.flush()
    edition = LmsBookEdition(
        id=uuid.uuid4(),
        book_id=book.id,
        organization_id=org.id,
        created_by=coord_a.id,
        title="Teacher 1 U1 Slice",
        chapter_keys=["u1"],
    )
    lms_prog = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="School Checklist")
    db.add_all([edition, lms_prog])
    await db.commit()

    # Owner creates a "general" cohort visible to all coordinators
    gen_res = await client.post(
        "/organization/cohorts",
        headers=_headers(owner),
        json={
            "program_id": str(program.id),
            "name": "All Teachers General Cohort",
            "coordinator_access_mode": "general",
        },
    )
    assert gen_res.status_code == 201, gen_res.text
    gen_id = gen_res.json()["id"]

    # Coordinator A creates an "assigned" cohort sharing with B only (C excluded; A auto-included)
    asg_res = await client.post(
        "/organization/cohorts",
        headers=_headers(coord_a),
        json={
            "program_id": str(program.id),
            "name": "Teacher A + B Private Class",
            "coordinator_access_mode": "assigned",
            "coordinator_user_ids": [str(coord_b.id)],
        },
    )
    assert asg_res.status_code == 201, asg_res.text
    asg_id = asg_res.json()["id"]
    asg_coord_ids = {c["id"] for c in asg_res.json()["coordinators"]}
    assert asg_coord_ids == {str(coord_a.id), str(coord_b.id)}

    # Check programs-overview visibility per actor
    for actor, expected in [
        (owner, {gen_id, asg_id}),
        (coord_a, {gen_id, asg_id}),
        (coord_b, {gen_id, asg_id}),
        (coord_c, {gen_id}),
    ]:
        ov = await client.get("/organization/programs-overview", headers=_headers(actor))
        assert ov.status_code == 200, ov.text
        seen = {c["id"] for p in ov.json()["programs"] for c in p["cohorts"]}
        assert seen == expected

    # Coordinator B can read/update cohort & override LMS checklist; Coordinator C gets 403
    assert (await client.get(f"/sessions/cohorts/{asg_id}", headers=_headers(coord_b))).status_code == 200
    assert (await client.get(f"/sessions/cohorts/{asg_id}", headers=_headers(coord_c))).status_code == 403
    assert (
        await client.patch(
            f"/organization/cohorts/{asg_id}",
            headers=_headers(coord_c),
            json={"name": "Hijacked"},
        )
    ).status_code == 403

    ov_payload = {
        "item_type": "book",
        "title": "Class Edition Reading",
        "book_id": str(book.id),
        "book_edition_id": str(edition.id),
    }
    ov_res = await client.post(
        f"/lms/admin/cohorts/{asg_id}/program-override/items",
        headers=_headers(coord_b),
        json=ov_payload,
    )
    assert ov_res.status_code == 201, ov_res.text
    assert ov_res.json()["book_edition_id"] == str(edition.id)
    assert (
        await client.post(
            f"/lms/admin/cohorts/{asg_id}/program-override/items",
            headers=_headers(coord_c),
            json=ov_payload,
        )
    ).status_code == 403

    # Create invite code granting BOTH the assigned cohort AND the book edition
    code = InvitationCode(
        id=uuid.uuid4(),
        code=f"CLASS-{uuid.uuid4().hex[:6].upper()}",
        kind="student",
        is_active=True,
        max_uses=30,
        used_count=0,
    )
    db.add(code)
    await db.flush()
    db.add_all([
        InvitationCodeGrant(
            id=uuid.uuid4(),
            invitation_code_id=code.id,
            product_type="lms_program",
            cohort_id=uuid.UUID(asg_id),
        ),
        InvitationCodeGrant(
            id=uuid.uuid4(),
            invitation_code_id=code.id,
            product_type="book",
            book_id=book.id,
            book_edition_id=edition.id,
        ),
    ])
    student = await _make_user(db, roles=["student"])
    assert student.contact_id is None
    student.invitation_code_used = code.code
    await db.flush()

    # Redemption works with student.contact_id == None (auto resolves/creates Contact) & sets book_edition_id
    await apply_invite_code_grants_to_new_user(db, user_id=student.id, invitation_code_id=code.id)
    await db.commit()
    await db.refresh(student)
    assert student.contact_id is not None

    reg = (
        await db.execute(
            select(Registration).where(
                Registration.cohort_id == uuid.UUID(asg_id),
                Registration.contact_id == student.contact_id,
            )
        )
    ).scalars().first()
    assert reg is not None

    benr = (
        await db.execute(
            select(LmsBookEnrollment).where(
                LmsBookEnrollment.user_id == student.id,
                LmsBookEnrollment.book_id == book.id,
            )
        )
    ).scalars().first()
    assert benr is not None and benr.book_edition_id == edition.id

    # Invite codes & students scoping: Coordinator A sees code+student, Coordinator C is blocked on cohort_id
    codes_a = await client.get(
        "/lms/admin/invite-codes",
        params={"cohort_id": asg_id},
        headers=_headers(coord_a),
    )
    assert codes_a.status_code == 200
    assert any(c["id"] == str(code.id) for c in codes_a.json())

    codes_c = await client.get(
        "/lms/admin/invite-codes",
        params={"cohort_id": asg_id},
        headers=_headers(coord_c),
    )
    assert codes_c.status_code in (403, 404)

    studs_a = (
        await client.get("/lms/admin/students", params={"q": student.email}, headers=_headers(coord_a))
    ).json()
    studs_c = (
        await client.get("/lms/admin/students", params={"q": student.email}, headers=_headers(coord_c))
    ).json()
    assert any(s["id"] == str(student.id) for s in studs_a)
    assert not any(s["id"] == str(student.id) for s in studs_c)

    # Coordinator A shares the cohort with Coordinator C -> C immediately gains access
    share_res = await client.patch(
        f"/organization/cohorts/{asg_id}",
        headers=_headers(coord_a),
        json={"coordinator_user_ids": [str(coord_b.id), str(coord_c.id)]},
    )
    assert share_res.status_code == 200
    assert (await client.get(f"/sessions/cohorts/{asg_id}", headers=_headers(coord_c))).status_code == 200


async def test_ops_can_view_and_set_org_cohort_coordinators(db, client):
    from app.models.sessions.program import Program

    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])
    coord_a = await _make_user(db, roles=["organization"])
    coord_b = await _make_user(db, roles=["organization"])
    for idx, c in enumerate((coord_a, coord_b), start=1):
        c.full_name = f"Ops Coord {idx}"
        c.organization_id = org.id
        c.org_role = "coordinator"
        c.org_roles = ["coordinator"]

    program = Program(
        id=uuid.uuid4(),
        code=f"OPS-{uuid.uuid4().hex[:6]}",
        name="Ops Managed Org Track",
        program_type="workshop",
        pricing_model="free",
        organization_id=org.id,
        active=True,
    )
    db.add(program)
    await db.commit()

    # Ops can list coordinators for a specific org
    roster = await client.get(
        "/organization/coordinators",
        params={"organization_id": str(org.id)},
        headers=_headers(ops),
    )
    assert roster.status_code == 200, roster.text
    roster_ids = {r["id"] for r in roster.json()}
    assert {str(owner.id), str(coord_a.id), str(coord_b.id)}.issubset(roster_ids)

    # Ops creates an assigned cohort via /sessions/cohorts
    create_res = await client.post(
        "/sessions/cohorts",
        headers=_headers(ops),
        json={
            "program_id": str(program.id),
            "organization_id": str(org.id),
            "name": "Ops Assigned Cohort",
            "management_mode": "partner",
            "coordinator_access_mode": "assigned",
            "coordinator_user_ids": [str(coord_a.id)],
        },
    )
    assert create_res.status_code == 201, create_res.text
    cid = create_res.json()["id"]
    assert create_res.json()["coordinator_access_mode"] == "assigned"
    assert [c["id"] for c in create_res.json()["coordinators"]] == [str(coord_a.id)]

    # Coordinator A can access, Coordinator B cannot
    assert (await client.get(f"/sessions/cohorts/{cid}", headers=_headers(coord_a))).status_code == 200
    assert (await client.get(f"/sessions/cohorts/{cid}", headers=_headers(coord_b))).status_code == 403

    # Ops updates cohort to reassign to Coordinator B
    patch_res = await client.patch(
        f"/sessions/cohorts/{cid}",
        headers=_headers(ops),
        json={
            "coordinator_access_mode": "assigned",
            "coordinator_user_ids": [str(coord_b.id)],
        },
    )
    assert patch_res.status_code == 200, patch_res.text
    assert [c["id"] for c in patch_res.json()["coordinators"]] == [str(coord_b.id)]
    assert (await client.get(f"/sessions/cohorts/{cid}", headers=_headers(coord_b))).status_code == 200
    assert (await client.get(f"/sessions/cohorts/{cid}", headers=_headers(coord_a))).status_code == 403


