"""Tests for team certificates, template kinds, email templates, and skip-already-issued isolation."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.certificate import Certificate
from app.models.enums import CertificateType
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.competitions.certificates import (
    get_cohort_certificate_recipients,
    render_certificate_email,
    send_cohort_certificates,
)
from app.services.documents.certificate import expand_certificate_body_template


@pytest.mark.asyncio
async def test_expand_team_and_rank_tokens():
    out = expand_certificate_body_template(
        "Team <b>{team_name}</b> placed <b>{rank}</b> ({rank_number})",
        program_name="Space Cup",
        team_name="Orbiters & Co",
        rank=2,
    )
    assert out == "Team <b>Orbiters &amp; Co</b> placed <b>2nd</b> (2)"

    unranked = expand_certificate_body_template(
        "Team <b>{team_name}</b><br/>{rank}",
        program_name="Space Cup",
        team_name="Rovers",
        rank=None,
    )
    assert unranked == "Team <b>Rovers</b>"


@pytest.mark.asyncio
async def test_render_certificate_email_with_profile_and_cert_list():
    subj, html = render_certificate_email(
        student_name="Sara Ali",
        program_name="Space Cup",
        cohort_name="Cohort 1",
        dates="Oct 12 – 16, 2026",
        team_name="Orbiters",
        team_rank=1,
        custom_subject="{student_name} - {rank} - {certificate_list}",
        custom_body="<p>{certificate_list}</p><p>{profile_link}</p>",
        certificate_list="Student Certificate and Team Certificate",
        profile_link="https://app.example.com/learn/profile",
    )
    assert subj == "Sara Ali - 1st - Student Certificate and Team Certificate"
    assert "Student Certificate and Team Certificate" in html
    assert "https://app.example.com/learn/profile" in html


@pytest.mark.asyncio
async def test_email_template_crud(client: AsyncClient, db: AsyncSession):
    admin = User(
        id=uuid.uuid4(),
        email=f"ops_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Ops Admin",
        roles=["operations"],
        status="active",
    )
    db.add(admin)
    await db.flush()

    from app.core.security import create_access_token
    token = create_access_token(str(admin.id), admin.roles)
    headers = {"Authorization": f"Bearer {token}"}

    # List seeded templates
    res = await client.get("/sessions/certificate-email-templates", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 4

    # Create
    create_res = await client.post(
        "/sessions/certificate-email-templates",
        json={
            "name": "Custom Team Mail",
            "kind": "team",
            "subject": "Congrats {team_name}",
            "body_html": "<p>Rank {rank}</p>",
            "is_default": False,
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    created = create_res.json()
    tid = created["id"]
    assert created["kind"] == "team"

    # Update
    upd_res = await client.put(
        f"/sessions/certificate-email-templates/{tid}",
        json={"name": "Updated Team Mail"},
        headers=headers,
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "Updated Team Mail"

    # Delete
    del_res = await client.delete(f"/sessions/certificate-email-templates/{tid}", headers=headers)
    assert del_res.status_code == 204


async def _ensure_test_team_columns(db: AsyncSession) -> None:
    for stmt in [
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS final_locked_at TIMESTAMPTZ",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS final_locked_by UUID",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS first_locked_at TIMESTAMPTZ",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS final_lock_penalty DOUBLE PRECISION",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS final_lock_notes VARCHAR(255)",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS timing_adjustment_override DOUBLE PRECISION",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS timing_adjustment_notes VARCHAR(255)",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS qualification VARCHAR(50)",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS ops_criterion_scores JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS ops_criterion_notes TEXT",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS ops_scored_by UUID",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS ops_scored_at TIMESTAMPTZ",
        "ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS is_observer BOOLEAN NOT NULL DEFAULT false",
    ]:
        await db.execute(text(stmt))


@pytest.mark.asyncio
async def test_skip_already_issued_isolated_between_student_and_team(db: AsyncSession, monkeypatch):
    await _ensure_test_team_columns(db)
    # Stub email & storage so no network/disk side effects
    sent_emails = []

    async def fake_send_email(to, subject, body, html=False, attachments=None):
        sent_emails.append({"to": to, "subject": subject, "attachments": attachments or []})

    async def fake_upload(bucket, path, data, content_type):
        return path

    monkeypatch.setattr("app.services.competitions.certificates.try_send_email", fake_send_email)
    monkeypatch.setattr("app.services.competitions.certificates.storage.upload_to_path", fake_upload)

    actor = User(
        id=uuid.uuid4(),
        email=f"actor_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Actor",
        roles=["operations"],
        status="active",
    )
    prog = Program(id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:6]}", name="Space Cup", program_type="competition", pricing_model="free")
    cohort = Cohort(id=uuid.uuid4(), program_id=prog.id, name="Cohort 1")
    contact = Contact(id=uuid.uuid4(), full_name="Sara Ali", email="sara@example.com")
    student_user = User(
        id=uuid.uuid4(),
        email="sara@example.com",
        password_hash="x",
        full_name="Sara Ali",
        contact_id=contact.id,
        roles=["student"],
        status="active",
    )
    db.add_all([actor, prog, contact, student_user])
    await db.flush()
    db.add(cohort)
    await db.flush()

    reg = Registration(id=uuid.uuid4(), cohort_id=cohort.id, contact_id=contact.id, status="registered", ticket_token=uuid.uuid4().hex, registered_via="admin")
    team = Team(id=uuid.uuid4(), cohort_id=cohort.id, name="Orbiters", join_code="ORB123")
    db.add_all([reg, team])
    await db.flush()

    db.add(TeamMember(team_id=team.id, user_id=student_user.id))
    await db.flush()

    # 1. Send individual certificate
    res1 = await send_cohort_certificates(
        db,
        cohort_id=cohort.id,
        actor_user_id=actor.id,
        registration_ids=[reg.id],
        primary_kind="individual",
        delivery_mode="email",
        skip_already_issued=True,
    )
    assert res1["sent_count"] == 1
    assert len(sent_emails) == 1
    assert sent_emails[0]["attachments"][0][0] == "Space Cup - Certificate.pdf"

    # 2. Send team certificate to the same student with skip_already_issued=True
    #    MUST NOT skip because only student_completion was issued!
    res2 = await send_cohort_certificates(
        db,
        cohort_id=cohort.id,
        actor_user_id=actor.id,
        registration_ids=[reg.id],
        primary_kind="team",
        delivery_mode="publish",
        skip_already_issued=True,
    )
    assert not res2.get("errors"), res2
    assert res2["sent_count"] == 1
    assert res2["skipped_count"] == 0
    assert len(sent_emails) == 2
    assert sent_emails[1]["attachments"] == []  # publish mode sends link, no PDF attachment

    # 3. Verify both rows exist independently
    certs = (await db.execute(select(Certificate).where(Certificate.registration_id == reg.id))).scalars().all()
    types = {c.type for c in certs}
    assert types == {CertificateType.student_completion, CertificateType.team_completion}

    # 4. Verify recipients summary reports both issued independently
    summary = await get_cohort_certificate_recipients(db, cohort_id=cohort.id)
    rec = summary["recipients"][0]
    assert rec["student_cert_issued"] is True
    assert rec["team_cert_issued"] is True


@pytest.mark.asyncio
async def test_my_certificates_returns_student_and_team_certificates(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    await _ensure_test_team_columns(db)
    async def fake_send_email(to, subject, body, html=False, attachments=None):
        return None

    async def fake_upload(bucket, path, data, content_type):
        return path

    async def fake_resolve_url(bucket, path, **kw):
        return f"https://files.example.com/{path}"

    monkeypatch.setattr("app.services.competitions.certificates.try_send_email", fake_send_email)
    monkeypatch.setattr("app.services.competitions.certificates.storage.upload_to_path", fake_upload)
    monkeypatch.setattr("app.routers.lms.student.storage.resolve_url", fake_resolve_url)

    actor = User(
        id=uuid.uuid4(),
        email=f"ops_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        full_name="Ops",
        roles=["operations"],
        status="active",
    )
    prog = Program(id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:6]}", name="Space Cup", program_type="competition", pricing_model="free")
    cohort = Cohort(id=uuid.uuid4(), program_id=prog.id, name="Cohort 1")
    contact = Contact(id=uuid.uuid4(), full_name="Sara Ali", email=f"sara_{uuid.uuid4().hex[:6]}@example.com")
    student_user = User(
        id=uuid.uuid4(),
        email=contact.email,
        password_hash="x",
        full_name="Sara Ali",
        contact_id=contact.id,
        roles=["student"],
        status="active",
    )
    db.add_all([actor, prog, contact, student_user])
    await db.flush()
    db.add(cohort)
    await db.flush()

    reg = Registration(id=uuid.uuid4(), cohort_id=cohort.id, contact_id=contact.id, status="registered", ticket_token=uuid.uuid4().hex, registered_via="admin")
    team = Team(id=uuid.uuid4(), cohort_id=cohort.id, name="Orbiters", join_code="ORB999")
    db.add_all([reg, team])
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=student_user.id))
    await db.flush()

    send_res = await send_cohort_certificates(
        db,
        cohort_id=cohort.id,
        actor_user_id=actor.id,
        registration_ids=[reg.id],
        primary_kind="individual",
        also_send_other=True,
        delivery_mode="publish",
        skip_already_issued=True,
    )
    assert not send_res.get("errors"), send_res
    assert send_res["sent_count"] == 1

    token = create_access_token(student_user.id, student_user.role_values)
    res = await client.get("/lms/my-certificates", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    items = res.json()
    by_type = {item["type"]: item for item in items}
    assert CertificateType.student_completion.value in by_type
    assert CertificateType.team_completion.value in by_type
    assert by_type[CertificateType.team_completion.value]["team_name"] == "Orbiters"
    assert by_type[CertificateType.team_completion.value]["url"].startswith("https://files.example.com/")

