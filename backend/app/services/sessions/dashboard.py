from datetime import datetime, timedelta, timezone
import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.games.run import GameParticipant
from app.models.instructors.invitation_code import InvitationCode
from app.models.inventory.item import Item
from app.models.inventory.kit import Kit
from app.models.inventory.movement import Movement
from app.models.inventory.warehouse import Warehouse
from app.models.lms.arcade_game import ArcadeGameAttempt
from app.models.lms.cohort_quiz import CohortQuizAttempt, CohortQuizTemplate
from app.models.lms.course import Course, CourseModule, ModuleItem
from app.models.lms.enrollment import Enrollment, ItemProgress
from app.models.lms.invite_grant import UserInvitationCode
from app.models.lms.program import (
    LmsProgram,
    LmsProgramAssignment,
    LmsProgramCohortOverride,
    LmsProgramItem,
    LmsProgramItemProgress,
    LmsProgramTeamItemProgress,
)
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.team import Team
from app.models.user import User
from app.schemas.sessions.dashboard import (
    ActiveProgramProgressOut,
    ActiveTeamsSummaryOut,
    DashboardFunnelOut,
    DashboardRange,
    MilestoneKindFilter,
    OpsDashboardOut,
    OpsDashboardOverviewOut,
    PaginatedMilestonesOut,
    StudentMilestoneOut,
    TopInviteCodeOut,
    WarehouseInventoryDeltaOut,
    WarehouseMovementRowOut,
)
from app.services.lms.admin_progress import courses_overview, missions_overview


async def get_ops_dashboard(db: AsyncSession) -> OpsDashboardOut:
    now = datetime.now(timezone.utc)
    today = now.date()
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=30)

    trained = await db.scalar(
        select(func.count(Registration.id)).where(
            Registration.status != "cancelled",
            Registration.cohort_id.in_(
                select(Cohort.id).where(
                    Cohort.status == "completed",
                    Cohort.is_template_legacy.is_(False),
                    Cohort.management_mode == "spacepoint",
                )
            ),
        )
    ) or 0

    active = await db.scalar(
        select(func.count(Cohort.id)).where(
            Cohort.status == "running",
            Cohort.is_template_legacy.is_(False),
            Cohort.management_mode == "spacepoint",
        )
    ) or 0

    upcoming = await db.scalar(
        select(func.count(Session.id))
        .join(Cohort, Cohort.id == Session.cohort_id)
        .where(
            Session.meeting_date.between(today, today + timedelta(days=7)),
            Cohort.is_template_legacy.is_(False),
            Cohort.status != "draft",
            ~Cohort.name.ilike("[Template]%"),
            Cohort.management_mode == "spacepoint",
        )
    ) or 0

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

    unpaid = (await db.execute(
        select(
            func.count(Registration.id),
            func.coalesce(func.sum(Registration.price_charged), 0),
        ).where(Registration.payment_status == "unpaid")
    )).one()
    unpaid_count = unpaid[0] or 0
    unpaid_sum = unpaid[1]

    regs_7d = await db.scalar(
        select(func.count(Registration.id)).where(
            Registration.created_at >= seven_days_ago
        )
    ) or 0

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


_RANGE_DELTAS: dict[DashboardRange, timedelta | None] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}

_RANGE_BUCKET_COUNT: dict[DashboardRange, int] = {
    "1h": 6,
    "24h": 8,
    "7d": 7,
    "30d": 6,
    "all": 6,
}


def _resolve_cutoff(now: datetime, range_key: DashboardRange) -> datetime | None:
    delta = _RANGE_DELTAS[range_key]
    return now - delta if delta is not None else None


