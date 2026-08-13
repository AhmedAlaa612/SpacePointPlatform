"""Operate v2 (Stage 7C) router tests — the HTTP surface end to end.
Redis-free (uses the `client` fixture).

The simulation itself is covered as pure functions in
`tests/services/missions/operate/test_operate_pure_functions.py`; what these
assert is the wiring: that the briefing is readable without spending a
retry, that a command lands on the event log with its sim time, that the
handbook's disclosure follows the variant, and that finishing freezes a
debrief that can be re-read later.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Operate Router User", email=f"opr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _operate_mission(db, *, author, config=None, team_policy="solo") -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Router Operate Mission", slug=f"router-operate-{uuid.uuid4().hex[:8]}",
        kind="operate", authored_by=author.id, status="published", team_policy=team_policy,
        summary="Fly it.",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Cadet", position=1, points=120,
        config=config if config is not None else {
            "pass_threshold": 50,
            "handbook_disclosure": "full",
            "shuffle_faults": False,
            "injected_faults": ["seu"],
            "orbit": {"orbits": 2, "time_compression": 18.0},
            "objectives": {"science_takes": 2, "downlink_mb": 40, "soc_floor": 0.30},
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


async def _start(client, mission, variant, student, team_id=None):
    body = {"variant_id": str(variant.id)}
    if team_id:
        body["team_id"] = str(team_id)
    res = await client.post(f"/missions/{mission.id}/attempts", headers=_headers(student), json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --------------------------------------------------------------------------
# Briefing — readable before an attempt exists
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_briefing_is_readable_without_creating_an_attempt(db, client):
    """The whole reason the briefing has its own route: reading the flight
    rules must never cost a retry."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    res = await client.get(f"/missions/operate/briefing/{mission.id}", headers=_headers(student))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["variant_label"] == "Cadet"
    assert body["orbit"]["orbits"] == 2
    assert 95.0 < body["orbit"]["period_minutes"] < 96.0
    assert 7.5 < body["orbit"]["velocity_km_s"] < 7.7
    assert len(body["objectives"]) == 4
    assert body["handbook"] and body["commands"] and body["flight_rules"]
    assert body["assumptions"]

    # and no attempt was created by reading it
    detail = await client.get(f"/missions/{mission.id}", headers=_headers(student))
    assert detail.json()["attempts"] == []


@pytest.mark.asyncio
async def test_briefing_can_be_asked_for_a_specific_variant(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    harder = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Flight Director", position=2, points=350,
        config={"pass_threshold": 80, "orbit": {"orbits": 4}},
    )
    db.add(harder)
    student = await _user(db)
    await db.commit()

    res = await client.get(
        f"/missions/operate/briefing/{mission.id}",
        params={"variant_id": str(harder.id)}, headers=_headers(student),
    )
    assert res.status_code == 200
    assert res.json()["variant_label"] == "Flight Director"
    assert res.json()["orbit"]["orbits"] == 4


@pytest.mark.asyncio
async def test_briefing_404s_for_a_non_operate_mission(db, client):
    author = await _user(db, roles=["operations"])
    quiz = Mission(
        id=uuid.uuid4(), title="A quiz", slug=f"q-{uuid.uuid4().hex[:8]}",
        kind="quiz", authored_by=author.id, status="published",
    )
    db.add(quiz)
    student = await _user(db)
    await db.commit()

    res = await client.get(f"/missions/operate/briefing/{quiz.id}", headers=_headers(student))
    assert res.status_code == http_status.HTTP_404_NOT_FOUND


