from decimal import Decimal

from pydantic import BaseModel


class OpsDashboardOut(BaseModel):
    students_trained: int
    active_cohorts: int
    upcoming_meetings_7d: int
    attendance_rate_30d: float
    unpaid_count: int
    unpaid_sum: Decimal
    registrations_7d: int
    open_calls_pending: int