async def _collect_activity_events(
    db: AsyncSession,
    cutoff: datetime | None,
) -> list[tuple[uuid.UUID, datetime]]:
    """Collect (user_id, occurred_at) across all student LMS, mission, quiz, and game signals."""
    pairs: list[tuple[uuid.UUID, datetime]] = []

    ip_stmt = select(ItemProgress.user_id, ItemProgress.updated_at).where(
        ItemProgress.updated_at.isnot(None)
    )
    lpip_stmt = (
        select(LmsProgramAssignment.user_id, LmsProgramItemProgress.updated_at)
        .join(LmsProgramAssignment, LmsProgramAssignment.id == LmsProgramItemProgress.assignment_id)
        .where(
            LmsProgramAssignment.mode == "participant",
            LmsProgramItemProgress.updated_at.isnot(None),
        )
    )
    quiz_stmt = select(CohortQuizAttempt.user_id, CohortQuizAttempt.started_at).where(
        CohortQuizAttempt.started_at.isnot(None)
    )
    mission_stmt = select(
        MissionAttempt.user_id,
        func.coalesce(MissionAttempt.submitted_at, MissionAttempt.started_at),
    ).where(MissionAttempt.user_id.isnot(None))
    arcade_stmt = select(ArcadeGameAttempt.user_id, ArcadeGameAttempt.completed_at).where(
        ArcadeGameAttempt.completed_at.isnot(None)
    )
    game_stmt = select(GameParticipant.user_id, GameParticipant.joined_at).where(
        GameParticipant.joined_at.isnot(None)
    )

    if cutoff is not None:
        ip_stmt = ip_stmt.where(ItemProgress.updated_at >= cutoff)
        lpip_stmt = lpip_stmt.where(LmsProgramItemProgress.updated_at >= cutoff)
        quiz_stmt = quiz_stmt.where(CohortQuizAttempt.started_at >= cutoff)
        mission_stmt = mission_stmt.where(
            func.coalesce(MissionAttempt.submitted_at, MissionAttempt.started_at) >= cutoff
        )
        arcade_stmt = arcade_stmt.where(ArcadeGameAttempt.completed_at >= cutoff)
        game_stmt = game_stmt.where(GameParticipant.joined_at >= cutoff)

    for stmt in (ip_stmt, lpip_stmt, quiz_stmt, mission_stmt, arcade_stmt, game_stmt):
        rows = (await db.execute(stmt)).all()
        for uid, ts in rows:
            if uid is not None and ts is not None:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                pairs.append((uid, ts))
    return pairs


def _bucket_learner_trend(
    events: list[tuple[uuid.UUID, datetime]],
    now: datetime,
    range_key: DashboardRange,
    cutoff: datetime | None,
) -> list[int]:
    n_buckets = _RANGE_BUCKET_COUNT[range_key]
    if not events:
        return [0] * n_buckets

    if cutoff is None:
        start = min(ts for _, ts in events)
        if start >= now - timedelta(hours=1):
            start = now - timedelta(days=30)
    else:
        start = cutoff

    span = max((now - start).total_seconds(), 1.0)
    bucket_sets: list[set[uuid.UUID]] = [set() for _ in range(n_buckets)]
    for uid, ts in events:
        ratio = (ts - start).total_seconds() / span
        idx = min(n_buckets - 1, max(0, int(ratio * n_buckets)))
        bucket_sets[idx].add(uid)
    return [len(s) for s in bucket_sets]


async def _delta_label(
    db: AsyncSession,
    active_count: int,
    now: datetime,
    range_key: DashboardRange,
) -> str:
    if range_key == "1h":
        return "Last 60 min"
    if range_key == "all":
        return "Across all records"

    delta = _RANGE_DELTAS[range_key]
    assert delta is not None
    prev_start = now - (delta * 2)
    prev_end = now - delta
    prev_events = await _collect_activity_events(db, prev_start)
    prev_users = {uid for uid, ts in prev_events if ts < prev_end}
    if not prev_users:
        return f"Last {range_key}"
    pct = round(((active_count - len(prev_users)) / len(prev_users)) * 100)
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct}% vs prior {range_key}"


