"""`GET /lms/support/chat-identity` — the Fin messenger's boot payload.

Covers the auth guard, the HMAC itself, the 503 on a missing secret, and the
two pick rules that exist because a student can genuinely hold several teams
and several cohorts at once (see services/lms/support.py). Redis-free — uses
the shared `client` fixture.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from fastapi import status as http_status

from app.core.config import settings
from app.core.security import create_access_token
from app.models.lms.program import LmsProgram, LmsProgramAssignment
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.team import Team, TeamMember
from app.models.user import User

URL = "/lms/support/chat-identity"
SECRET = "test-intercom-secret"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    """Every test but the 503 one wants identity configured."""
    monkeypatch.setattr(settings, "INTERCOM_IDENTITY_SECRET", SECRET)


async def _user(db, *, roles=None, card_number=None, **kw) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name=kw.pop("full_name", "Student One"),
        email=f"support-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=list(roles) if roles else ["student"],
        status="active",
        card_number=card_number,
        **kw,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _cohort(db, *, name: str) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="Ru'ya Space Race",
        program_type="competition", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name=name)
    db.add(cohort)
    await db.flush()
    return cohort


async def _assign(db, *, user: User, cohort: Cohort, assigned_at: datetime) -> None:
    lms_program = LmsProgram(id=uuid.uuid4(), name=f"Checklist {uuid.uuid4().hex[:6]}")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramAssignment(
        id=uuid.uuid4(), user_id=user.id, lms_program_id=lms_program.id,
        cohort_id=cohort.id, assigned_at=assigned_at,
    ))
    await db.flush()


async def _team(db, *, user: User, name: str, cohort: Cohort | None, created_at: datetime) -> Team:
    team = Team(
        id=uuid.uuid4(), name=name,
        cohort_id=cohort.id if cohort is not None else None,
        created_at=created_at,
    )
    db.add(team)
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id))
    await db.flush()
    return team


async def test_requires_authentication(db, client):
    res = await client.get(URL)
    assert res.status_code in (http_status.HTTP_401_UNAUTHORIZED, http_status.HTTP_403_FORBIDDEN)


async def test_returns_the_callers_identity_as_signed_claims(db, client):
    """The token is what Intercom actually reads, so verify it the way
    Intercom will — decode it against the workspace secret — rather than
    trusting the plaintext fields echoed beside it."""
    user = await _user(db, full_name="Aisha Khan", card_number=12)

    res = await client.get(URL, headers=_headers(user))
    assert res.status_code == http_status.HTTP_200_OK
    body = res.json()

    claims = jwt.decode(body["intercom_user_jwt"], SECRET, algorithms=["HS256"])
    assert claims["user_id"] == str(user.id)
    assert claims["name"] == "Aisha Khan"
    assert claims["email"] == user.email
    assert claims["card_id"] == "SP-ST-0012-UAE"
    assert claims["exp"] > datetime.now(timezone.utc).timestamp()

    # The echoed copies must agree with the signed ones, or the Inbox shows
    # something the token doesn't actually vouch for.
    assert body["user_id"] == claims["user_id"]
    assert body["email"] == claims["email"]


async def test_token_is_signed_hs256_and_rejects_a_wrong_secret(db, client):
    """A token Intercom can't verify is worse than no token: the boot fails
    and the widget silently drops to anonymous."""
    user = await _user(db)
    body = (await client.get(URL, headers=_headers(user))).json()

    assert jwt.get_unverified_header(body["intercom_user_jwt"])["alg"] == "HS256"
    with pytest.raises(Exception):
        jwt.decode(body["intercom_user_jwt"], "not-the-secret", algorithms=["HS256"])


async def test_never_sends_the_deprecated_user_hash(db, client):
    """Intercom accepts `user_hash` or `intercom_user_jwt`, never both — a
    payload carrying each is rejected outright."""
    user = await _user(db)
    body = (await client.get(URL, headers=_headers(user))).json()
    assert "user_hash" not in body


async def test_token_differs_per_user(db, client):
    one, two = await _user(db), await _user(db)
    a = (await client.get(URL, headers=_headers(one))).json()["intercom_user_jwt"]
    b = (await client.get(URL, headers=_headers(two))).json()["intercom_user_jwt"]
    assert a != b


async def test_503_when_the_secret_is_unset(db, client, monkeypatch):
    """A blank secret still signs a syntactically valid token — one keyed on
    the empty string. Serving that would look fine and verify nowhere, so the
    route must refuse instead."""
    monkeypatch.setattr(settings, "INTERCOM_IDENTITY_SECRET", "")
    user = await _user(db)
    res = await client.get(URL, headers=_headers(user))
    assert res.status_code == http_status.HTTP_503_SERVICE_UNAVAILABLE


async def test_student_with_no_team_cohort_or_card_gets_nulls_not_a_500(db, client):
    user = await _user(db, card_number=None)
    res = await client.get(URL, headers=_headers(user))
    assert res.status_code == http_status.HTTP_200_OK
    body = res.json()
    assert body["team"] is None
    assert body["cohort"] is None
    assert body["card_id"] is None


async def test_prefers_the_cohort_scoped_team_over_a_self_formed_one(db, client):
    """A student on a competition team *and* a self-formed mission team is
    ordinary. The support agent wants the competition one — even though the
    self-formed team is newer, so plain recency would pick the wrong row."""
    user = await _user(db)
    cohort = await _cohort(db, name="Ru'ya 2026")
    now = datetime.now(timezone.utc)
    await _team(db, user=user, name="Orbiteers", cohort=cohort, created_at=now - timedelta(days=5))
    await _team(db, user=user, name="Weekend Tinkerers", cohort=None, created_at=now)

    body = (await client.get(URL, headers=_headers(user))).json()
    assert body["team"] == "Orbiteers"


async def test_falls_back_to_a_self_formed_team_when_there_is_no_cohort_one(db, client):
    user = await _user(db)
    now = datetime.now(timezone.utc)
    await _team(db, user=user, name="Older Solo", cohort=None, created_at=now - timedelta(days=5))
    await _team(db, user=user, name="Newer Solo", cohort=None, created_at=now)

    body = (await client.get(URL, headers=_headers(user))).json()
    assert body["team"] == "Newer Solo"


async def test_picks_the_most_recently_assigned_cohort(db, client):
    """Assignments across several cohorts concurrently are explicitly allowed
    (LmsProgramAssignment's docstring), so this is a choice, not a lookup."""
    user = await _user(db)
    now = datetime.now(timezone.utc)
    old = await _cohort(db, name="Ru'ya 2025")
    new = await _cohort(db, name="Ru'ya 2026")
    await _assign(db, user=user, cohort=old, assigned_at=now - timedelta(days=200))
    await _assign(db, user=user, cohort=new, assigned_at=now)

    body = (await client.get(URL, headers=_headers(user))).json()
    assert body["cohort"] == "Ru'ya 2026"


async def test_roles_is_a_single_value_for_a_single_role_account(db, client):
    user = await _user(db, roles=["student"])
    body = (await client.get(URL, headers=_headers(user))).json()
    assert body["roles"] == "student"


async def test_roles_lists_every_role_a_multi_role_account_holds(db, client):
    """The reason this is a joined list and not one value: an Intercom rule
    reading `roles contains student` has to still match someone who also
    teaches. A single `role` string would drop one of them."""
    user = await _user(db, roles=["student", "instructor"])
    body = (await client.get(URL, headers=_headers(user))).json()
    assert body["roles"] == "student,instructor"


async def test_card_id_uses_the_student_prefix(db, client):
    """`format_card_id` branches on roles, and the roles column hydrates as
    either enums or strings depending on the driver — this is what proves the
    service passes the normalised form and a student isn't labelled staff."""
    user = await _user(db, roles=["student"], card_number=12)
    body = (await client.get(URL, headers=_headers(user))).json()
    assert body["card_id"] == "SP-ST-0012-UAE"


async def test_card_id_uses_the_staff_prefix_for_a_non_student(db, client):
    user = await _user(db, roles=["operations"], card_number=12)
    body = (await client.get(URL, headers=_headers(user))).json()
    assert body["card_id"] == "SP-0012-UAE"
