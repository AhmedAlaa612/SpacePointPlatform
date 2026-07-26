from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.schemas.sessions.dashboard import OpsDashboardOut


async def get_ops_dashboard(db: AsyncSession) -> OpsDashboardOut:
    now = datetime.now(timezone.utc)
    today = now.date()
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=30)

    # students_trained: non-cancelled registrations on completed cohorts
    trained = await db.scalar(
        select(func.count(Registration.id)).where(
            Registration.status != "cancelled",
            Registration.cohort_id.in_(
                select(Cohort.id).where(Cohort.status == "completed")
            ),
        )
    ) or 0

    # active_cohorts
    active = await db.scalar(
        select(func.count(Cohort.id)).where(Cohort.status == "running")
    ) or 0

    # upcoming_meetings_7d
    upcoming = await db.scalar(
        select(func.count(Session.id)).where(
            Session.meeting_date.between(today, today + timedelta(days=7))
        )
    ) or 0

    # attendance_rate_30d
    total_records_30d = await db.scalar(
        select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.recorded_at >= thirty_days_ago
        )
    ) or 0
    present_records_30d = await db.scalar(
        select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.att_status == "present",
            AttendanceRecord.recorded_at >= thirty_days_ago,
        )
    ) or 0
    attendance_rate = (present_records_30d / total_records_30d) if total_records_30d else 0.0

    # unpaid count + sum
    unpaid = (await db.execute(
        select(
            func.count(Registration.id),
            func.coalesce(func.sum(Registration.price_charged), 0),
        ).where(Registration.payment_status == "unpaid")
    )).one()
    unpaid_count = unpaid[0] or 0
    unpaid_sum = unpaid[1]

    # registrations_7d
    regs_7d = await db.scalar(
        select(func.count(Registration.id)).where(
            Registration.created_at >= seven_days_ago
        )
    ) or 0

    # open_calls_pending
    open_calls = await db.scalar(
        select(func.count(Session.id)).where(
            Session.staffing_status == "open_call"
        )
    ) or 0

    return OpsDashboardOut(
        students_trained=trained,
        active_cohorts=active,
        upcoming_meetings_7d=upcoming,
        attendance_rate_30d=round(attendance_rate, 4),
        unpaid_count=unpaid_count,
        unpaid_sum=unpaid_sum,
        registrations_7d=regs_7d,
        open_calls_pending=open_calls,
    )
