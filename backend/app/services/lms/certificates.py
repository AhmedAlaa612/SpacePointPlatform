"""LMS completion certificates (2026-08-13).

A student earns one by finishing a course, and one by finishing every course
in a learning path. Both render through the same generator and the same
editable `document_templates` rows as every other certificate on the
platform (`services/documents/certificate.py`) — the only thing new here is
*when* they're issued and *what* they're keyed to.

Two deliberate differences from `_issue_student_certificate`
(services/sessions/delivery.py), the closest existing analogue:

- **User-owned, not contact-owned.** An LMS learner always has a User row
  (enrollments key on user_id); a public cohort registrant may not.
- **Stored, not just emailed.** Cohort certs are emailed as an attachment and
  the DB row keeps no file pointer. These have to be listable and
  re-downloadable from the student's own profile, so the PDF goes to the
  `certificates` bucket and the row records bucket/file_path (URLs signed at
  query time, the resolve_url pattern).

Idempotency is enforced by the partial unique indexes added in migration
2608ca6f7434, not by the `existing` check alone — two concurrent
item-progress writes can both observe "not yet issued" before either
inserts, and the index is what actually stops the duplicate. The
IntegrityError that loser sees is caught and treated as success.
"""

from __future__ import annotations

import asyncio
from datetime import date
from html import escape
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.models.document_template import DocumentTemplate
from app.models.enums import CertificateType
from app.models.lms.course import Course
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.user import User
from app.services import storage
from app.services.documents.certificate import generate_completion_certificate_pdf
from app.services.email import try_send_email
from app.services.lms.progress import course_completion

CERTIFICATE_BUCKET = "certificates"

_FALLBACK_BODY = {
    "lms_course_completion": "For successfully completing the course<br/><b>{course_name}</b><br/>{date}",
    "lms_path_completion": "For successfully completing the learning path<br/><b>{path_name}</b><br/>{date}",
}


async def _template_body(db: AsyncSession, key: str) -> str:
    """The admin-editable system template, falling back to the seeded wording
    if the row was deleted — a missing template must never be the reason a
    student doesn't get their certificate."""
    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == key)
    )).scalars().first()
    return template.body_text if template and template.body_text else _FALLBACK_BODY[key]


async def _render_and_store(
    db: AsyncSession, *, user: User, key: str, tokens: dict[str, str], filename_stem: str,
) -> tuple[str, str, bytes]:
    """Returns (bucket, path, pdf_bytes). reportlab is synchronous and
    CPU-bound — run it off the event loop, same as every other certificate
    call site. The bytes come back so the notification email can attach the
    PDF without re-downloading what we just uploaded."""
    body = await _template_body(db, key)
    for token, value in tokens.items():
        body = body.replace("{" + token + "}", escape(value))

    pdf = await asyncio.to_thread(generate_completion_certificate_pdf, user.full_name, body)
    path = f"{user.id}/{filename_stem}-{uuid4().hex[:8]}.pdf"
    await storage.upload_to_path(CERTIFICATE_BUCKET, path, pdf, "application/pdf")
    return CERTIFICATE_BUCKET, path, pdf


def _today() -> str:
    return date.today().strftime("%d %B %Y").lstrip("0")


def _email_body(name: str, what: str, kind: str) -> str:
    return (
        f"<p>Hi {escape(name)},</p>"
        f"<p>Congratulations on completing the {kind} <strong>{escape(what)}</strong>!</p>"
        "<p>Your certificate is attached to this email as a PDF. You can also download it any time "
        "from your profile.</p>"
        "<p>— SpacePoint</p>"
    )


async def _notify(user: User, *, what: str, kind: str, pdf: bytes) -> None:
    """Best-effort — a certificate is earned whether or not SMTP is up, and
    the row is already committed by the caller. Mirrors
    `_issue_student_certificate`'s posture (services/sessions/delivery.py):
    log and move on, never surface the failure."""
    if not user.email:
        return
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in what).strip("_") or "certificate"
    await try_send_email(
        user.email,
        f"Your SpacePoint certificate — {what}",
        _email_body(user.full_name, what, kind),
        html=True,
        attachments=[(f"SpacePoint_Certificate_{safe}.pdf", pdf, "pdf")],
    )


