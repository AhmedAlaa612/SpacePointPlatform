"""Competition judging certificate issuance tests (2026-09).

Tests:
1. Preview recipients:
   - Evaluates 'at_least_one' filter (students with >= 1 submission)
   - Evaluates 'all_completed' filter (students who finished all required deliverables or locked team)
2. Send certificates:
   - Generates Certificate rows, updates registration to 'completed', and sends emails
   - Honors skip_already_issued flag (idempotency)
"""

import io
import uuid
from unittest.mock import patch

from pypdf import PdfReader
import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.certificate import Certificate
from app.models.lms.program import (
    LmsProgram, LmsProgramItem, LmsProgramTeamItemProgress,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.sessions.registration import register
from app.services.teams import create_team


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Cert Ops", email=f"certops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, name: str, *, cohort: Cohort | None = None) -> tuple[User, Registration]:
    email = f"student-{uuid.uuid4().hex[:8]}@example.com"
    contact = Contact(
        id=uuid.uuid4(), full_name=name, email=email, contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name=name, email=email,
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    reg = None
    if cohort is not None:
        reg = await register(
            db, contact_id=contact.id, cohort_id=cohort.id,
            registered_via="desk", payment_status="waived",
        )
        await db.flush()
    return user, reg


async def _setup_competition_cohort(db):
    program = Program(
        id=uuid.uuid4(), code=f"CERT-{uuid.uuid4().hex[:8]}", name="Space Cup",
        program_type="competition", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()

    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Qualifier Stage", status="running")
    db.add(cohort)
    await db.flush()

    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Cup Checklist")
    db.add(lms_program)
    await db.flush()

    # Checklist items: 2 required team submissions
    item1 = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Design Proposal", scope="team", optional=False,
    )
    item2 = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="submission", title="Final Presentation", scope="team", optional=False,
    )
    db.add_all([item1, item2])
    await db.flush()

    return program, cohort, lms_program, [item1, item2]


@pytest.mark.asyncio
async def test_certificate_recipients_preview(db, client):
    ops = await _ops(db)
    program, cohort, lms_program, (item1, item2) = await _setup_competition_cohort(db)

    # Student 1: Team Alpha (submitted item 1 only)
    s1, r1 = await _student(db, "Student Alpha 1", cohort=cohort)
    team_alpha = await create_team(db, cohort_id=cohort.id, name="Team Alpha", created_by=s1.id)
    # add item 1 submission
    p1 = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item1.id, team_id=team_alpha.id, status="done",
        submitted_url="https://example.com/alpha-proposal",
    )
    db.add(p1)

    # Student 2: Team Beta (submitted both item 1 and item 2)
    s2, r2 = await _student(db, "Student Beta 1", cohort=cohort)
    team_beta = await create_team(db, cohort_id=cohort.id, name="Team Beta", created_by=s2.id)
    p2a = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item1.id, team_id=team_beta.id, status="done",
        submitted_url="https://example.com/beta-proposal",
    )
    p2b = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item2.id, team_id=team_beta.id, status="done",
        submitted_url="https://example.com/beta-final",
    )
    db.add_all([p2a, p2b])

    # Student 3: Team Gamma (no submissions)
    s3, r3 = await _student(db, "Student Gamma 1", cohort=cohort)
    await create_team(db, cohort_id=cohort.id, name="Team Gamma", created_by=s3.id)

    await db.commit()

    # Query all recipients
    resp_all = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/recipients?filter=all",
        headers=_headers(ops),
    )
    assert resp_all.status_code == 200, resp_all.text
    data = resp_all.json()
    assert data["total_registered"] == 3
    assert data["at_least_one_count"] == 2
    assert data["all_completed_count"] == 1
    assert len(data["recipients"]) == 3

    # Query 'at_least_one' filter
    resp_at_least_one = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/recipients?filter=at_least_one",
        headers=_headers(ops),
    )
    assert resp_at_least_one.status_code == 200
    at_least_one_data = resp_at_least_one.json()
    assert len(at_least_one_data["recipients"]) == 2
    names = {r["student_name"] for r in at_least_one_data["recipients"]}
    assert names == {"Student Alpha 1", "Student Beta 1"}

    # Query 'all_completed' filter
    resp_all_comp = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/recipients?filter=all_completed",
        headers=_headers(ops),
    )
    assert resp_all_comp.status_code == 200
    all_comp_data = resp_all_comp.json()
    assert len(all_comp_data["recipients"]) == 1
    assert all_comp_data["recipients"][0]["student_name"] == "Student Beta 1"


