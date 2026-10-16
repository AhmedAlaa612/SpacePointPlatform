"""Chat identity for the Fin (Intercom) support messenger on `/learn/*`.

Composes the one payload the Messenger boots with: who the student is, plus
an HMAC signature Intercom verifies so a student can't open a chat as
someone else. Nothing here writes, and nothing here is reachable for any
user but the caller — see the router's docstring for why that matters.

Why a service and not inline router code: two of the five attributes are
genuinely multi-valued and need a documented pick rule (below), which is
this codebase's line for "anything with rules gets a service module"
(docs/HANDOFF.md §8 #4).

The frontend could assemble name/email/card itself — they're already on
`/auth/me` and sitting in `AuthContext`. It doesn't, deliberately: identity
verification signs the *user id*, not the attributes beside it, so anything
the browser supplies can be edited in devtools before boot. A support agent
reads the email and card id to find the student in the admin Users screen,
so those need to come from the server. It also keeps the boot to one call
instead of three.
"""

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.program import LmsProgram, LmsProgramAssignment
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program as SessionsProgram
from app.models.team import Team
from app.models.user import User
from app.services.documents.card_id import format_card_id
from app.services.teams import teams_for_user


# How long a minted token stays valid. Kept to a single study day so a student
# leaving a tab open (or waking a sleeping laptop) doesn't hit a mid-session
# 401 from Intercom Messenger Security before the frontend refreshes it.
JWT_TTL = timedelta(hours=12)


def identity_jwt(*, secret: str, claims: dict) -> str:
    """Intercom Messenger Security token — HS256 over the workspace secret.

    This replaced the older `user_hash` HMAC digest, which Intercom
    deprecated along with the whole Identity Verification feature. Old
    `user_hash` values are still accepted, but the two are mutually
    exclusive: a boot payload may carry one or the other, never both.

    Every attribute rides *inside* the token rather than beside it, which is
    the real upgrade. `user_hash` only ever signed the user id, so the name,
    email and custom attributes next to it in the boot payload were
    unauthenticated and editable in devtools. As signed claims they are not.
    """
    return jwt.encode(
        {**claims, "exp": datetime.now(timezone.utc) + JWT_TTL},
        secret,
        algorithm="HS256",
    )


def _pick_team(teams: list[Team]) -> Team | None:
    """Prefer the most recent *cohort-scoped* team, else the most recent of
    any kind.

    A student can hold several teams at once: `learner_teams.cohort_id` is
    nullable (NULL = self-formed from the public mission catalog) and
    `TeamMember`'s PK is `(team_id, user_id)` with nothing limiting a user to
    one row. Someone on a competition team *and* a self-formed mission team
    is ordinary, not a data error.

    A support agent handling a competition question wants the cohort-scoped
    one; self-formed teams are noise. `teams_for_user` already returns
    `created_at desc`, so this is a filter over that order, not a re-sort.
    """
    return next((t for t in teams if t.cohort_id is not None), None) or (teams[0] if teams else None)


async def _resolve_context(
    db: AsyncSession, *, user_id: uuid.UUID, assignment_id: uuid.UUID | None
) -> tuple[str | None, str | None, uuid.UUID | None]:
    """The (program, cohort, cohort_id) triple Fin audiences filter on.

    `program` is the real Sessions program name (e.g. "Ru'ya"), loaded via
    the cohort exactly like the student-facing checklist title does
    (`services/lms/program.py::_assignment_summary`) — never the LMS program
    name, which is an ops-internal checklist label like "week 1 checklist".
    `cohort` is likewise the Sessions cohort name. Both fall back to None
    (never a 500) when the student holds no assignment.

    When `assignment_id` names one of the caller's own `LmsProgramAssignment`
    rows (e.g. the checklist board currently open on `/learn/*`), the names
    come from that assignment — so Fin answers from the cohort being viewed,
    not just the latest one. An unknown id, or one belonging to someone else,
    is ignored and falls back to the latest assignment: the widget must
    degrade rather than 500, and must never leak another student's context.

    Without a usable `assignment_id` this is the most recently assigned
    checklist, deliberately the same lightweight query as before rather than
    `list_student_assignments` (which refreshes per-item progress) or
    `my_programs` (keyed off `contact_id`, empty for contact-less students).

    A student can hold assignments across several cohorts concurrently, so
    "most recent" is a choice, not a lookup of something unique. Assignments
    whose `cohort_id` went NULL when a cohort was deleted still contribute
    their LMS program name — only the Sessions halves are missing.
    """
    if assignment_id is not None:
        assignment = await db.scalar(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.id == assignment_id,
                LmsProgramAssignment.user_id == user_id,
            )
        )
        if assignment is not None:
            return await _names_for_assignment(db, assignment)

    row = await db.execute(
        select(
            SessionsProgram.name,
            LmsProgram.name,
            Cohort.name,
            LmsProgramAssignment.cohort_id,
        )
        .join(LmsProgram, LmsProgram.id == LmsProgramAssignment.lms_program_id)
        .outerjoin(Cohort, Cohort.id == LmsProgramAssignment.cohort_id)
        .outerjoin(SessionsProgram, SessionsProgram.id == Cohort.program_id)
        .where(LmsProgramAssignment.user_id == user_id)
        .order_by(LmsProgramAssignment.assigned_at.desc().nullslast())
        .limit(1)
    )
    first = row.first()
    if first is None:
        return None, None, None
    sessions_name, lms_name, cohort_name, cohort_id = first
    return sessions_name or lms_name, cohort_name, cohort_id


