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
