"""LMS completion certificates (2026-08-13) — issued on finishing a course,
and on finishing every course in a learning path. Redis-free.
"""

import uuid

import pytest

from app.core.security import create_access_token
from app.models.certificate import Certificate
from app.models.document_template import DocumentTemplate
from app.models.enums import CertificateType
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.user import User
from app.services.lms import enroll, item_progress
from app.services.lms import certificates as certificates_service
from app.services.lms.certificates import award_for_course_completion
from sqlalchemy import select


@pytest.fixture(autouse=True)
def sent_emails(monkeypatch):
    """Capture instead of send — no SMTP in tests, and the captured list is
    what the notification assertions below read."""
    captured: list[dict] = []

    async def _capture(to, subject, body, **kwargs):
        captured.append({"to": to, "subject": subject, "body": body, **kwargs})
        return True

    monkeypatch.setattr(certificates_service, "try_send_email", _capture)
    return captured


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Certificate Student",
        email=f"cert-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course_with_items(db, *, author, n_items=1, title=None, kind="course") -> tuple[Course, list[ModuleItem]]:
    course = Course(
        id=uuid.uuid4(), title=title or f"Course {uuid.uuid4().hex[:6]}",
        created_by=author.id, is_published=True, kind=kind,
    )
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    items = []
    for i in range(n_items):
        item = ModuleItem(
            id=uuid.uuid4(), module_id=module.id, position=i + 1, kind="text", content={"body": "x"},
        )
        db.add(item)
        items.append(item)
    await db.flush()
    return course, items


async def _finish(db, *, user, items) -> None:
    for item in items:
        await item_progress(db, user_id=user.id, item_id=item.id, action="text-viewed")


@pytest.mark.asyncio
async def test_finishing_a_course_issues_exactly_one_certificate(db, client):
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    course, items = await _course_with_items(db, author=ops, n_items=2, title="Orbital Mechanics")
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    # Halfway through: nothing earned yet.
    await _finish(db, user=student, items=items[:1])
    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()
    assert (await db.execute(select(Certificate).where(Certificate.user_id == student.id))).scalars().all() == []

    # Last item completes it.
    await _finish(db, user=student, items=items[1:])
    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()

    certs = (await db.execute(select(Certificate).where(Certificate.user_id == student.id))).scalars().all()
    assert len(certs) == 1
    assert certs[0].type == CertificateType.lms_course_completion
    assert certs[0].course_id == course.id
    assert certs[0].bucket == "certificates"
    assert certs[0].file_path

    # Re-running (every later progress write does) must not duplicate.
    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()
    again = (await db.execute(select(Certificate).where(Certificate.user_id == student.id))).scalars().all()
    assert len(again) == 1


@pytest.mark.asyncio
async def test_progress_endpoint_issues_the_certificate(db, client):
    """The hook, not just the service — finishing via the real HTTP path."""
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    course, items = await _course_with_items(db, author=ops, n_items=1)
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    resp = await client.post(
        f"/lms/items/{items[0].id}/progress", headers=_headers(student), json={"action": "text-viewed"},
    )
    assert resp.status_code == 200, resp.text

    listed = await client.get("/lms/my-certificates", headers=_headers(student))
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert len(body) == 1
    assert body[0]["type"] == "lms_course_completion"
    assert body[0]["title"] == course.title
    assert body[0]["course_id"] == str(course.id)


@pytest.mark.asyncio
async def test_finishing_every_course_in_a_path_issues_a_path_certificate(db, client):
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    first, first_items = await _course_with_items(db, author=ops)
    second, second_items = await _course_with_items(db, author=ops)

    path = LearningPath(
        id=uuid.uuid4(), title="Space Science Foundations", created_by=ops.id, is_published=True,
    )
    db.add(path)
    await db.flush()
    db.add_all([
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=first.id, position=1),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=second.id, position=2),
    ])
    await enroll(db, user_id=student.id, course_id=first.id)
    await enroll(db, user_id=student.id, course_id=second.id)
    await db.commit()

    # First course done — course cert only, path is still outstanding.
    await _finish(db, user=student, items=first_items)
    await award_for_course_completion(db, user_id=student.id, course_id=first.id)
    await db.commit()
    types = {c.type for c in (await db.execute(
        select(Certificate).where(Certificate.user_id == student.id)
    )).scalars().all()}
    assert types == {CertificateType.lms_course_completion}

    # Second course done — path completes too.
    await _finish(db, user=student, items=second_items)
    await award_for_course_completion(db, user_id=student.id, course_id=second.id)
    await db.commit()

    certs = (await db.execute(select(Certificate).where(Certificate.user_id == student.id))).scalars().all()
    path_certs = [c for c in certs if c.type == CertificateType.lms_path_completion]
    assert len(path_certs) == 1
    assert path_certs[0].learning_path_id == path.id
    assert len([c for c in certs if c.type == CertificateType.lms_course_completion]) == 2


