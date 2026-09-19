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

from app.models.lms.program import LmsProgramAssignment
from app.models.sessions.cohort import Cohort
from app.models.team import Team
from app.models.user import User
from app.services.documents.card_id import format_card_id
from app.services.teams import teams_for_user


# How long a minted token stays valid. The Messenger only needs it at boot,
# and the widget refetches on every mount, so this is short on purpose — a
# token lifted from a shared machine's devtools stops working the same hour.
JWT_TTL = timedelta(hours=1)


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


async def _latest_cohort_name(db: AsyncSession, *, user_id: uuid.UUID) -> str | None:
    """The name of the cohort this student was most recently assigned to.

    Deliberately its own query rather than reusing the two existing paths —
    both do far too much work for something that runs on every `/learn/*`
    mount. `list_student_assignments` (services/lms/program.py) refreshes
    per-item checklist progress; `my_programs` (services/lms/my_programs.py)
    resolves a location and computes course completion per row, and is keyed
    off `user.contact_id`, so it returns nothing at all for a student with no
    linked Contact.

    A student can hold assignments across several cohorts concurrently — an
    explicit operator decision recorded in `LmsProgramAssignment`'s own
    docstring — so "most recent" is a choice, not a lookup of something
    unique. The inner join also drops assignments whose `cohort_id` went NULL
    when a cohort was deleted (`ondelete="SET NULL"`), which is right: there
    is no name left to show.
    """
    return await db.scalar(
        select(Cohort.name)
        .join(LmsProgramAssignment, LmsProgramAssignment.cohort_id == Cohort.id)
        .where(LmsProgramAssignment.user_id == user_id)
        .order_by(LmsProgramAssignment.assigned_at.desc().nullslast())
        .limit(1)
    )


async def chat_identity(db: AsyncSession, *, user: User, secret: str) -> dict:
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
    team = _pick_team(teams)

    fields = {
        "user_id": str(user.id),
        "name": user.full_name,
        "email": user.email,
        # Comma-joined rather than a single role: `users.roles` is an array
        # and a person can hold `student` and `instructor` at once, so one
        # value would mean picking arbitrarily and having an Intercom rule
        # silently miss the people who hold two. The rule reads
        # `roles contains student`. Unsorted on purpose — `role_values`
        # keeps the DB array order, and `roles[0]` carries a weak "primary
        # role" meaning the frontend already leans on
        # (AuthContext::resolveActiveRole).
        "roles": ",".join(user.role_values),
        "team": team.name if team is not None else None,
        "cohort": await _latest_cohort_name(db, user_id=user.id),
        "card_id": (
            format_card_id(user.card_number, user.role_values)
            if user.card_number is not None
            else None
        ),
    }

    # Anything that isn't one of Intercom's own standard attributes has to be
    # nested under `custom_attributes`, the same shape their REST API uses.
    # Sent as bare top-level claims they are simply dropped: the contact ends
    # up with name and email applied and no roles/team/cohort/card at all,
    # with nothing anywhere reporting a problem. Found the hard way, on a
    # contact whose attribute list was entirely Intercom's own defaults.
    claims = {
        "user_id": fields["user_id"],
        "name": fields["name"],
        "email": fields["email"],
        "custom_attributes": {
            k: v for k, v in fields.items() if k not in ("user_id", "name", "email")
        },
    }

    # The response stays flat — it is our own debugging surface, readable
    # without decoding a token, and the frontend forwards only the token
    # anyway. The nesting above is Intercom's wire format, not ours.
    return {"intercom_user_jwt": identity_jwt(secret=secret, claims=claims), **fields}