async def _fetch_team_summary(
    db: AsyncSession,
    cutoff: datetime | None,
    range_key: DashboardRange,
) -> ActiveTeamsSummaryOut:
    cohort_filter = Cohort.status == "running" if range_key != "all" else Cohort.status != "cancelled"
    teams = (
        await db.execute(
            select(Team.id, Team.final_locked_at, Team.created_at)
        .join(Cohort, Cohort.id == Team.cohort_id)
        .where(
            Team.is_observer.is_(False),
            cohort_filter,
            Cohort.is_template_legacy.is_(False),
            Cohort.management_mode == "spacepoint",
        )
        )
    ).all()
    if not teams:
        return ActiveTeamsSummaryOut(active=0, total=0, locked=0)

    team_ids = [t.id for t in teams]
    locked = sum(1 for t in teams if t.final_locked_at is not None)

    active_ids: set[uuid.UUID] = set()
    tip_stmt = select(LmsProgramTeamItemProgress.team_id).where(
        LmsProgramTeamItemProgress.team_id.in_(team_ids),
        LmsProgramTeamItemProgress.updated_at.isnot(None),
    )
    ma_stmt = select(MissionAttempt.team_id).where(MissionAttempt.team_id.in_(team_ids))

    if cutoff is not None:
        tip_stmt = tip_stmt.where(LmsProgramTeamItemProgress.updated_at >= cutoff)
        ma_stmt = ma_stmt.where(
            func.coalesce(MissionAttempt.submitted_at, MissionAttempt.started_at) >= cutoff
        )
        for t in teams:
            if t.final_locked_at is not None:
                ts = t.final_locked_at
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    active_ids.add(t.id)
    else:
        for t in teams:
            if t.final_locked_at is not None:
                active_ids.add(t.id)

    for (tid,) in (await db.execute(tip_stmt)).all():
        if tid is not None:
            active_ids.add(tid)
    for (tid,) in (await db.execute(ma_stmt)).all():
        if tid is not None:
            active_ids.add(tid)

    return ActiveTeamsSummaryOut(
        active=len(active_ids),
        total=len(teams),
        locked=locked,
    )


async def _fetch_top_invite_codes(
    db: AsyncSession,
    active_users: set[uuid.UUID],
    cutoff: datetime | None,
) -> list[TopInviteCodeOut]:
    codes = (
        await db.execute(
            select(InvitationCode)
            .where(InvitationCode.kind == "student")
            .order_by(InvitationCode.used_count.desc(), InvitationCode.created_at.desc())
            .limit(40)
        )
    ).scalars().all()
    if not codes:
        return []

    code_ids = [c.id for c in codes]
    redemption_stmt = select(
        UserInvitationCode.invitation_code_id,
        UserInvitationCode.user_id,
    ).where(UserInvitationCode.invitation_code_id.in_(code_ids))
    if cutoff is not None:
        redemption_stmt = redemption_stmt.where(UserInvitationCode.redeemed_at >= cutoff)

    users_by_code: dict[uuid.UUID, set[uuid.UUID]] = {}
    for cid, uid in (await db.execute(redemption_stmt)).all():
        users_by_code.setdefault(cid, set()).add(uid)

    rows: list[TopInviteCodeOut] = []
    for c in codes:
        uids = users_by_code.get(c.id, set())
        redeemed = len(uids) if cutoff is not None else max(c.used_count, len(uids))
        active = len(uids & active_users)
        if cutoff is not None and redeemed == 0:
            continue
        rows.append(
            TopInviteCodeOut(
                code=c.code,
                label=c.label,
                redeemed=redeemed,
                active=active,
            )
        )

    rows.sort(key=lambda r: (r.redeemed, r.active), reverse=True)
    return rows[:25]