# --------------------------------------------------------------------------
# The live console
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_state_drives_the_whole_console_in_one_fetch(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    res = await client.get(f"/missions/operate/attempts/{attempt_id}", headers=_headers(student))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["attempt_status"] == "in_progress"
    assert body["events"] == []
    assert body["expired"] is False
    assert body["phase"]["orbit_number"] == 1
    assert len(body["subsystems"]) == 5
    assert len(body["objectives"]) == 4
    assert body["telemetry"]["battery_soc"] > 0
    assert body["spacecraft_log"], "the spacecraft should be narrating its own orbit"


@pytest.mark.asyncio
async def test_a_fresh_attempt_is_not_already_passing(db, client):
    """v1 shipped this exact bug: an untouched attempt reported 100%."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    body = (await client.get(f"/missions/operate/attempts/{attempt_id}", headers=_headers(student))).json()
    assert body["score"] < body["pass_threshold"]
    assert body["objectives_score"] < 100


@pytest.mark.asyncio
async def test_finishing_immediately_fails_the_attempt(db, client):
    """The v1 exploit, as an HTTP regression test: start, finish, pass with
    full points. It must fail now, and no points may be awarded."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    res = await client.post(f"/missions/operate/attempts/{attempt_id}/finish", headers=_headers(student))
    assert res.status_code == 200, res.text
    assert res.json()["passed"] is False
    assert res.json()["score"] < 50
    assert res.json()["state"]["attempt_status"] == "failed"


@pytest.mark.asyncio
async def test_command_lands_on_the_log_with_its_sim_time(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    res = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command",
        headers=_headers(student), json={"command": "STATUS"},
    )
    assert res.status_code == 200, res.text
    event = res.json()["event"]
    assert event["command"] == "STATUS"
    assert event["success"] is True
    assert event["seq"] == 1
    assert "sim_t" in event
    assert res.json()["state"]["events"][0]["command"] == "STATUS"


@pytest.mark.asyncio
async def test_command_arguments_are_kept(db, client):
    """SatKit echoed the parameter; v1 accepted and silently dropped it."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    res = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command",
        headers=_headers(student), json={"command": "UPDATE_BEACON 45"},
    )
    assert res.json()["event"]["arg"] == "45"
    assert "45" in res.json()["event"]["message"]


@pytest.mark.asyncio
async def test_unknown_command_is_rejected_but_still_logged(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    res = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command",
        headers=_headers(student), json={"command": "MAKE_COFFEE"},
    )
    assert res.status_code == 200
    assert res.json()["event"]["success"] is False
    assert "UNRECOGNIZED" in res.json()["event"]["message"]


@pytest.mark.asyncio
async def test_commands_are_refused_once_the_flight_is_decided(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    await client.post(f"/missions/operate/attempts/{attempt_id}/finish", headers=_headers(student))
    res = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command",
        headers=_headers(student), json={"command": "HELP"},
    )
    assert res.status_code == http_status.HTTP_409_CONFLICT


# --------------------------------------------------------------------------
# The Ops Handbook (D-d)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handbook_disclosure_follows_the_variant(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(
        db, author=author, config={"pass_threshold": 75, "handbook_disclosure": "reference"},
    )
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    res = await client.get(f"/missions/operate/attempts/{attempt_id}/handbook", headers=_headers(student))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["disclosure"] == "reference"
    assert body["entries"], "you always get told what to watch"
    assert all("action" not in e for e in body["entries"]), "the response is withheld at this difficulty"
    # The command reference is never withheld — knowing a command exists is
    # not the puzzle; knowing when to reach for it is.
    assert body["commands"]
    assert body["flight_rules"]
    assert body["assumptions"]


@pytest.mark.asyncio
async def test_full_disclosure_spells_out_the_response(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)  # handbook_disclosure="full"
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    body = (await client.get(
        f"/missions/operate/attempts/{attempt_id}/handbook", headers=_headers(student),
    )).json()
    assert all("action" in e and "if_ignored" in e for e in body["entries"])


# --------------------------------------------------------------------------
# The debrief (Stage 7C-8)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_debrief_is_unavailable_until_the_flight_ends(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    res = await client.get(f"/missions/operate/attempts/{attempt_id}/debrief", headers=_headers(student))
    assert res.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_debrief_freezes_the_flight_and_explains_every_fault(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    await client.post(
        f"/missions/operate/attempts/{attempt_id}/command",
        headers=_headers(student), json={"command": "COLLECT_SAMPLE"},
    )
    await client.post(f"/missions/operate/attempts/{attempt_id}/finish", headers=_headers(student))

    res = await client.get(f"/missions/operate/attempts/{attempt_id}/debrief", headers=_headers(student))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["attempt_status"] in ("passed", "failed")
    assert body["trace"], "the telemetry trace is frozen at finish time"
    assert body["timeline"]["orbits"] == 2
    assert body["timeline"]["passes"] and body["timeline"]["eclipses"]
    assert body["command_markers"], "your own actions are pinned to the flight clock"
    assert body["report"]["notes"], "a debrief that says nothing teaches nothing"
    assert body["objectives"]
    # Disclosure is always full here — withholding the explanation after the
    # flight serves nobody.
    for window in body["anomaly_windows"]:
        assert window["teaching"]["action"]


@pytest.mark.asyncio
async def test_debrief_is_stable_when_read_again(db, client):
    """It reads the frozen trace, not a re-simulation, so a debrief opened
    later shows the flight that was actually graded."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)
    await client.post(f"/missions/operate/attempts/{attempt_id}/finish", headers=_headers(student))

    first = (await client.get(f"/missions/operate/attempts/{attempt_id}/debrief", headers=_headers(student))).json()
    second = (await client.get(f"/missions/operate/attempts/{attempt_id}/debrief", headers=_headers(student))).json()
    assert first["score"] == second["score"]
    assert first["trace"] == second["trace"]


# --------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_another_student_cannot_read_or_fly_your_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    intruder = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    assert (await client.get(
        f"/missions/operate/attempts/{attempt_id}", headers=_headers(intruder),
    )).status_code == http_status.HTTP_404_NOT_FOUND
    assert (await client.post(
        f"/missions/operate/attempts/{attempt_id}/command",
        headers=_headers(intruder), json={"command": "HELP"},
    )).status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_an_attempt_of_another_kind_is_not_reachable_here(db, client):
    author = await _user(db, roles=["operations"])
    quiz = Mission(
        id=uuid.uuid4(), title="Quiz", slug=f"quiz-{uuid.uuid4().hex[:8]}",
        kind="quiz", authored_by=author.id, status="published",
    )
    db.add(quiz)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=quiz.id, label="Only", position=1, points=10,
        config={"pass_threshold": 50, "questions": []},
    )
    db.add(variant)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, quiz, variant, student)

    res = await client.get(f"/missions/operate/attempts/{attempt_id}", headers=_headers(student))
    assert res.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_crew_roles_are_rejected_on_a_solo_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = await _start(client, mission, variant, student)

    res = await client.post(
        f"/missions/operate/attempts/{attempt_id}/crew", headers=_headers(student), json={"role": "eps"},
    )
    assert res.status_code == http_status.HTTP_400_BAD_REQUEST