async def _names_for_assignment(
    db: AsyncSession, assignment: LmsProgramAssignment
) -> tuple[str | None, str | None, uuid.UUID | None]:
    """Program/cohort names for one known-good assignment row."""
    cohort = await db.get(Cohort, assignment.cohort_id) if assignment.cohort_id else None
    sessions_program = (
        await db.get(SessionsProgram, cohort.program_id)
        if cohort and cohort.program_id else None
    )
    if sessions_program is not None:
        return sessions_program.name, cohort.name if cohort else None, assignment.cohort_id
    lms_name = await db.scalar(
        select(LmsProgram.name).where(LmsProgram.id == assignment.lms_program_id)
    )
    return lms_name, cohort.name if cohort else None, assignment.cohort_id


async def chat_identity(
    db: AsyncSession, *, user: User, secret: str, assignment_id: uuid.UUID | None = None
) -> dict:
    """Everything the Messenger needs for one student.

    Every attribute but the id and the hash is nullable on purpose: a student
    with no team, no cohort or no allocated card number is an ordinary
    account (card numbers were backfilled, and roster assignment can lag
    signup), and a support widget must never 500 on one.

    `role_values` rather than `roles`: the column hydrates as either enum
    members or plain strings depending on the driver, and `format_card_id`
    tests `"student" in roles` — so the normalised accessor is the one that
    can't silently mislabel a student's card as staff.
    """
    teams = await teams_for_user(db, user_id=user.id)
    program_name, cohort_name, context_cohort_id = await _resolve_context(
        db, user_id=user.id, assignment_id=assignment_id
    )
    if context_cohort_id is not None:
        team = next(
            (t for t in teams if t.cohort_id == context_cohort_id), None
        ) or _pick_team(teams)
    else:
        team = _pick_team(teams)

    fields = {
        "user_id": str(user.id),
        "name": user.full_name,
        "email": user.email,
        # Every message originating from the LMS (`/learn/*`) passes `"student"`
        # as the sole role — regardless of whether the account is an observer,
        # instructor, or multi-role staff member — so Fin on the LMS always
        # treats the caller strictly as a student.
        "roles": "student",
        "team": team.name if team is not None else None,
        "program": program_name,
        "cohort": cohort_name,
        "card_id": (
            format_card_id(user.card_number, user.role_values)
            if user.card_number is not None
            else None
        ),
    }

    custom_attrs = {
        k: v for k, v in fields.items() if k not in ("user_id", "name", "email")
    }

    # Intercom Messenger Security (JWT) reads custom attributes directly as
    # top-level claims in the token. We provide both the normalized snake_case
    # keys and title-cased variants (e.g. "Roles", "Cohort", "Card id") to
    # match however the attribute API name was configured in Intercom, as well as
    # the nested `custom_attributes` object for REST API parity.
    cased_variants = {}
    for k, v in custom_attrs.items():
        if v is not None:
            cased_variants[k.capitalize()] = v
            cased_variants[k.replace("_", " ").capitalize()] = v
            cased_variants[k.replace("_", " ").title()] = v

    claims = {
        "user_id": fields["user_id"],
        "name": fields["name"],
        "email": fields["email"],
        **custom_attrs,
        **cased_variants,
        "custom_attributes": {
            **custom_attrs,
            **cased_variants,
        },
    }

    # The response stays flat — it is our own debugging surface, readable
    # without decoding a token, and the frontend forwards only the token
    # anyway.
    return {"intercom_user_jwt": identity_jwt(secret=secret, claims=claims), **fields}