async def _fetch_active_programs(db: AsyncSession) -> list[ActiveProgramProgressOut]:
    running_cohorts = (
        await db.execute(
            select(Cohort)
            .where(
                Cohort.status == "running",
                Cohort.is_template_legacy.is_(False),
                Cohort.management_mode == "spacepoint",
            )
            .order_by(Cohort.starts_on.asc().nulls_last(), Cohort.created_at.desc())
            .limit(6)
        )
    ).scalars().all()
    if not running_cohorts:
        return []

    cohort_ids = [c.id for c in running_cohorts]
    assignments = (
        await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.cohort_id.in_(cohort_ids),
                LmsProgramAssignment.mode == "participant",
            )
        )
    ).scalars().all()

    by_cohort: dict[uuid.UUID, list[LmsProgramAssignment]] = {}
    for a in assignments:
        if a.cohort_id is not None:
            by_cohort.setdefault(a.cohort_id, []).append(a)

    overrides = {
        ov.cohort_id: ov.id
        for ov in (
            await db.execute(
                select(LmsProgramCohortOverride).where(
                    LmsProgramCohortOverride.cohort_id.in_(cohort_ids)
                )
            )
        ).scalars().all()
    }
    base_lms_by_program = {
        lp.program_id: lp.id
        for lp in (await db.execute(select(LmsProgram).where(LmsProgram.program_id.isnot(None)))).scalars().all()
        if lp.program_id is not None
    }

    req_items_by_owner: dict[tuple[str, uuid.UUID], int] = {}
    for owner_type, owner_id, cnt in (
        await db.execute(
            select(
                LmsProgramItem.owner_type,
                LmsProgramItem.owner_id,
                func.count(LmsProgramItem.id),
            )
            .where(LmsProgramItem.optional.is_(False))
            .group_by(LmsProgramItem.owner_type, LmsProgramItem.owner_id)
        )
    ).all():
        req_items_by_owner[(owner_type, owner_id)] = cnt

    assignment_ids = [a.id for a in assignments]
    progress_stats: dict[uuid.UUID, tuple[int, int]] = {}
    if assignment_ids:
        for aid, done_cnt, touched_cnt in (
            await db.execute(
                select(
                    LmsProgramItemProgress.assignment_id,
                    func.count(LmsProgramItemProgress.id).filter(LmsProgramItemProgress.status == "done"),
                    func.count(LmsProgramItemProgress.id).filter(LmsProgramItemProgress.updated_at.isnot(None)),
                )
                .where(LmsProgramItemProgress.assignment_id.in_(assignment_ids))
                .group_by(LmsProgramItemProgress.assignment_id)
            )
        ).all():
            progress_stats[aid] = (done_cnt or 0, touched_cnt or 0)

    out: list[ActiveProgramProgressOut] = []
    for cohort in running_cohorts:
        cohort_assignments = by_cohort.get(cohort.id, [])
        total_students = len(cohort_assignments)
        if cohort.id in overrides:
            required_total = req_items_by_owner.get(("cohort_override", overrides[cohort.id]), 0)
        elif cohort.program_id in base_lms_by_program:
            required_total = req_items_by_owner.get(("program", base_lms_by_program[cohort.program_id]), 0)
        else:
            required_total = 0

        if total_students == 0:
            out.append(
                ActiveProgramProgressOut(
                    cohort_id=str(cohort.id),
                    cohort_name=cohort.name,
                    students=0,
                    completed_pct=0,
                    active_pct=0,
                    not_started_pct=100,
                    engaged_pct=0,
                )
            )
            continue

        completed_n = 0
        active_n = 0
        for a in cohort_assignments:
            done_cnt, touched_cnt = progress_stats.get(a.id, (0, 0))
            if required_total > 0 and done_cnt >= required_total:
                completed_n += 1
            elif done_cnt > 0 or touched_cnt > 0:
                active_n += 1

        not_started_n = max(0, total_students - completed_n - active_n)
        completed_pct = round((completed_n / total_students) * 100)
        active_pct = round((active_n / total_students) * 100)
        not_started_pct = max(0, 100 - completed_pct - active_pct)
        if not_started_n == 0 and completed_pct + active_pct != 100:
            active_pct = max(0, 100 - completed_pct)
            not_started_pct = 0

        out.append(
            ActiveProgramProgressOut(
                cohort_id=str(cohort.id),
                cohort_name=cohort.name,
                students=total_students,
                completed_pct=completed_pct,
                active_pct=active_pct,
                not_started_pct=not_started_pct,
                engaged_pct=min(100, completed_pct + active_pct),
            )
        )
    return out


