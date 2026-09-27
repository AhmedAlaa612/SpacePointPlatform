import calendar
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user, require_admin
from app.db.session import get_db
from app.models.birthday_log import BirthdayEmailLog
from app.models.user import User
from app.schemas.birthday import BirthdayLogOut, BirthdayLogsResponse, BirthdayStatsOut, UpcomingBirthdayUser
from app.workers.tasks.birthdays import send_single_user_birthday_email

router = APIRouter(tags=["admin-birthdays"])


def _calculate_next_birthday(birthdate: date, today: date) -> tuple[int, date]:
    """Calculates days until next birthday and the next birthday date,

    properly handling February 29 leap day birthdays.
    """
    month = birthdate.month
    day = birthdate.day

    # Attempt to place birthday in the current calendar year
    try:
        bday_this_year = date(today.year, month, day)
    except ValueError:
        # Month 2, Day 29 on non-leap year -> celebrate Feb 28
        bday_this_year = date(today.year, 2, 28)

    if bday_this_year >= today:
        next_bday = bday_this_year
    else:
        # Next year
        next_year = today.year + 1
        try:
            next_bday = date(next_year, month, day)
        except ValueError:
            next_bday = date(next_year, 2, 28)

    days_until = (next_bday - today).days
    return days_until, next_bday


@router.get("/upcoming", response_model=list[UpcomingBirthdayUser])
async def get_upcoming_birthdays(
    days: int = Query(30, ge=1, le=365, description="Number of days ahead to look"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Returns users whose birthdays are coming up in the next N days (ordered by days remaining)."""
    today = datetime.now(timezone.utc).date()
    current_year = today.year

    # Query all active users who have a birthdate
    stmt = (
        select(User)
        .where(
            User.status == "active",
            User.birthdate.isnot(None),
        )
    )
    users = (await db.execute(stmt)).scalars().all()

    # Get set of user IDs who already have a "sent" birthday email log this year
    sent_logs = (
        await db.execute(
            select(BirthdayEmailLog.user_id)
            .where(
                BirthdayEmailLog.sent_at_year == current_year,
                BirthdayEmailLog.status == "sent",
            )
        )
    ).scalars().all()
    sent_user_ids = set(sent_logs)

    upcoming_list: list[UpcomingBirthdayUser] = []

    for user in users:
        if not user.birthdate:
            continue

        days_until, next_bday = _calculate_next_birthday(user.birthdate, today)

        if 0 <= days_until <= days:
            upcoming_list.append(
                UpcomingBirthdayUser(
                    id=user.id,
                    full_name=user.full_name,
                    email=user.email,
                    roles=user.role_values,
                    birthdate=user.birthdate,
                    days_until=days_until,
                    next_birthday=next_bday,
                    photo_url=user.photo_url,
                    status=user.status,
                    has_sent_this_year=(user.id in sent_user_ids),
                )
            )

    # Order by days remaining ascending
    upcoming_list.sort(key=lambda u: (u.days_until, u.full_name.lower()))
    return upcoming_list


@router.get("/logs", response_model=BirthdayLogsResponse)
async def get_birthday_email_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Returns paginated history from birthday_email_logs with user details, image thumbnail, date, and status."""
    query = select(BirthdayEmailLog).options(selectinload(BirthdayEmailLog.user))

    if status_filter:
        query = query.where(BirthdayEmailLog.status == status_filter.lower())

    # Total count
    count_query = select(func.count(BirthdayEmailLog.id))
    if status_filter:
        count_query = count_query.where(BirthdayEmailLog.status == status_filter.lower())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(BirthdayEmailLog.sent_at.desc()).offset((page - 1) * page_size).limit(page_size)
    logs = (await db.execute(query)).scalars().all()

    items: list[BirthdayLogOut] = []
    for log in logs:
        u = log.user
        items.append(
            BirthdayLogOut(
                id=log.id,
                user_id=log.user_id,
                user_full_name=u.full_name if u else "Unknown User",
                user_email=u.email if u else "Unknown Email",
                user_roles=u.role_values if u else [],
                sent_at=log.sent_at,
                sent_at_year=log.sent_at_year,
                birth_year_referenced=log.birth_year_referenced,
                nasa_image_url=log.nasa_image_url,
                nasa_title=log.nasa_title,
                nasa_explanation=log.nasa_explanation,
                status=log.status,
                error_message=log.error_message,
            )
        )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return BirthdayLogsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/retry/{log_id_or_user_id}", response_model=BirthdayLogOut)
async def retry_birthday_email(
    log_id_or_user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Manually re-triggers the birthday email dispatch for a user whose previous send failed or was missed."""
    target_user: User | None = None

    # Check if target is a BirthdayEmailLog ID
    log = (
        await db.execute(
            select(BirthdayEmailLog)
            .options(selectinload(BirthdayEmailLog.user))
            .where(BirthdayEmailLog.id == log_id_or_user_id)
        )
    ).scalars().first()

    if log and log.user:
        target_user = log.user
    else:
        # Check if target is a User ID
        target_user = (
            await db.execute(
                select(User).where(User.id == log_id_or_user_id)
            )
        ).scalars().first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Birthday record or user not found with that identifier",
        )

    if not target_user.birthdate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {target_user.full_name} does not have a birthdate on file. Please set their birthdate first.",
        )

    # Force re-send
    updated_log = await send_single_user_birthday_email(db, target_user, force=True)

    return BirthdayLogOut(
        id=updated_log.id,
        user_id=target_user.id,
        user_full_name=target_user.full_name,
        user_email=target_user.email,
        user_roles=target_user.role_values,
        sent_at=updated_log.sent_at,
        sent_at_year=updated_log.sent_at_year,
        birth_year_referenced=updated_log.birth_year_referenced,
        nasa_image_url=updated_log.nasa_image_url,
        nasa_title=updated_log.nasa_title,
        nasa_explanation=updated_log.nasa_explanation,
        status=updated_log.status,
        error_message=updated_log.error_message,
    )


@router.get("/stats", response_model=BirthdayStatsOut)
async def get_birthday_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Summary counts for birthday dispatch operations dashboard."""
    today = datetime.now(timezone.utc).date()
    current_year = today.year

    total_with_birthdays = (
        await db.scalar(
            select(func.count(User.id)).where(
                User.status == "active",
                User.birthdate.isnot(None),
            )
        )
    ) or 0

    sent_this_year = (
        await db.scalar(
            select(func.count(BirthdayEmailLog.id)).where(
                BirthdayEmailLog.sent_at_year == current_year,
                BirthdayEmailLog.status == "sent",
            )
        )
    ) or 0

    failed_count = (
        await db.scalar(
            select(func.count(BirthdayEmailLog.id)).where(
                BirthdayEmailLog.sent_at_year == current_year,
                BirthdayEmailLog.status == "failed",
            )
        )
    ) or 0

    # Calculate 7 and 30 day upcoming
    active_users = (
        await db.execute(
            select(User.birthdate).where(
                User.status == "active",
                User.birthdate.isnot(None),
            )
        )
    ).scalars().all()

    upcoming_7 = 0
    upcoming_30 = 0
    for bdate in active_users:
        if not bdate:
            continue
        days_until, _ = _calculate_next_birthday(bdate, today)
        if 0 <= days_until <= 7:
            upcoming_7 += 1
        if 0 <= days_until <= 30:
            upcoming_30 += 1

    return BirthdayStatsOut(
        total_with_birthdays=total_with_birthdays,
        sent_this_year=sent_this_year,
        upcoming_7_days=upcoming_7,
        upcoming_30_days=upcoming_30,
        failed_count=failed_count,
    )
