"""Judge identity and cohort access (2026-08-24) — the `judge` role's
equivalent of `services/missions/cohort_access.py`'s `instructor_cohort_ids`/
`require_cohort_access`, and of `services/lms/ops_integration.py`'s
find-or-create-account + set-password-email flow, reused as-is rather than
duplicated.

Deliberately no staff-bypass in `judge_cohort_ids` (unlike the instructor
version): staff reach the same data through the separate `/admin/*`
endpoints (`services/competitions/judging.py`), never through the judge
surface, so there's no case where "unrestricted" needs to mean anything
here — a plain judge with no `CompetitionJudge` row for a cohort simply
sees nothing for it.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.competitions.judging import CompetitionJudge
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.services.lms.ops_integration import send_registered_notice_email, send_set_password_email


async def judge_cohort_ids(db: AsyncSession, *, user: User) -> set[uuid.UUID]:
    """Every cohort this judge is assigned to via `CompetitionJudge` — may
    be empty. Admin is not special-cased here (unlike `instructor_cohort_ids`)
    since nothing routes an admin through the judge surface; an admin
    inspecting judging goes through the ops endpoints instead."""
    rows = (await db.execute(
        select(CompetitionJudge.cohort_id).where(CompetitionJudge.user_id == user.id)
    )).scalars().all()
    return set(rows)


async def require_judge_cohort_access(db: AsyncSession, *, cohort_id: uuid.UUID, user: User) -> None:
    """404s, not 403s, on a cohort this judge isn't assigned to — same
    "don't leak existence" convention `cohort_access.py::require_cohort_access`
    uses for instructors."""
    allowed = await judge_cohort_ids(db, user=user)
    if cohort_id not in allowed:
        raise HTTPException(404, detail="Cohort not found")


async def assigned_cohorts(db: AsyncSession, *, user: User) -> list[tuple[Cohort, str]]:
    """This judge's own cohort picker (`/judge` landing page) — every
    cohort they hold a `CompetitionJudge` row for, paired with its
    program's name since a bare cohort name ("Qualifier") is ambiguous
    across competitions."""
    allowed = await judge_cohort_ids(db, user=user)
    if not allowed:
        return []
    rows = (await db.execute(
        select(Cohort, Program.name)
        .join(Program, Program.id == Cohort.program_id)
        .where(Cohort.id.in_(allowed))
        .order_by(Cohort.name)
    )).all()
    return [(cohort, program_name) for cohort, program_name in rows]


async def list_judges(db: AsyncSession, *, cohort_id: uuid.UUID) -> list[User]:
    rows = (await db.execute(
        select(User).join(CompetitionJudge, CompetitionJudge.user_id == User.id)
        .where(CompetitionJudge.cohort_id == cohort_id)
        .order_by(User.full_name)
    )).scalars().all()
    return list(rows)


async def _judge_context(db: AsyncSession, *, cohort_id: uuid.UUID) -> str:
    cohort = await db.get(Cohort, cohort_id)
    program = await db.get(Program, cohort.program_id) if cohort else None
    return f"{program.name} ({cohort.name})" if program and cohort else (cohort.name if cohort else "SpacePoint")


async def send_judge_onboarding_email(
    db: AsyncSession, *, user: User, assignment: CompetitionJudge, cohort_id: uuid.UUID,
) -> bool:
    """Picks and sends the right onboarding email for one judge assignment —
    set-password if they still haven't set one (`must_change_password`, not
    "was the account just created": an existing staff account added as a
    judge before ever logging in still needs the password step, not the
    bare login notice), the plain "you're registered" notice otherwise.
    Stamps `assignment.onboarding_sent_at` on success — used both by
    `invite_judge`'s automatic send and by the ops "resend onboarding
    email" action, so both paths share one stamping rule."""
    context = await _judge_context(db, cohort_id=cohort_id)
    if user.must_change_password:
        sent = await send_set_password_email(user, purpose="welcome", audience="judge", context=context)
    else:
        sent = await send_registered_notice_email(user, audience="judge", context=context)
    if sent:
        assignment.onboarding_sent_at = datetime.now(timezone.utc)
        await db.flush()
    return sent


async def invite_judge(
    db: AsyncSession, *, cohort_id: uuid.UUID, name: str, email: str, send_email: bool = True,
) -> User:
    """Find-or-create a judge account for this email, add the `judge` role
    if it's missing one (an existing staff/instructor account can also
    judge — the role only adds capability, same "layered on top of, not
    instead of" posture `mission_managers` uses), assign them to this
    cohort, and email them via `send_judge_onboarding_email`.
    Idempotent: re-inviting an already-assigned judge just returns them.

    `send_email=False` (2026-09-10) still creates the account and the
    assignment — same "the action always happens, only the notification is
    optional" posture every other send_welcome_email/send_ticket_email
    toggle in this codebase already has."""
    # Login compares `User.email == input.strip().lower()` exactly — storing
    # anything else (capitals, trailing space) mints an account that can
    # never log in (prod incident 2026-09-30). Normalize on the way in, for
    # both the lookup and the insert, so duplicates can't slip past either.
    email = email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    is_new = user is None
    if user is None:
        user = User(
            id=uuid.uuid4(), full_name=name, email=email,
            password_hash=get_password_hash(secrets.token_urlsafe(24)),
            roles=["judge"], status="active", must_change_password=True,
        )
        db.add(user)
        await db.flush()
    elif "judge" not in user.role_values:
        user.roles = [*user.roles, "judge"]

    assignment = await db.scalar(
        select(CompetitionJudge).where(
            CompetitionJudge.cohort_id == cohort_id, CompetitionJudge.user_id == user.id,
        )
    )
    is_new_assignment = assignment is None
    if is_new_assignment:
        assignment = CompetitionJudge(id=uuid.uuid4(), cohort_id=cohort_id, user_id=user.id)
        db.add(assignment)
        await db.flush()

    # Only a genuinely new account or a genuinely new assignment gets an
    # email — a repeat invite of a judge already assigned to this cohort is
    # the true idempotent no-op the docstring promises, not a re-send.
    if send_email and (is_new or is_new_assignment):
        await send_judge_onboarding_email(db, user=user, assignment=assignment, cohort_id=cohort_id)
    return user


async def resend_judge_onboarding_email(db: AsyncSession, *, cohort_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """The manual "resend onboarding email" action — unlike `invite_judge`,
    always sends regardless of whether this assignment already got one,
    since re-sending on request is the entire point."""
    assignment = await db.scalar(
        select(CompetitionJudge).where(
            CompetitionJudge.cohort_id == cohort_id, CompetitionJudge.user_id == user_id,
        )
    )
    if assignment is None:
        raise HTTPException(404, detail="This judge isn't assigned to this cohort")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(404, detail="Judge not found")
    return await send_judge_onboarding_email(db, user=user, assignment=assignment, cohort_id=cohort_id)


async def revoke_judge(db: AsyncSession, *, cohort_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    assignment = await db.scalar(
        select(CompetitionJudge).where(
            CompetitionJudge.cohort_id == cohort_id, CompetitionJudge.user_id == user_id,
        )
    )
    if assignment is None:
        return False
    await db.delete(assignment)
    await db.flush()
    return True