async def _fetch_milestones(
    db: AsyncSession,
    cutoff: datetime | None,
    kind: MilestoneKindFilter,
    page: int,
    page_size: int,
) -> PaginatedMilestonesOut:
    events: list[StudentMilestoneOut] = []

    if kind in ("all", "course"):
        stmt = (
            select(
                ItemProgress.id,
                ItemProgress.completed_at,
                User.full_name,
                ModuleItem.title.label("item_title"),
                ModuleItem.kind.label("item_kind"),
                Course.id.label("course_id"),
                Course.title.label("course_title"),
            )
            .join(User, User.id == ItemProgress.user_id)
            .join(ModuleItem, ModuleItem.id == ItemProgress.item_id)
            .join(CourseModule, CourseModule.id == ModuleItem.module_id)
            .join(Course, Course.id == CourseModule.course_id)
            .where(ItemProgress.completed_at.isnot(None))
            .order_by(ItemProgress.completed_at.desc())
            .limit(40)
        )
        if cutoff is not None:
            stmt = stmt.where(ItemProgress.completed_at >= cutoff)
        for row in (await db.execute(stmt)).all():
            item_label = row.item_title or row.item_kind.capitalize()
            events.append(
                StudentMilestoneOut(
                    id=f"course-{row.id}",
                    kind="course",
                    title=f"Completed {item_label}",
                    actor_name=row.full_name,
                    meta=row.course_title,
                    tone="green",
                    link="/lms-authoring/progress",
                    timestamp=row.completed_at,
                )
            )

    if kind in ("all", "mission"):
        stmt = (
            select(
                MissionAttempt.id,
                MissionAttempt.status,
                MissionAttempt.score,
                MissionAttempt.submitted_at,
                MissionAttempt.decided_at,
                Mission.title.label("mission_title"),
                User.full_name.label("user_name"),
                Team.name.label("team_name"),
                MissionAttempt.cohort_id,
            )
            .join(Mission, Mission.id == MissionAttempt.mission_id)
            .outerjoin(User, User.id == MissionAttempt.user_id)
            .outerjoin(Team, Team.id == MissionAttempt.team_id)
            .where(
                MissionAttempt.status.in_(["submitted", "passed", "failed"]),
                func.coalesce(MissionAttempt.decided_at, MissionAttempt.submitted_at).isnot(None),
            )
            .order_by(func.coalesce(MissionAttempt.decided_at, MissionAttempt.submitted_at).desc())
            .limit(40)
        )
        if cutoff is not None:
            stmt = stmt.where(
                func.coalesce(MissionAttempt.decided_at, MissionAttempt.submitted_at) >= cutoff
            )
        for row in (await db.execute(stmt)).all():
            ts = row.decided_at or row.submitted_at
            actor = row.team_name or row.user_name or "Student"
            verb = "Passed" if row.status == "passed" else "Failed" if row.status == "failed" else "Submitted"
            tone = "green" if row.status == "passed" else "rose" if row.status == "failed" else "purple"
            score_txt = f"Score {round(float(row.score))}%" if row.score is not None else row.status.capitalize()
            events.append(
                StudentMilestoneOut(
                    id=f"mission-{row.id}",
                    kind="mission",
                    title=f"{verb} {row.mission_title}",
                    actor_name=actor,
                    meta=score_txt,
                    tone=tone,
                    link=f"/operations/cohorts/{row.cohort_id}" if row.cohort_id else "/lms-authoring/missions",
                    timestamp=ts,
                )
            )

    if kind in ("all", "quiz"):
        stmt = (
            select(
                CohortQuizAttempt.id,
                CohortQuizAttempt.score,
                CohortQuizAttempt.total,
                CohortQuizAttempt.submitted_at,
                CohortQuizAttempt.cohort_id,
                User.full_name,
                CohortQuizTemplate.name.label("quiz_title"),
            )
            .join(User, User.id == CohortQuizAttempt.user_id)
            .join(CohortQuizTemplate, CohortQuizTemplate.id == CohortQuizAttempt.cohort_quiz_template_id)
            .where(
                CohortQuizAttempt.status == "submitted",
                CohortQuizAttempt.submitted_at.isnot(None),
            )
            .order_by(CohortQuizAttempt.submitted_at.desc())
            .limit(40)
        )
        if cutoff is not None:
            stmt = stmt.where(CohortQuizAttempt.submitted_at >= cutoff)
        for row in (await db.execute(stmt)).all():
            pct = round((row.score / row.total) * 100) if (row.score is not None and row.total) else None
            meta = f"{pct}% ({row.score}/{row.total})" if pct is not None else "Submitted"
            tone = "green" if (pct is not None and pct >= 70) else "rose" if (pct is not None and pct < 50) else "purple"
            events.append(
                StudentMilestoneOut(
                    id=f"quiz-{row.id}",
                    kind="quiz",
                    title=f"Submitted {row.quiz_title}",
                    actor_name=row.full_name,
                    meta=meta,
                    tone=tone,
                    link=f"/operations/cohorts/{row.cohort_id}" if row.cohort_id else "/lms-authoring/quiz-bank",
                    timestamp=row.submitted_at,
                )
            )

    if kind in ("all", "team"):
        lock_stmt = (
            select(
                Team.id,
                Team.name,
                Team.final_locked_at,
                Team.cohort_id,
                Cohort.name.label("cohort_name"),
            )
            .outerjoin(Cohort, Cohort.id == Team.cohort_id)
            .where(Team.is_observer.is_(False), Team.final_locked_at.isnot(None))
            .order_by(Team.final_locked_at.desc())
            .limit(30)
        )
        if cutoff is not None:
            lock_stmt = lock_stmt.where(Team.final_locked_at >= cutoff)
        for row in (await db.execute(lock_stmt)).all():
            events.append(
                StudentMilestoneOut(
                    id=f"team-lock-{row.id}",
                    kind="team",
                    title="Locked final team submission",
                    actor_name=row.name,
                    meta=row.cohort_name,
                    tone="green",
                    link=f"/operations/cohorts/{row.cohort_id}" if row.cohort_id else None,
                    timestamp=row.final_locked_at,
                )
            )

        tip_stmt = (
            select(
                LmsProgramTeamItemProgress.id,
                LmsProgramTeamItemProgress.completed_at,
                Team.name.label("team_name"),
                Team.cohort_id,
                LmsProgramItem.title.label("item_title"),
            )
            .join(Team, Team.id == LmsProgramTeamItemProgress.team_id)
            .join(LmsProgramItem, LmsProgramItem.id == LmsProgramTeamItemProgress.item_id)
            .where(
                Team.is_observer.is_(False),
                LmsProgramTeamItemProgress.completed_at.isnot(None),
            )
            .order_by(LmsProgramTeamItemProgress.completed_at.desc())
            .limit(30)
        )
        if cutoff is not None:
            tip_stmt = tip_stmt.where(LmsProgramTeamItemProgress.completed_at >= cutoff)
        for row in (await db.execute(tip_stmt)).all():
            events.append(
                StudentMilestoneOut(
                    id=f"team-item-{row.id}",
                    kind="team",
                    title=f"Completed {row.item_title}",
                    actor_name=row.team_name,
                    meta="Team checklist",
                    tone="purple",
                    link=f"/operations/cohorts/{row.cohort_id}" if row.cohort_id else None,
                    timestamp=row.completed_at,
                )
            )

    def _aware_ts(ev: StudentMilestoneOut) -> datetime:
        return ev.timestamp if ev.timestamp.tzinfo is not None else ev.timestamp.replace(tzinfo=timezone.utc)

    events.sort(key=_aware_ts, reverse=True)
    total = len(events)
    total_pages = max(1, math.ceil(total / page_size))
    safe_page = min(page, total_pages)
    start = (safe_page - 1) * page_size
    return PaginatedMilestonesOut(
        items=events[start:start + page_size],
        total=total,
        page=safe_page,
        page_size=page_size,
        total_pages=total_pages,
    )