@pytest.mark.asyncio
async def test_a_path_whose_only_remaining_step_is_a_mission_still_completes(db, client):
    """Mission steps aren't gradeable through course_completion (path_progress
    gives them state='mission'), so they must not hold the path certificate
    hostage forever."""
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    course, items = await _course_with_items(db, author=ops)
    mission_course, _ = await _course_with_items(db, author=ops, n_items=0, kind="mission")

    path = LearningPath(id=uuid.uuid4(), title="Mixed Path", created_by=ops.id, is_published=True)
    db.add(path)
    await db.flush()
    db.add_all([
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=mission_course.id, position=2),
    ])
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    await _finish(db, user=student, items=items)
    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()

    path_certs = [c for c in (await db.execute(
        select(Certificate).where(Certificate.user_id == student.id)
    )).scalars().all() if c.type == CertificateType.lms_path_completion]
    assert len(path_certs) == 1


@pytest.mark.asyncio
async def test_an_empty_course_earns_nothing(db, client):
    """A course with no modules would otherwise read as 100% complete and
    hand out a certificate for doing nothing."""
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    course = Course(id=uuid.uuid4(), title="Empty", created_by=ops.id, is_published=True)
    db.add(course)
    await db.flush()
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()
    assert (await db.execute(select(Certificate).where(Certificate.user_id == student.id))).scalars().all() == []


@pytest.mark.asyncio
async def test_certificate_body_comes_from_the_editable_system_template(db, client):
    """The whole point of "same template as the portal" — an admin edit to
    the seeded row changes what gets rendered, with no code change."""
    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "lms_course_completion")
    )).scalars().first()
    assert template is not None, "migration 2608ca6f7434 should have seeded this"
    assert template.is_system is True
    assert template.type == "certificate"
    assert template.roles == []
    assert "{course_name}" in template.body_text


@pytest.mark.asyncio
async def test_my_certificates_only_returns_lms_types(db, client):
    """A staff member's workshop cert belongs on their portal documents page,
    not mixed into the learner profile."""
    staff = await _user(db, roles=["student", "instructor"])
    db.add(Certificate(
        id=uuid.uuid4(), user_id=staff.id, type=CertificateType.workshop_delivery,
        workshop_name="Intro to Orbits",
    ))
    await db.commit()

    resp = await client.get("/lms/my-certificates", headers=_headers(staff))
    assert resp.status_code == 200
    assert resp.json() == []


# ── issue notification (2026-08-13) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_certificate_is_emailed_with_the_pdf_attached(db, client, sent_emails):
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    course, items = await _course_with_items(db, author=ops, n_items=1, title="Orbital Mechanics")
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    await _finish(db, user=student, items=items)
    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()

    assert len(sent_emails) == 1
    email = sent_emails[0]
    assert email["to"] == student.email
    assert "Orbital Mechanics" in email["subject"]
    assert email["html"] is True

    # The PDF itself must ride along — a congratulations mail with no
    # certificate in it is the failure mode worth guarding.
    (filename, payload, kind), = email["attachments"]
    assert filename.endswith(".pdf")
    assert kind == "pdf"
    assert payload.startswith(b"%PDF"), "attachment should be a real PDF, not an empty/placeholder blob"


@pytest.mark.asyncio
async def test_completing_a_path_emails_both_certificates(db, client, sent_emails):
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    course, items = await _course_with_items(db, author=ops, title="Final Course")

    path = LearningPath(id=uuid.uuid4(), title="Foundations", created_by=ops.id, is_published=True)
    db.add(path)
    await db.flush()
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=1))
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    await _finish(db, user=student, items=items)
    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()

    subjects = [e["subject"] for e in sent_emails]
    assert len(subjects) == 2
    assert any("Final Course" in s for s in subjects)
    assert any("Foundations" in s for s in subjects)


@pytest.mark.asyncio
async def test_no_email_is_sent_twice_for_the_same_certificate(db, client, sent_emails):
    """Every later progress write re-runs the award check — it must not
    re-congratulate someone for a course they finished last week."""
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    course, items = await _course_with_items(db, author=ops)
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()

    await _finish(db, user=student, items=items)
    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()
    assert len(sent_emails) == 1

    await award_for_course_completion(db, user_id=student.id, course_id=course.id)
    await db.commit()
    assert len(sent_emails) == 1


@pytest.mark.asyncio
async def test_backfill_issues_certificates_without_emailing(db, client, sent_emails):
    """A student with old completions opening their profile must not get a
    burst of congratulations for work finished weeks ago."""
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    first, first_items = await _course_with_items(db, author=ops)
    second, second_items = await _course_with_items(db, author=ops)
    await enroll(db, user_id=student.id, course_id=first.id)
    await enroll(db, user_id=student.id, course_id=second.id)
    await db.commit()

    # Finish both without ever going through the awarding path — the
    # pre-existing-completion case the backfill exists for.
    await _finish(db, user=student, items=first_items)
    await _finish(db, user=student, items=second_items)
    await db.commit()
    assert sent_emails == []

    resp = await client.get("/lms/my-certificates", headers=_headers(student))
    assert resp.status_code == 200
    assert len(resp.json()) == 2, "backfill should have issued both"
    assert sent_emails == [], "backfill must stay silent"
