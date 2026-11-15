from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


DashboardRange = Literal["1h", "24h", "7d", "30d", "all"]
MilestoneKindFilter = Literal["all", "course", "mission", "quiz", "team"]


class OpsDashboardOut(BaseModel):
    students_trained: int
    active_cohorts: int
    upcoming_meetings_7d: int
    attendance_rate_30d: float
    unpaid_count: int
    unpaid_sum: Decimal
    registrations_7d: int
    open_calls_pending: int


class DashboardFunnelOut(BaseModel):
    enrolled: int
    active: int
    completed: int


class ActiveTeamsSummaryOut(BaseModel):
    active: int
    total: int
    locked: int


class TopInviteCodeOut(BaseModel):
    code: str
    label: str | None = None
    redeemed: int
    active: int


class ActiveProgramProgressOut(BaseModel):
    cohort_id: str
    cohort_name: str
    students: int
    completed_pct: int
    active_pct: int
    not_started_pct: int
    engaged_pct: int


class StudentMilestoneOut(BaseModel):
    id: str
    kind: Literal["course", "mission", "quiz", "team"]
    title: str
    actor_name: str
    meta: str | None = None
    tone: Literal["green", "purple", "rose", "neutral"]
    link: str | None = None
    timestamp: datetime


class PaginatedMilestonesOut(BaseModel):
    items: list[StudentMilestoneOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class WarehouseInventoryDeltaOut(BaseModel):
    warehouse_id: str
    warehouse_name: str
    added: int
    removed: int


class WarehouseMovementRowOut(BaseModel):
    id: str
    item_label: str
    qty_display: str
    tone: Literal["green", "rose", "purple"]
    warehouse_label: str
    reason: str
    actor_name: str | None = None
    created_at: datetime


class OpsDashboardOverviewOut(BaseModel):
    range: DashboardRange
    active_cohorts: int
    upcoming_sessions_7d: int
    active_learners: int
    learner_trend: list[int]
    learner_delta_label: str
    funnel: DashboardFunnelOut
    active_teams: ActiveTeamsSummaryOut
    avg_course_completion_pct: float
    avg_mission_completion_pct: float
    top_invite_codes: list[TopInviteCodeOut]
    active_programs: list[ActiveProgramProgressOut]
    milestones: PaginatedMilestonesOut
    warehouses: list[WarehouseInventoryDeltaOut]
    recent_movements: list[WarehouseMovementRowOut]
