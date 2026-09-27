"""Daily birthday greetings background task (NASA APOD integration).

Queries users whose birthdate falls on today's date, fetches a randomized
NASA Astronomy Picture of the Day from a past year, dispatches a starry greeting
email, and audits the result in birthday_email_logs.
"""

import calendar
import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import and_, extract, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.birthday_log import BirthdayEmailLog
from app.models.user import User
from app.services.email import send_birthday_greeting_email
from app.services.nasa_apod import get_nasa_birthday_picture

logger = logging.getLogger(__name__)


async def send_single_user_birthday_email(
    db: AsyncSession,
    user: User,
    current_year: int | None = None,
    force: bool = False,
) -> BirthdayEmailLog:
    """Dispatches a birthday email to a single user, logging the outcome.

    If an email with status 'sent' was already dispatched for the target year,
    returns that existing log record unless force=True.
    """
    now = datetime.now(timezone.utc)
    target_year = current_year or now.year

    if not user.birthdate:
        raise ValueError(f"User {user.id} ({user.email}) does not have a birthdate on file.")

    # Check for existing log this year
    existing_log = (
        await db.execute(
            select(BirthdayEmailLog).where(
                BirthdayEmailLog.user_id == user.id,
                BirthdayEmailLog.sent_at_year == target_year,
            ).order_by(BirthdayEmailLog.sent_at.desc())
        )
    ).scalars().first()

    if existing_log and existing_log.status == "sent" and not force:
        logger.info("Birthday email already sent to %s for year %s", user.email, target_year)
        return existing_log

    # 1. Fetch APOD card
    apod_data = await get_nasa_birthday_picture(user.birthdate)
    birth_year_referenced = apod_data.get("year")
    image_url = apod_data.get("image_url")
    title = apod_data.get("title")
    explanation = apod_data.get("explanation")

    # 2. Dispatch email
    email_success = False
    error_msg: str | None = None
    try:
        email_success = await send_birthday_greeting_email(
            to_email=user.email,
            full_name=user.full_name,
            apod_data=apod_data,
        )
        if not email_success:
            error_msg = "SMTP delivery returned failure (check server SMTP credentials/configuration)"
    except Exception as exc:
        logger.exception("Error dispatching birthday email to %s", user.email)
        error_msg = str(exc)

    status = "sent" if email_success else "failed"

    # 3. Create or update log entry
    if existing_log and not force:
        # Retry updating existing failed log
        log_entry = existing_log
        log_entry.sent_at = now
        log_entry.birth_year_referenced = birth_year_referenced
        log_entry.nasa_image_url = image_url
        log_entry.nasa_title = title
        log_entry.nasa_explanation = explanation
        log_entry.status = status
        log_entry.error_message = error_msg
    else:
        log_entry = BirthdayEmailLog(
            user_id=user.id,
            sent_at=now,
            sent_at_year=target_year,
            birth_year_referenced=birth_year_referenced,
            nasa_image_url=image_url,
            nasa_title=title,
            nasa_explanation=explanation,
            status=status,
            error_message=error_msg,
        )
        db.add(log_entry)

    await db.commit()
    await db.refresh(log_entry)
    logger.info("Birthday email logged for user=%s status=%s year=%s", user.email, status, target_year)
    return log_entry


async def send_daily_birthday_emails(ctx: dict | None = None) -> dict[str, Any]:
    """ARQ daily cron job: dispatches NASA APOD birthday emails to all users

    celebrating their birthday today.
    """
    today = datetime.now(timezone.utc).date()
    month = today.month
    day = today.day
    current_year = today.year

    logger.info("Starting daily birthday emails dispatch for %02d-%02d (%d)", month, day, current_year)

    sent_count = 0
    failed_count = 0
    skipped_count = 0

    async with AsyncSessionLocal() as db:
        # Match today's month & day.
        # Handle leap year edge case: on non-leap years, send to Feb 29 birthdays on Feb 28.
        is_leap = calendar.isleap(current_year)
        if month == 2 and day == 28 and not is_leap:
            birthday_filter = or_(
                and_(extract("month", User.birthdate) == 2, extract("day", User.birthdate) == 28),
                and_(extract("month", User.birthdate) == 2, extract("day", User.birthdate) == 29),
            )
        else:
            birthday_filter = and_(
                extract("month", User.birthdate) == month,
                extract("day", User.birthdate) == day,
            )

        users_query = (
            select(User)
            .where(
                User.status == "active",
                User.birthdate.isnot(None),
                birthday_filter,
            )
        )
        users = (await db.execute(users_query)).scalars().all()

        logger.info("Found %d users with birthday today (%02d-%02d)", len(users), month, day)

        for user in users:
            try:
                # Check if already successfully sent this year
                already_sent = await db.scalar(
                    select(BirthdayEmailLog.id).where(
                        BirthdayEmailLog.user_id == user.id,
                        BirthdayEmailLog.sent_at_year == current_year,
                        BirthdayEmailLog.status == "sent",
                    )
                )
                if already_sent:
                    logger.debug("Skipping user %s (already sent in %d)", user.email, current_year)
                    skipped_count += 1
                    continue

                log_entry = await send_single_user_birthday_email(db, user, current_year=current_year)
                if log_entry.status == "sent":
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as exc:
                logger.exception("Failed processing birthday email for user %s: %s", user.email, exc)
                failed_count += 1

    summary = {
        "date": today.isoformat(),
        "total_eligible": len(users),
        "sent": sent_count,
        "failed": failed_count,
        "skipped_already_sent": skipped_count,
    }
    logger.info("Completed daily birthday emails run: %s", summary)
    return summary