async def issue_course_certificate(
    db: AsyncSession, *, user_id: UUID, course_id: UUID, notify: bool = True,
) -> Certificate | None:
    """Idempotent. Returns the existing row if this student already has a
    certificate for this course, a new one if it was just earned, or None if
    the course/user no longer exists. Caller commits.

    `notify=False` for backfill (see `award_for_course_completion`) — an
    email only makes sense for a certificate earned just now."""
    existing = (await db.execute(
        select(Certificate).where(
            Certificate.user_id == user_id, Certificate.course_id == course_id,
        )
    )).scalars().first()
    if existing is not None:
        return existing

    user = await db.get(User, user_id)
    course = await db.get(Course, course_id)
    if user is None or course is None:
        return None

    bucket, path, pdf = await _render_and_store(
        db, user=user, key="lms_course_completion",
        tokens={"course_name": course.title, "date": _today()},
        filename_stem="course",
    )
    certificate = Certificate(
        id=uuid4(), user_id=user_id, course_id=course_id,
        type=CertificateType.lms_course_completion,
        bucket=bucket, file_path=path,
    )
    # SAVEPOINT, not a bare flush: this runs inside the caller's transaction,
    # which already contains the student's progress write. A plain
    # IntegrityError would poison that transaction and `db.rollback()` would
    # throw the progress away — losing real work to a duplicate-certificate
    # race. The nested block confines the failure to this insert.
    try:
        async with db.begin_nested():
            db.add(certificate)
    except IntegrityError:
        # Lost the race against a concurrent write — the other one issued it,
        # which is the outcome we wanted anyway.
        return (await db.execute(
            select(Certificate).where(
                Certificate.user_id == user_id, Certificate.course_id == course_id,
            )
        )).scalars().first()

    if notify:
        await _notify(user, what=course.title, kind="course", pdf=pdf)
    return certificate


async def issue_path_certificate(
    db: AsyncSession, *, user_id: UUID, path_id: UUID, notify: bool = True,
) -> Certificate | None:
    existing = (await db.execute(
        select(Certificate).where(
            Certificate.user_id == user_id, Certificate.learning_path_id == path_id,
        )
    )).scalars().first()
    if existing is not None:
        return existing

    user = await db.get(User, user_id)
    path = await db.get(LearningPath, path_id)
    if user is None or path is None:
        return None

    bucket, stored, pdf = await _render_and_store(
        db, user=user, key="lms_path_completion",
        tokens={"path_name": path.title, "date": _today()},
        filename_stem="path",
    )
    certificate = Certificate(
        id=uuid4(), user_id=user_id, learning_path_id=path_id,
        type=CertificateType.lms_path_completion,
        bucket=bucket, file_path=stored,
    )
    # SAVEPOINT — see the note in issue_course_certificate above.
    try:
        async with db.begin_nested():
            db.add(certificate)
    except IntegrityError:
        return (await db.execute(
            select(Certificate).where(
                Certificate.user_id == user_id, Certificate.learning_path_id == path_id,
            )
        )).scalars().first()

    if notify:
        await _notify(user, what=path.title, kind="learning path", pdf=pdf)
    return certificate


async def _path_is_complete(db: AsyncSession, *, user_id: UUID, path_id: UUID) -> bool:
    """Every course-kind step finished. Mission steps are skipped — they're
    not gradeable through `course_completion` (path_progress gives them
    state='mission' for the same reason), so a path whose only outstanding
    step is a mission still counts as complete. A path with no course steps
    at all is never complete: there'd be nothing to have earned."""
    steps = (await db.execute(
        select(LearningPathStep).where(LearningPathStep.learning_path_id == path_id)
    )).scalars().all()
    if not steps:
        return False

    course_ids = [s.course_id for s in steps]
    courses = (await db.execute(select(Course).where(Course.id.in_(course_ids)))).scalars().all()
    gradeable = [c for c in courses if c.kind != "mission"]
    if not gradeable:
        return False

    for course in gradeable:
        completion = await course_completion(db, user_id=user_id, course_id=course.id)
        if not (completion["completed"] and completion["modules"]):
            return False
    return True


async def award_for_course_completion(
    db: AsyncSession, *, user_id: UUID, course_id: UUID, notify: bool = True,
) -> list[Certificate]:
    """Called after any progress write. Issues the course certificate if the
    course is now finished, then any learning-path certificate that finishing
    it completed. Returns whatever was newly issued or already held — callers
    generally ignore it and just commit.

    Cheap in the common case: `course_completion` is one batched read and
    returns False long before any PDF work happens. The expensive path (PDF
    render + upload) only runs on the single request that finishes a course.

    `notify=False` is for the backfill path (`GET /lms/my-certificates`),
    which can issue many certificates in one sweep for work finished long
    ago — mailing all of them at once would be a burst of congratulations
    for things the student did weeks earlier. Only a certificate earned in
    the moment gets an email.
    """
    issued: list[Certificate] = []

    completion = await course_completion(db, user_id=user_id, course_id=course_id)
    if not (completion["completed"] and completion["modules"]):
        return issued

    certificate = await issue_course_certificate(
        db, user_id=user_id, course_id=course_id, notify=notify,
    )
    if certificate is not None:
        issued.append(certificate)

    # Finishing this course may have been the last step of one or more paths.
    path_ids = (await db.execute(
        select(LearningPathStep.learning_path_id).where(LearningPathStep.course_id == course_id).distinct()
    )).scalars().all()
    for path_id in path_ids:
        if await _path_is_complete(db, user_id=user_id, path_id=path_id):
            path_cert = await issue_path_certificate(
                db, user_id=user_id, path_id=path_id, notify=notify,
            )
            if path_cert is not None:
                issued.append(path_cert)

    return issued