async def _fetch_warehouse_inventory(
    db: AsyncSession,
    cutoff: datetime | None,
) -> tuple[list[WarehouseInventoryDeltaOut], list[WarehouseMovementRowOut]]:
    warehouses = (
        await db.execute(
            select(Warehouse)
            .where(Warehouse.is_active.is_(True))
            .order_by(Warehouse.name)
        )
    ).scalars().all()
    wh_names: dict[uuid.UUID, str] = {w.id: w.name for w in warehouses}
    added_by_wh: dict[uuid.UUID, int] = {w.id: 0 for w in warehouses}
    removed_by_wh: dict[uuid.UUID, int] = {w.id: 0 for w in warehouses}

    mv_stmt = select(Movement).order_by(Movement.created_at.desc())
    if cutoff is not None:
        mv_stmt = mv_stmt.where(Movement.created_at >= cutoff)
    movements = (await db.execute(mv_stmt)).scalars().all()

    for m in movements:
        amount = abs(m.qty) if m.qty is not None else 1
        if m.to_warehouse_id is not None:
            added_by_wh[m.to_warehouse_id] = added_by_wh.get(m.to_warehouse_id, 0) + amount
        if m.from_warehouse_id is not None:
            removed_by_wh[m.from_warehouse_id] = removed_by_wh.get(m.from_warehouse_id, 0) + amount

    wh_summaries = [
        WarehouseInventoryDeltaOut(
            warehouse_id=str(w.id),
            warehouse_name=w.name,
            added=added_by_wh.get(w.id, 0),
            removed=removed_by_wh.get(w.id, 0),
        )
        for w in warehouses
    ]
    wh_summaries.sort(key=lambda r: (r.added + r.removed, r.warehouse_name), reverse=True)

    recent_raw = [
        m for m in movements
        if m.to_warehouse_id is not None or m.from_warehouse_id is not None
    ][:8]

    item_ids = {m.item_id for m in recent_raw if m.item_id is not None}
    kit_ids = {m.kit_id for m in recent_raw if m.kit_id is not None}
    actor_ids = {m.created_by for m in recent_raw if m.created_by is not None}
    extra_wh_ids = (
        {m.to_warehouse_id for m in recent_raw if m.to_warehouse_id is not None}
        | {m.from_warehouse_id for m in recent_raw if m.from_warehouse_id is not None}
    ) - set(wh_names.keys())

    items_map: dict[uuid.UUID, str] = {}
    if item_ids:
        for iid, name in (await db.execute(select(Item.id, Item.name).where(Item.id.in_(item_ids)))).all():
            items_map[iid] = name

    kits_map: dict[uuid.UUID, str] = {}
    if kit_ids:
        for kid, label in (await db.execute(select(Kit.id, Kit.label).where(Kit.id.in_(kit_ids)))).all():
            kits_map[kid] = label

    actors_map: dict[uuid.UUID, str] = {}
    if actor_ids:
        for uid, full_name in (await db.execute(select(User.id, User.full_name).where(User.id.in_(actor_ids)))).all():
            actors_map[uid] = full_name

    if extra_wh_ids:
        for wid, name in (await db.execute(select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(extra_wh_ids)))).all():
            wh_names[wid] = name

    recent_rows: list[WarehouseMovementRowOut] = []
    for m in recent_raw:
        amount = abs(m.qty) if m.qty is not None else 1
        unit_suffix = "" if m.qty is not None else " kit"
        item_label = (
            items_map.get(m.item_id, "Item")
            if m.item_id is not None
            else kits_map.get(m.kit_id, "Kit")
        )
        from_name = wh_names.get(m.from_warehouse_id) if m.from_warehouse_id else None
        to_name = wh_names.get(m.to_warehouse_id) if m.to_warehouse_id else None

        if from_name and to_name:
            qty_display = f"{amount}{unit_suffix}"
            tone = "purple"
            wh_label = f"{from_name} -> {to_name}"
        elif to_name:
            qty_display = f"+{amount}{unit_suffix}"
            tone = "green"
            wh_label = to_name
        else:
            qty_display = f"-{amount}{unit_suffix}"
            tone = "rose"
            wh_label = from_name or "Warehouse"

        recent_rows.append(
            WarehouseMovementRowOut(
                id=str(m.id),
                item_label=item_label,
                qty_display=qty_display,
                tone=tone,
                warehouse_label=wh_label,
                reason=m.reason.replace("_", " ").capitalize(),
                actor_name=actors_map.get(m.created_by),
                created_at=m.created_at,
            )
        )

    return wh_summaries, recent_rows


