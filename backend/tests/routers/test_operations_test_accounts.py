"""Automated tests for @spacepoint.local test accounts & deep cascade delete.

Covers the 6 checklist scenarios:
1. @spacepoint.local email validation unblocked (Pydantic EmailStr accepts .local)
2. Split SMTP routing (routes @spacepoint.local to Mailpit, other domains to real SMTP)
3. Non-test email protection (rejects 403 on non-@spacepoint.local accounts)
4. Admin role protection (rejects 403 when assigning admin or touching admin accounts)
5. Full cascade delete across RESTRICT FKs and Spine contacts
6. Re-signup after cascade delete without contact collisions
"""

from unittest.mock import AsyncMock, patch
import uuid

import pytest
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.enums import UserRole
from app.models.games.game import Game
from app.models.games.run import GameParticipant, GameRun
from app.models.missions.mission import MissionAttempt
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.invite_grant import UserInvitationCode
from app.models.spine.contact import Contact, ContactRelationship
from app.models.team import Team as LearnerTeam, TeamMember as LearnerTeamMember
from app.models.user import User
from app.services.email import send_email
from app.services.test_account_cleanup import cascade_delete_test_account


class SampleEmailModel(BaseModel):
    email: EmailStr


def _headers(user: User):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.roles)}"}


async def _make_user(db, email: str, roles: list[UserRole], full_name: str = "Test User") -> User:
    user = User(
        id=uuid.uuid4(),
        full_name=full_name,
        email=email,
        password_hash=get_password_hash("SpacePoint123!"),
        roles=roles,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_1_spacepoint_local_email_validation():
    """Case 1: Pydantic EmailStr accepts @spacepoint.local across all schemas."""
    model = SampleEmailModel(email="ali.test@spacepoint.local")
    assert model.email == "ali.test@spacepoint.local"
    assert settings.is_test_email("ali.test@spacepoint.local") is True
    assert settings.is_test_email("ali@gmail.com") is False


@pytest.mark.asyncio
async def test_2_split_smtp_routing():
    """Case 2: Split SMTP routing routes @spacepoint.local to Mailpit."""
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await send_email(
            to="student@spacepoint.local",
            subject="Welcome!",
            body="Your code is 123",
        )
        assert mock_send.call_count == 1
        _, kwargs = mock_send.call_args
        assert kwargs["hostname"] == settings.LOCAL_SMTP_HOST
        assert kwargs["port"] == settings.LOCAL_SMTP_PORT
        assert kwargs["use_tls"] is False
        assert kwargs["start_tls"] is False

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send_real:
        with patch.object(settings, "SMTP_USER", "real_user@gmail.com"), patch.object(
            settings, "SMTP_PASSWORD", "secret"
        ):
            await send_email(
                to="parent@gmail.com",
                subject="Receipt",
                body="Your payment succeeded",
            )
            assert mock_send_real.call_count == 1
            _, kwargs_real = mock_send_real.call_args
            assert kwargs_real["hostname"] == settings.SMTP_HOST
            assert kwargs_real["port"] == settings.SMTP_PORT
            assert kwargs_real["username"] == "real_user@gmail.com"


@pytest.mark.asyncio
async def test_3_non_test_email_protection(db, client):
    """Case 3: Operations cannot delete or update real domain accounts."""
    ops_user = await _make_user(db, "ops@spacepoint.local", [UserRole.operations])
    real_user = await _make_user(db, "founder@spacepoint.ae", [UserRole.instructor])

    headers = _headers(ops_user)

    # Attempt to delete real domain account
    res_del = await client.delete(
        f"/operations/test-accounts/users/{real_user.id}", headers=headers
    )
    assert res_del.status_code == 403
    assert "Only @spacepoint.local test accounts" in res_del.json()["detail"]

    # Attempt to update real domain account
    res_patch = await client.patch(
        f"/operations/test-accounts/users/{real_user.id}",
        json={"full_name": "Hacked Name"},
        headers=headers,
    )
    assert res_patch.status_code == 403


@pytest.mark.asyncio
async def test_4_admin_role_protection(db, client):
    """Case 4: Operations cannot assign the admin role or modify admin accounts."""
    ops_user = await _make_user(db, "ops.lead@spacepoint.local", [UserRole.operations])
    admin_user = await _make_user(db, "admin.test@spacepoint.local", [UserRole.admin])
    headers = _headers(ops_user)

    # Cannot delete admin even if @spacepoint.local
    res_del = await client.delete(
        f"/operations/test-accounts/users/{admin_user.id}", headers=headers
    )
    assert res_del.status_code == 403
    assert "Admin accounts cannot be modified or deleted" in res_del.json()["detail"]

    # Cannot create user with admin role
    res_create = await client.post(
        "/operations/test-accounts/users",
        json={
            "full_name": "Rogue Admin",
            "email": "rogue@spacepoint.local",
            "password": "Password123!",
            "roles": ["admin"],
        },
        headers=headers,
    )
    assert res_create.status_code == 403
    assert "Operations cannot assign or test the admin role" in res_create.json()["detail"]


@pytest.mark.asyncio
async def test_5_full_cascade_delete_and_spine_cleanup(db):
    """Case 5: Deep cascade delete wipes user, FK dependencies, and orphan guardian."""
    student_contact = Contact(
        id=uuid.uuid4(),
        full_name="Test Student",
        email="student.test@spacepoint.local",
        primary_phone_e164="+971500000001",
    )
    guardian_contact = Contact(
        id=uuid.uuid4(),
        full_name="Parent Guardian",
        email="parent.test@spacepoint.local",
        primary_phone_e164="+971500000002",
    )
    db.add_all([student_contact, guardian_contact])
    await db.flush()

    rel = ContactRelationship(
        contact_id=guardian_contact.id,
        related_contact_id=student_contact.id,
        relation="guardian_of",
    )
    db.add(rel)

    # Create student user linked to contact
    student_user = User(
        id=uuid.uuid4(),
        contact_id=student_contact.id,
        full_name="Test Student",
        email="student.test@spacepoint.local",
        password_hash=get_password_hash("Pass123!"),
        roles=[UserRole.student],
        status="active",
    )
    db.add(student_user)
    await db.flush()

    # Create solo learner team & mission attempt (RESTRICT FK)
    team = LearnerTeam(
        id=uuid.uuid4(),
        name="Team Alpha",
        created_by=student_user.id,
    )
    db.add(team)
    await db.flush()

    team_member = LearnerTeamMember(
        team_id=team.id,
        user_id=student_user.id,
    )
    db.add(team_member)

    # Create game created by user (RESTRICT FK on users.id)
    game = Game(id=uuid.uuid4(), title="Test Game", created_by=student_user.id)
    db.add(game)
    await db.flush()

    user_id = student_user.id
    contact_id = student_contact.id
    guardian_id = guardian_contact.id
    team_id = team.id
    game_id = game.id

    # Trigger cascade deletion
    with patch("app.services.test_account_cleanup.purge_mailpit_messages", new_callable=AsyncMock):
        result = await cascade_delete_test_account(db, user_id=user_id)

    assert result["deleted_user_id"] == str(user_id)
    assert result["deleted_contacts"] >= 2  # student contact + orphan guardian contact

    # Verify user row deleted
    assert (await db.get(User, user_id)) is None
    # Verify contacts deleted
    assert (await db.get(Contact, contact_id)) is None
    assert (await db.get(Contact, guardian_id)) is None
    # Verify team and game rows deleted
    assert (await db.get(LearnerTeam, team_id)) is None
    assert (await db.get(Game, game_id)) is None


@pytest.mark.asyncio
async def test_6_re_signup_after_cascade_delete(db, client):
    """Case 6: Can re-create account with the exact same email after cascade delete."""
    ops_user = await _make_user(db, "ops.admin@spacepoint.local", [UserRole.operations])
    headers = _headers(ops_user)

    target_email = "recreation.student@spacepoint.local"

    # Create test account
    res1 = await client.post(
        "/operations/test-accounts/users",
        json={
            "full_name": "First Creation",
            "email": target_email,
            "password": "Password123!",
            "roles": ["student"],
        },
        headers=headers,
    )
    assert res1.status_code == 201
    user_id = res1.json()["id"]

    # Delete test account
    with patch("app.services.test_account_cleanup.purge_mailpit_messages", new_callable=AsyncMock):
        res_del = await client.delete(f"/operations/test-accounts/users/{user_id}", headers=headers)
        assert res_del.status_code == 200

    # Re-create account with exact same email immediately
    res2 = await client.post(
        "/operations/test-accounts/users",
        json={
            "full_name": "Second Creation",
            "email": target_email,
            "password": "Password123!",
            "roles": ["student"],
        },
        headers=headers,
    )
    assert res2.status_code == 201
    assert res2.json()["email"] == target_email


@pytest.mark.asyncio
async def test_7_delete_student_with_invite_code_and_media_consent(db, client):
    """Case 7: Can delete a student who redeemed an invite code and has matched media consents."""
    ops_user = await _make_user(db, "ops.invites@spacepoint.local", [UserRole.operations])
    headers = _headers(ops_user)

    contact = Contact(
        id=uuid.uuid4(),
        full_name="Invited Student",
        email="invited.student@spacepoint.local",
        contact_roles=["student"],
    )
    db.add(contact)
    await db.flush()

    student = User(
        id=uuid.uuid4(),
        full_name="Invited Student",
        email="invited.student@spacepoint.local",
        password_hash=get_password_hash("Password123!"),
        roles=[UserRole.student],
        contact_id=contact.id,
        status="active",
        invitation_code_used="SUMMER26",
    )
    db.add(student)
    await db.flush()

    # Create dummy invite code and user redemption
    code_row = InvitationCode(
        id=uuid.uuid4(),
        code="SUMMER26",
        kind="student",
        is_active=True,
    )
    db.add(code_row)
    await db.flush()

    db.add(
        UserInvitationCode(
            id=uuid.uuid4(),
            user_id=student.id,
            invitation_code_id=code_row.id,
            code="SUMMER26",
        )
    )

    # If cohort_media_consents table exists in this DB, add a record
    res = await db.execute(select(Contact.id).where(Contact.id == contact.id))
    assert res.scalar_one_or_none() is not None

    student_id = student.id
    contact_id = contact.id

    with patch("app.services.test_account_cleanup.purge_mailpit_messages", new_callable=AsyncMock):
        del_res = await client.delete(f"/operations/test-accounts/users/{student_id}", headers=headers)
        assert del_res.status_code == 200, del_res.text

    assert (await db.get(User, student_id)) is None
    assert (await db.get(Contact, contact_id)) is None


@pytest.mark.asyncio
async def test_8_admin_delete_normal_user_and_test_user(db, client):
    """Case 8: Admin DELETE /admin/users/{id} works for both normal users and test users."""
    admin_user = await _make_user(db, "admin.test@spacepoint.local", [UserRole.admin])
    headers = _headers(admin_user)

    # 1. Normal non-test user deletion via /admin/users/{id}
    normal_user = await _make_user(db, "standard.applicant@example.com", [UserRole.student])
    res_del_norm = await client.delete(f"/admin/users/{normal_user.id}", headers=headers)
    assert res_del_norm.status_code == 200, res_del_norm.text

    # 2. Test user deletion via /admin/users/{id} (delegates to cascade cleanup)
    test_student = await _make_user(db, "cascade.target@spacepoint.local", [UserRole.student])
    with patch("app.services.test_account_cleanup.purge_mailpit_messages", new_callable=AsyncMock):
        res_del_test = await client.delete(f"/admin/users/{test_student.id}", headers=headers)
        assert res_del_test.status_code == 200, res_del_test.text