@pytest.mark.asyncio
async def test_send_cohort_certificates(db, client):
    ops = await _ops(db)
    program, cohort, lms_program, (item1, item2) = await _setup_competition_cohort(db)

    # Student 1: submitted 1 item
    s1, r1 = await _student(db, "Student Alpha", cohort=cohort)
    team_alpha = await create_team(db, cohort_id=cohort.id, name="Alpha", created_by=s1.id)
    p1 = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item1.id, team_id=team_alpha.id, status="done",
        submitted_url="https://example.com/alpha-proposal",
    )
    db.add(p1)

    # Student 2: submitted 2 items
    s2, r2 = await _student(db, "Student Beta", cohort=cohort)
    team_beta = await create_team(db, cohort_id=cohort.id, name="Beta", created_by=s2.id)
    p2a = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item1.id, team_id=team_beta.id, status="done",
        submitted_url="https://example.com/beta-proposal",
    )
    p2b = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item2.id, team_id=team_beta.id, status="done",
        submitted_url="https://example.com/beta-final",
    )
    db.add_all([p2a, p2b])
    await db.commit()

    # Send certificates for students with 'all_completed'
    with patch("app.services.competitions.certificates.try_send_email") as mock_email:
        mock_email.return_value = None
        send_resp = await client.post(
            f"/competitions/admin/cohorts/{cohort.id}/certificates/send",
            headers=_headers(ops),
            json={"filter": "all_completed", "theme": "dark", "skip_already_issued": True},
        )
        assert send_resp.status_code == 200, send_resp.text
        res = send_resp.json()
        assert res["sent_count"] == 1
        assert mock_email.called
        call_args = mock_email.call_args[0]
        # recipient, subject, body
        assert program.name in call_args[1]
        assert program.name in call_args[2]

    # Check Certificate row was created
    certs = (await db.execute(select(Certificate).where(Certificate.registration_id == r2.id))).scalars().all()
    assert len(certs) == 1
    assert certs[0].workshop_name == program.name

    # Check registration was updated to completed
    await db.refresh(r2)
    assert r2.status == "completed"

    # Re-sending with skip_already_issued=True should skip Student Beta
    with patch("app.services.competitions.certificates.try_send_email") as mock_email:
        send_again = await client.post(
            f"/competitions/admin/cohorts/{cohort.id}/certificates/send",
            headers=_headers(ops),
            json={"filter": "all_completed", "theme": "dark", "skip_already_issued": True},
        )
        assert send_again.status_code == 200
        res2 = send_again.json()
        assert res2["sent_count"] == 0
        assert res2["skipped_count"] == 1
        assert not mock_email.called

    # Explicitly selecting Student Alpha only should send only to Student Alpha
    with patch("app.services.competitions.certificates.try_send_email") as mock_email:
        mock_email.return_value = None
        send_alpha = await client.post(
            f"/competitions/admin/cohorts/{cohort.id}/certificates/send",
            headers=_headers(ops),
            json={"filter": "at_least_one", "theme": "dark", "registration_ids": [str(r1.id)], "skip_already_issued": False},
        )
        assert send_alpha.status_code == 200
        res_alpha = send_alpha.json()
        assert res_alpha["sent_count"] == 1
        assert res_alpha["recipient_names"] == ["Student Alpha"]
        assert mock_email.called


@pytest.mark.asyncio
async def test_download_cohort_certificates_pdf(db, client):
    ops = await _ops(db)
    program, cohort, lms_program, (item1, item2) = await _setup_competition_cohort(db)

    # Student 1: submitted 1 item
    s1, r1 = await _student(db, "PDF Student Alpha", cohort=cohort)
    team_alpha = await create_team(db, cohort_id=cohort.id, name="PDF Alpha", created_by=s1.id)
    p1 = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item1.id, team_id=team_alpha.id, status="done",
        submitted_url="https://example.com/pdf-alpha",
    )
    db.add(p1)

    # Student 2: submitted both items
    s2, r2 = await _student(db, "PDF Student Beta", cohort=cohort)
    team_beta = await create_team(db, cohort_id=cohort.id, name="PDF Beta", created_by=s2.id)
    p2a = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item1.id, team_id=team_beta.id, status="done",
        submitted_url="https://example.com/pdf-beta-1",
    )
    p2b = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item2.id, team_id=team_beta.id, status="done",
        submitted_url="https://example.com/pdf-beta-2",
    )
    db.add_all([p2a, p2b])
    await db.commit()

    # 1. Download dark theme PDF for at_least_one (should include both students, 2 pages)
    resp_dark = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/download?filter=at_least_one&theme=dark",
        headers=_headers(ops),
    )
    assert resp_dark.status_code == 200, resp_dark.text
    assert resp_dark.headers["content-type"] == "application/pdf"
    assert "attachment;" in resp_dark.headers.get("content-disposition", "")
    assert resp_dark.content.startswith(b"%PDF-")

    # 2. Download light theme PDF for all_completed (should include Student Beta only, 1 page)
    resp_light = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/download?filter=all_completed&theme=light",
        headers=_headers(ops),
    )
    assert resp_light.status_code == 200, resp_light.text
    assert resp_light.headers["content-type"] == "application/pdf"
    assert resp_light.content.startswith(b"%PDF-")

    # 3. Empty cohort with no submissions should return 400
    empty_cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Empty Stage", status="running")
    db.add(empty_cohort)
    await db.commit()

    resp_empty = await client.get(
        f"/competitions/admin/cohorts/{empty_cohort.id}/certificates/download?filter=at_least_one&theme=dark",
        headers=_headers(ops),
    )
    assert resp_empty.status_code == 404
    assert "No matching students found" in resp_empty.json()["detail"]

    # 4. Download PDF for only selected student (Student Alpha only, exactly 1 page)
    resp_selected = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/download",
        headers=_headers(ops),
        json={"filter": "at_least_one", "theme": "dark", "registration_ids": [str(r1.id)]},
    )
    assert resp_selected.status_code == 200, resp_selected.text
    assert resp_selected.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(resp_selected.content))
    assert len(reader.pages) == 1

    # 5. GET with query param registration_ids also downloads only selected
    resp_get_selected = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/download?registration_ids={r1.id}",
        headers=_headers(ops),
    )
    assert resp_get_selected.status_code == 200
    reader_get = PdfReader(io.BytesIO(resp_get_selected.content))
    assert len(reader_get.pages) == 1