async def get_ops_dashboard_overview(
    db: AsyncSession,
    range_key: DashboardRange = "7d",
    kind: MilestoneKindFilter = "all",
    page: int = 1,
    page_size: int = 8,
) -> OpsDashboardOverviewOut:
    now = datetime.now(timezone.utc)
    today = now.date()
    cutoff = _resolve_cutoff(now, range_key)

    active_cohorts = await db.scalar(
        select(func.count(Cohort.id)).where(
            Cohort.status == "running",
            Cohort.is_template_legacy.is_(False),
            Cohort.management_mode == "spacepoint",
        )
    ) or 0
    upcoming_sessions_7d = await db.scalar(
        select(func.count(Session.id))
        .join(Cohort, Cohort.id == Session.cohort_id)
        .where(
            Session.meeting_date.between(today, today + timedelta(days=7)),
            Cohort.is_template_legacy.is_(False),
            Cohort.management_mode == "spacepoint",
        )
    ) or 0

    activity_events = await _collect_activity_events(db, cutoff)
    active_users = {uid for uid, _ in activity_events}
    active_learners = len(active_users)
    learner_trend = _bucket_learner_trend(activity_events, now, range_key, cutoff)
    learner_delta_label = await _delta_label(db, active_learners, now, range_key)

    enrolled_course_users = set(
        (await db.execute(select(Enrollment.user_id).where(Enrollment.status == "active"))).scalars().all()
    )
    assigned_cohort_users = set(
        (
            await db.execute(
                select(LmsProgramAssignment.user_id).where(LmsProgramAssignment.mode == "participant")
            )
        ).scalars().all()
    )
    enrolled_users = enrolled_course_users | assigned_cohort_users | active_users

    # Completed >= 1 course (weighted >= 100%) or passed >= 1 mission
    course_rows = await courses_overview(db)
    mission_rows = await missions_overview(db)

    total_course_enrolled = sum(r["enrolled_count"] for r in course_rows)
    total_course_completed = sum(r["completed_count"] for r in course_rows)
    avg_course_pct = (
        round((total_course_completed / total_course_enrolled) * 100, 1)
        if total_course_enrolled > 0
        else 0.0
    )

    total_mission_attempted = sum(r["attempted_count"] for r in mission_rows)
    total_mission_passed = sum(r["passed_count"] for r in mission_rows)
    avg_mission_pct = (
        round((total_mission_passed / total_mission_attempted) * 100, 1)
        if total_mission_attempted > 0
        else 0.0
    )

    # Distinct learners who completed a course or passed a mission
    completed_users: set[uuid.UUID] = set()
    passed_mission_stmt = select(MissionAttempt.user_id).where(
        MissionAttempt.status == "passed",
        MissionAttempt.user_id.isnot(None),
    )
    if cutoff is not None:
        passed_mission_stmt = passed_mission_stmt.where(
            func.coalesce(MissionAttempt.decided_at, MissionAttempt.submitted_at, MissionAttempt.started_at) >= cutoff
        )
    for uid in (await db.execute(passed_mission_stmt)).scalars().all():
        if uid is not None:
            completed_users.add(uid)

    team_passed_stmt = (
        select(MissionAttemptMember.user_id)
        .join(MissionAttempt, MissionAttempt.id == MissionAttemptMember.attempt_id)
        .where(MissionAttempt.status == "passed")
    )
    if cutoff is not None:
        team_passed_stmt = team_passed_stmt.where(
            func.coalesce(MissionAttempt.decided_at, MissionAttempt.submitted_at, MissionAttempt.started_at) >= cutoff
        )
    for (uid,) in (await db.execute(team_passed_stmt)).all():
        if uid is not None:
            completed_users.add(uid)

    # Students who completed a course (batch_course_completion check already gave total_course_completed,
    # and we include students whose required course items are all completed)
    req_count_rows = (
        await db.execute(
            select(CourseModule.course_id, func.count(ModuleItem.id))
            .join(ModuleItem, ModuleItem.module_id == CourseModule.id)
            .where(ModuleItem.is_required.is_(True))
            .group_by(CourseModule.course_id)
        )
    ).all()
    req_by_course = {cid: cnt for cid, cnt in req_count_rows if cnt > 0}
    if req_by_course:
        done_stmt = (
            select(
                ItemProgress.user_id,
                CourseModule.course_id,
                func.count(ItemProgress.id),
                func.max(ItemProgress.completed_at),
            )
            .join(ModuleItem, ModuleItem.id == ItemProgress.item_id)
            .join(CourseModule, CourseModule.id == ModuleItem.module_id)
            .where(
                ModuleItem.is_required.is_(True),
                ItemProgress.status.in_(["completed", "skipped"]),
            )
            .group_by(ItemProgress.user_id, CourseModule.course_id)
        )
        for uid, cid, done_cnt, max_completed_at in (await db.execute(done_stmt)).all():
            need = req_by_course.get(cid)
            if need and done_cnt >= need:
                if cutoff is None or (
                    max_completed_at is not None
                    and (
                        max_completed_at
                        if max_completed_at.tzinfo is not None
                        else max_completed_at.replace(tzinfo=timezone.utc)
                    ) >= cutoff
                ):
                    completed_users.add(uid)

    funnel = DashboardFunnelOut(
        enrolled=len(enrolled_users),
        active=active_learners,
        completed=len(completed_users),
    )

    active_teams = await _fetch_team_summary(db, cutoff, range_key)
    top_invite_codes = await _fetch_top_invite_codes(db, active_users, cutoff)
    active_programs = await _fetch_active_programs(db)
    milestones = await _fetch_milestones(db, cutoff, kind, page, page_size)
    warehouses, recent_movements = await _fetch_warehouse_inventory(db, cutoff)

    return OpsDashboardOverviewOut(
        range=range_key,
        active_cohorts=active_cohorts,
        upcoming_sessions_7d=upcoming_sessions_7d,
        active_learners=active_learners,
        learner_trend=learner_trend,
        learner_delta_label=learner_delta_label,
        funnel=funnel,
        active_teams=active_teams,
        avg_course_completion_pct=avg_course_pct,
        avg_mission_completion_pct=avg_mission_pct,
        top_invite_codes=top_invite_codes,
        active_programs=active_programs,
        milestones=milestones,
        warehouses=warehouses,
        recent_movements=recent_movements,
    )
