"""Background worker job to monitor applicant deadlines, inactivity timeouts, and auto-rejections."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.enums import ApplicationStatus, UserRole
from app.models.instructors.application_review import ApplicationReview
from app.models.user import User
from app.services.email import send_applicant_timeout_rejected_email
from app.services.instructors.deadlines import get_instructor_settings

logger = logging.getLogger(__name__)


async def process_expired_applications(
    ctx: dict | None = None, db_session: AsyncSession | None = None
) -> dict:
    """Daily/periodic cron job that checks for expired deadlines and auto-rejects inactive applicants."""
    now = datetime.now(timezone.utc)
    expired_count = 0

    async def _execute(db: AsyncSession) -> int:
        nonlocal expired_count
        settings = await get_instructor_settings(db)
        hard_timeout_days = settings.get("instructor_hard_timeout_days", 10)
        ext_days = settings.get("instructor_extension_days", 1)
        hard_cutoff = now - timedelta(days=hard_timeout_days)
        ext_cutoff = now - timedelta(days=ext_days)

        # Only phases where action is pending on the applicant's side are subject to expiration.
        # Applications in `under_review` are awaiting admin action and must never be auto-rejected.
        applicant_active_statuses = [
            ApplicationStatus.in_progress,
            ApplicationStatus.phase_1_approved,
            ApplicationStatus.research_approved,
        ]

        stmt = (
            select(ApplicationReview, User)
            .join(User, User.id == ApplicationReview.user_id)
            .where(
                ApplicationReview.status.in_(applicant_active_statuses),
                User.roles.any("applicant"),
                or_(
                    ApplicationReview.last_status_change_at < hard_cutoff,
                    and_(
                        ApplicationReview.phase_deadline.isnot(None),
                        ApplicationReview.extension_used.is_(True),
                        ApplicationReview.phase_deadline < now,
                    ),
                    and_(
                        ApplicationReview.phase_deadline.isnot(None),
                        ApplicationReview.extension_used.is_(False),
                        ApplicationReview.phase_deadline < ext_cutoff,
                    ),
                ),
            )
        )
        rows = (await db.execute(stmt)).all()

        for review, user in rows:
            try:
                review.status = ApplicationStatus.rejected
                review.feedback = (
                    "Application closed automatically due to deadline expiration or inactivity. "
                    "Your student account remains active."
                )
                review.reviewed_at = now
                review.last_status_change_at = now
                review.phase_deadline = None

                # Revert: strip applicant, ensure student role is present if no other role
                kept = [r for r in user.role_values if r != UserRole.applicant.value]
                if not kept:
                    kept = [UserRole.student.value]
                user.roles = [UserRole(r) for r in kept]

                await db.commit()
                expired_count += 1
                logger.info(
                    "Auto-rejected expired applicant %s (%s). Reverted roles: %s",
                    user.id,
                    user.email,
                    user.roles,
                )

                try:
                    await send_applicant_timeout_rejected_email(user.email, user.full_name)
                except Exception as email_exc:
                    logger.warning("Failed sending timeout rejection email to %s: %s", user.email, email_exc)

            except Exception as exc:
                await db.rollback()
                logger.exception("Failed processing expired application for user %s: %s", user.id, exc)

        return expired_count

    session = db_session or (ctx.get("db") if ctx else None)
    if session:
        await _execute(session)
    else:
        async with AsyncSessionLocal() as db:
            await _execute(db)

    summary = {"timestamp": now.isoformat(), "expired_count": expired_count}
    logger.info("Completed process_expired_applications run: %s", summary)
    return summary