@pytest.mark.asyncio
async def test_locked_only_and_participation_filters_and_custom_emails(db, client):
    from datetime import datetime, timezone
    from app.models.sessions.program_certificate_template import ProgramCertificateTemplate

    ops = await _ops(db)
    program, cohort, lms_program, (item1, item2) = await _setup_competition_cohort(db)

    # Custom template with email subject and body configured
    custom_template = ProgramCertificateTemplate(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Custom Winner Cert",
        is_default=True,
        background_type="dark",
        email_subject="Exclusive Award — {program_name} ({certificate_type})",
        email_body="<p>Greetings {student_name}, team {team_name} earned {certificate_type}!</p>",
    )
    db.add(custom_template)

    # Student 1: locked team (even with 1 submission, team locked -> locked_only / completion)
    s1, r1 = await _student(db, "Locked Student Alpha", cohort=cohort)
    team1 = await create_team(db, cohort_id=cohort.id, name="Team Locked", created_by=s1.id)
    team1.final_locked_at = datetime.now(timezone.utc)
    p1 = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item1.id, team_id=team1.id, status="done",
        submitted_url="https://example.com/locked-p1",
    )
    db.add(p1)

    # Student 2: submitted 1 item, but team is NOT locked -> participation
    s2, r2 = await _student(db, "Participant Beta", cohort=cohort)
    team2 = await create_team(db, cohort_id=cohort.id, name="Team Active", created_by=s2.id)
    p2 = LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=item1.id, team_id=team2.id, status="done",
        submitted_url="https://example.com/part-p1",
    )
    db.add(p2)
    await db.commit()

    # 1. Test get recipients with locked_only filter
    resp_locked = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/recipients?filter=locked_only",
        headers=_headers(ops),
    )
    assert resp_locked.status_code == 200, resp_locked.text
    locked_data = resp_locked.json()
    assert locked_data["program_name"] == program.name
    assert locked_data["cohort_name"] == cohort.name
    assert locked_data["locked_only_count"] == 1
    assert locked_data["participation_count"] == 1
    assert len(locked_data["recipients"]) == 1
    assert locked_data["recipients"][0]["student_name"] == "Locked Student Alpha"
    assert locked_data["recipients"][0]["certificate_type_earned"] == "completion"
    assert locked_data["recipients"][0]["team_locked"] is True

    # 2. Test get recipients with participation filter
    resp_part = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/recipients?filter=participation",
        headers=_headers(ops),
    )
    assert resp_part.status_code == 200
    part_data = resp_part.json()
    assert len(part_data["recipients"]) == 1
    assert part_data["recipients"][0]["student_name"] == "Participant Beta"
    assert part_data["recipients"][0]["certificate_type_earned"] == "participation"
    assert part_data["recipients"][0]["team_locked"] is False

    # 3. Test sending with custom email override & save_email_to_template
    with patch("app.services.competitions.certificates.try_send_email") as mock_email:
        mock_email.return_value = None
        send_resp = await client.post(
            f"/competitions/admin/cohorts/{cohort.id}/certificates/send",
            headers=_headers(ops),
            json={
                "filter": "locked_only",
                "template_id": str(custom_template.id),
                "custom_email_subject": "Custom Header for {student_name}",
                "custom_email_body": "<p>Hello {student_name}, congrats to {team_name}!</p>",
                "save_email_to_template": True,
            },
        )
        assert send_resp.status_code == 200, send_resp.text
        res = send_resp.json()
        assert res["sent_count"] == 1
        assert mock_email.called
        call_args = mock_email.call_args[0]
        # subject check
        assert call_args[1] == "Custom Header for Locked Student Alpha"
        # body check
        assert "Hello Locked Student Alpha, congrats to Team Locked!" in call_args[2]

    # Check that custom template email copy was updated in DB
    await db.refresh(custom_template)
    assert custom_template.email_subject == "Custom Header for {student_name}"
    assert custom_template.email_body == "<p>Hello {student_name}, congrats to {team_name}!</p>"

