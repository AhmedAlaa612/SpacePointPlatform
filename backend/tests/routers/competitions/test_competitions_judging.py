"""Competition judging domain (2026-08-24) — `/competitions/admin/*` and
`/competitions/judge/*`: rubric authoring, blind per-judge scoring, the
publish gate, the leaderboard, and judge-roster management.
"""

import io
import uuid

import openpyxl
import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.competitions.judging import CompetitionJudge
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.team import Team
from app.models.user import User
from app.services.lms.program import assign_lms_program
from app.services.teams import create_team, team_member_ids

RUBRIC_CRITERIA = [
    {"key": "design", "label": "Design Quality", "max_points": 30},
    {"key": "execution", "label": "Execution", "max_points": 25},
]


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Judging Test Ops", email=f"jops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _judge(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Judging Test Judge", email=f"jjudge-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["judge"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Judging Test Student", email=f"jstu-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _program_and_cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"RUYA-{uuid.uuid4().hex[:8]}", name="Ru'ya Space Race",
        program_type="competition", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Qualifier", status="running")
    db.add(cohort)
    await db.flush()
    return program, cohort


# ── Rubric ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rubric_get_404s_before_any_rubric_is_authored(db, client):
    ops = await _ops(db)
    program, _cohort = await _program_and_cohort(db)
    await db.commit()

    resp = await client.get(f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_ops_can_author_and_re_edit_a_rubric(db, client):
    ops = await _ops(db)
    program, _cohort = await _program_and_cohort(db)
    await db.commit()

    created = await client.put(
        f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(ops),
        json={"name": "Ru'ya Rubric", "criteria": RUBRIC_CRITERIA},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "Ru'ya Rubric"
    assert [c["key"] for c in body["criteria"]] == ["design", "execution"]

    # Re-edit: drop "execution", add "bonus" — a full declarative sync, not append.
    edited = await client.put(
        f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(ops),
        json={"name": "Ru'ya Rubric v2", "criteria": [
            {"key": "design", "label": "Design Quality", "max_points": 35},
            {"key": "teamwork", "label": "Teamwork", "max_points": 10},
        ]},
    )
    assert edited.status_code == 200
    edited_body = edited.json()
    assert edited_body["id"] == body["id"]
    assert {c["key"] for c in edited_body["criteria"]} == {"design", "teamwork"}
    assert next(c for c in edited_body["criteria"] if c["key"] == "design")["max_points"] == 35


@pytest.mark.asyncio
async def test_a_student_cannot_author_a_rubric(db, client):
    student = await _student(db)
    program, _cohort = await _program_and_cohort(db)
    await db.commit()

    resp = await client.put(
        f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(student),
        json={"name": "Nope", "criteria": RUBRIC_CRITERIA},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_cohort_scoped_rubrics_are_isolated_across_cohorts(db, client):
    ops = await _ops(db)
    program = Program(
        id=uuid.uuid4(), code=f"RUYA-SEP-{uuid.uuid4().hex[:8]}", name="Ru'ya Space Race Isolation Test",
        program_type="competition", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()

    cohort_a = Cohort(id=uuid.uuid4(), program_id=program.id, name="Qualifiers Stage", status="running")
    cohort_b = Cohort(id=uuid.uuid4(), program_id=program.id, name="Finals Stage", status="running")
    db.add_all([cohort_a, cohort_b])
    await db.commit()

    # Author rubric for Cohort A
    resp_a = await client.put(
        f"/competitions/admin/cohorts/{cohort_a.id}/rubric", headers=_headers(ops),
        json={
            "name": "Qualifiers Rubric",
            "criteria": [
                {"key": "concept", "label": "Mission Concept", "max_points": 15},
                {"key": "circuit", "label": "Circuit Design", "max_points": 15},
            ],
        },
    )
    assert resp_a.status_code == 200, resp_a.text
    body_a = resp_a.json()
    assert body_a["name"] == "Qualifiers Rubric"
    assert [c["key"] for c in body_a["criteria"]] == ["concept", "circuit"]

    # Author rubric for Cohort B with completely different criteria
    resp_b = await client.put(
        f"/competitions/admin/cohorts/{cohort_b.id}/rubric", headers=_headers(ops),
        json={
            "name": "Finals Rubric",
            "criteria": [
                {"key": "assembly", "label": "Hardware Assembly", "max_points": 20},
                {"key": "qa", "label": "Live Q&A", "max_points": 10},
            ],
        },
    )
    assert resp_b.status_code == 200, resp_b.text
    body_b = resp_b.json()
    assert body_b["name"] == "Finals Rubric"
    assert [c["key"] for c in body_b["criteria"]] == ["assembly", "qa"]

    # Verify Cohort A's rubric was NOT altered by Cohort B
    check_a = await client.get(f"/competitions/admin/cohorts/{cohort_a.id}/rubric", headers=_headers(ops))
    assert check_a.status_code == 200
    check_a_body = check_a.json()
    assert check_a_body["name"] == "Qualifiers Rubric"
    assert [c["key"] for c in check_a_body["criteria"]] == ["concept", "circuit"]
    assert check_a_body["id"] != body_b["id"]


# ── Judge roster ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ops_can_invite_list_and_revoke_a_judge(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    invited = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/judges", headers=_headers(ops),
        json={"name": "Dr. Amina", "email": f"amina-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert invited.status_code == 201, invited.text
    judge_user_id = invited.json()["user_id"]

    listed = await client.get(f"/competitions/admin/cohorts/{cohort.id}/judges", headers=_headers(ops))
    assert listed.status_code == 200
    row = next(r for r in listed.json() if r["user_id"] == judge_user_id)
    assert row["scored_count"] == 0

    revoked = await client.delete(
        f"/competitions/admin/cohorts/{cohort.id}/judges/{judge_user_id}", headers=_headers(ops),
    )
    assert revoked.status_code == http_status.HTTP_204_NO_CONTENT

    revoked_again = await client.delete(
        f"/competitions/admin/cohorts/{cohort.id}/judges/{judge_user_id}", headers=_headers(ops),
    )
    assert revoked_again.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_inviting_an_existing_account_as_judge_sends_a_registered_notice_not_a_password_email(
    db, client, monkeypatch,
):
    """2026-09-10: previously an already-existing account added as a judge
    got no email at all. Now it gets send_registered_notice_email — no
    token/password step, just "you're registered, log in"."""
    ops = await _ops(db)
    program, cohort = await _program_and_cohort(db)
    existing = await _judge(db)
    await db.commit()

    captured = {}

    async def _fake_send(to, subject, body, **kwargs):
        captured["subject"] = subject
        captured["body"] = body
        return True

    monkeypatch.setattr("app.services.lms.ops_integration.try_send_email", _fake_send)

    invited = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/judges", headers=_headers(ops),
        json={"name": existing.full_name, "email": existing.email},
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["user_id"] == str(existing.id)

    assert captured["subject"] == f"You're confirmed as a judge — {program.name} ({cohort.name})"
    assert "Step 1" not in captured["body"]


@pytest.mark.asyncio
async def test_reinviting_an_already_assigned_judge_sends_no_email(db, client, monkeypatch):
    """The docstring's idempotency promise — re-inviting a judge already
    assigned to this cohort is a true no-op, not a re-send of the
    "you're confirmed" notice on every retry/double-click."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    existing = await _judge(db)
    await db.commit()

    sent = False

    async def _fake_send(*args, **kwargs):
        nonlocal sent
        sent = True
        return True

    monkeypatch.setattr("app.services.lms.ops_integration.try_send_email", _fake_send)

    first = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/judges", headers=_headers(ops),
        json={"name": existing.full_name, "email": existing.email},
    )
    assert first.status_code == 201, first.text
    assert sent is True  # first assignment to this cohort — expected to notify

    sent = False
    second = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/judges", headers=_headers(ops),
        json={"name": existing.full_name, "email": existing.email},
    )
    assert second.status_code == 201, second.text
    assert sent is False  # already assigned — no repeat email


@pytest.mark.asyncio
async def test_inviting_a_judge_can_opt_out_of_the_email_while_still_creating_the_account(
    db, client, monkeypatch,
):
    """"Send email" (2026-09-10) is independent of the invite itself — the
    account and assignment are always created, only the notification is
    optional, same shape as send_welcome_email elsewhere."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()
    sent = False

    async def _fake_send(*args, **kwargs):
        nonlocal sent
        sent = True
        return True

    monkeypatch.setattr("app.services.lms.ops_integration.try_send_email", _fake_send)

    invited = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/judges", headers=_headers(ops),
        json={"name": "Silent Judge", "email": f"silent-judge-{uuid.uuid4().hex[:8]}@example.com", "send_email": False},
    )
    assert invited.status_code == 201, invited.text
    assert sent is False

    listed = await client.get(f"/competitions/admin/cohorts/{cohort.id}/judges", headers=_headers(ops))
    assert any(r["user_id"] == invited.json()["user_id"] for r in listed.json())


# ── Judge scoring surface ────────────────────────────────────────────────

async def _judge_setup(db):
    """Ops-authored rubric + cohort + one team + one assigned judge."""
    ops = await _ops(db)
    program, cohort = await _program_and_cohort(db)
    student_a = await _student(db)
    student_b = await _student(db)
    judge = await _judge(db)
    await db.commit()

    team = await create_team(
        db, name="Falcon Eye", created_by=student_a.id, cohort_id=cohort.id, member_ids=[student_b.id],
    )
    db.add(CompetitionJudge(id=uuid.uuid4(), cohort_id=cohort.id, user_id=judge.id))

    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Ru'ya Checklist")
    db.add(lms_program)
    await db.flush()
    poster_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Poster", submission_prompt="Paste your poster link", scope="team",
    )
    db.add(poster_item)
    await db.flush()

    await client_rubric_seed(db, program_id=program.id)
    await db.commit()
    return ops, program, cohort, team, judge, poster_item


async def client_rubric_seed(db, *, program_id):
    from app.services.competitions.judging import upsert_rubric
    await upsert_rubric(db, program_id=program_id, name="Ru'ya Rubric", criteria=RUBRIC_CRITERIA)


@pytest.mark.asyncio
async def test_judge_lists_only_their_own_assigned_cohorts(db, client):
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)
    other_cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Finalists", status="running")
    db.add(other_cohort)
    await db.commit()

    resp = await client.get("/competitions/judge/cohorts", headers=_headers(judge))
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert ids == {str(cohort.id)}
    assert resp.json()[0]["program_name"] == "Ru'ya Space Race"


@pytest.mark.asyncio
async def test_judge_only_sees_teams_in_their_assigned_cohort(db, client):
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)
    other_cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Finalists", status="running")
    db.add(other_cohort)
    await db.commit()

    ok = await client.get(f"/competitions/judge/teams?cohort_id={cohort.id}", headers=_headers(judge))
    assert ok.status_code == 200
    assert len(ok.json()) == 1
    assert ok.json()[0]["id"] == str(team.id)
    assert ok.json()[0]["already_scored"] is False

    forbidden = await client.get(f"/competitions/judge/teams?cohort_id={other_cohort.id}", headers=_headers(judge))
    assert forbidden.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_judge_roster_shows_a_teams_final_submission_lock(db, client):
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)

    unlocked = await client.get(f"/competitions/judge/teams?cohort_id={cohort.id}", headers=_headers(judge))
    row = unlocked.json()[0]
    assert row["locked"] is False
    assert "items_done" in row
    assert "items_total" in row
    assert "pct" in row
    assert "member_count" in row

    from app.services.competitions.team_management import finalize_team_submission
    await finalize_team_submission(db, team_id=team.id, locked_by_user_id=ops.id)
    await db.commit()

    locked = await client.get(f"/competitions/judge/teams?cohort_id={cohort.id}", headers=_headers(judge))
    assert locked.json()[0]["locked"] is True


@pytest.mark.asyncio
async def test_judge_team_detail_surfaces_submissions_and_rubric(db, client):
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)

    resp = await client.get(f"/competitions/judge/teams/{team.id}", headers=_headers(judge))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["team"]["id"] == str(team.id)
    assert body["rubric"]["name"] == "Ru'ya Rubric"
    assert {c["key"] for c in body["rubric"]["criteria"]} == {"design", "execution"}
    assert len(body["submissions"]) == 1
    assert body["submissions"][0]["item_id"] == str(poster_item.id)
    assert body["submissions"][0]["status"] == "pending"
    assert body["own_score"] is None


@pytest.mark.asyncio
async def test_judge_team_detail_shows_who_submitted_and_when(db, client):
    from datetime import datetime, timezone
    from app.models.lms.program import LmsProgramTeamItemProgress

    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)
    student_b = User(
        id=uuid.uuid4(), full_name="Lina Nasser", email=f"lina-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(student_b)
    await db.flush()
    submitted_at = datetime(2026, 8, 24, 14, 30, tzinfo=timezone.utc)
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster_item.id, team_id=team.id, status="done",
        submitted_url="https://canva.com/design/poster-v1", updated_by_user_id=student_b.id,
        updated_at=submitted_at,
    ))
    await db.commit()

    resp = await client.get(f"/competitions/judge/teams/{team.id}", headers=_headers(judge))
    assert resp.status_code == 200, resp.text
    submission = resp.json()["submissions"][0]
    assert submission["submitted_url"] == "https://canva.com/design/poster-v1"
    assert submission["updated_by_name"] == "Lina Nasser"
    assert submission["updated_at"] is not None


@pytest.mark.asyncio
async def test_judge_team_detail_groups_multiple_labeled_links_on_a_multi_link_submission(db, client):
    """Ops's own ask (2026-09-14): several labeled links in one submission
    (e.g. mem1/mem2/team link), and judges/ops see them grouped under the
    one submission item rather than as several separate items."""
    from app.models.lms.program import LmsProgramTeamItemProgress

    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)
    poster_item.submission_multi_link = True
    links = [
        {"label": "Member 1 link", "url": "https://example.com/mem1"},
        {"label": "Member 2 link", "url": "https://example.com/mem2"},
        {"label": "Team link", "url": "https://example.com/team"},
    ]
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster_item.id, team_id=team.id, status="done",
        submitted_url=links[0]["url"], submitted_links=links,
    ))
    await db.commit()

    resp = await client.get(f"/competitions/judge/teams/{team.id}", headers=_headers(judge))
    assert resp.status_code == 200, resp.text
    submission = resp.json()["submissions"][0]
    assert submission["submission_multi_link"] is True
    assert len(submission["submitted_links"]) == 3
    assert submission["submitted_links"][0] == {
        "label": "Member 1 link", "url": "https://example.com/mem1", "text": None,
    }
    assert submission["submitted_links"][2]["label"] == "Team link"


@pytest.mark.asyncio
async def test_judge_team_detail_mission_runs_is_empty_without_any_team_scoped_mission_run(db, client):
    """The safety property that matters most for Phase 3: `_judge_setup`'s
    team has only the pre-existing team-scoped submission item, no
    mission_run — every judge/cohort running today's individual-only
    missions must see an empty `mission_runs` list, not an error and not
    a stray row."""
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)

    resp = await client.get(f"/competitions/judge/teams/{team.id}", headers=_headers(judge))
    assert resp.status_code == 200, resp.text
    assert resp.json()["mission_runs"] == []


# ── Phase 3: judge visibility into team design missions ─────────────────────

async def _judge_setup_with_mission_run(db, *, team_policy="team"):
    """`_judge_setup` plus a team-scoped design mission_run item on the
    same checklist — the Phase 3 surface under test."""
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)
    mission = Mission(
        id=uuid.uuid4(), title="Team CubeSat", slug=f"team-cubesat-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=ops.id, status="published", team_policy=team_policy,
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=100)
    db.add(variant)
    await db.flush()
    lms_program = (await db.execute(select(LmsProgram).where(LmsProgram.program_id == program.id))).scalars().one()
    mission_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id, scope="team",
    )
    db.add(mission_item)
    await db.commit()
    return ops, program, cohort, team, judge, poster_item, mission, variant, mission_item


async def _assign_team(db, *, team_id, cohort_id):
    for member_id in await team_member_ids(db, team_id=team_id):
        await assign_lms_program(db, user_id=member_id, cohort_id=cohort_id)
    await db.commit()


@pytest.mark.asyncio
async def test_judge_team_detail_includes_the_team_mission_run_and_keeps_it_out_of_submissions(db, client):
    ops, program, cohort, team, judge, poster_item, mission, variant, mission_item = await _judge_setup_with_mission_run(db)
    await _assign_team(db, team_id=team.id, cohort_id=cohort.id)

    resp = await client.get(f"/competitions/judge/teams/{team.id}", headers=_headers(judge))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Never leaks into the submission-links panel — it has no link/status
    # of its own, only the original poster submission belongs there.
    assert len(body["submissions"]) == 1
    assert body["submissions"][0]["item_id"] == str(poster_item.id)

    assert len(body["mission_runs"]) == 1
    run = body["mission_runs"][0]
    assert run["mission_id"] == str(mission.id)
    assert run["title"] == mission.title
    assert run["attempt_id"] is not None
    assert run["status"] == "in_progress"


@pytest.mark.asyncio
async def test_judge_mission_run_design_detail_404s_before_the_team_has_started_designing(db, client):
    ops, program, cohort, team, judge, poster_item, mission, variant, mission_item = await _judge_setup_with_mission_run(db)
    await _assign_team(db, team_id=team.id, cohort_id=cohort.id)
    attempt = (await db.execute(select(MissionAttempt).where(MissionAttempt.mission_id == mission.id))).scalars().one()

    resp = await client.get(
        f"/competitions/judge/teams/{team.id}/mission-runs/{attempt.id}/design-detail", headers=_headers(judge),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_judge_can_view_a_team_mission_runs_design_dashboard_once_started(db, client):
    ops, program, cohort, team, judge, poster_item, mission, variant, mission_item = await _judge_setup_with_mission_run(db)
    await _assign_team(db, team_id=team.id, cohort_id=cohort.id)
    attempt = (await db.execute(select(MissionAttempt).where(MissionAttempt.mission_id == mission.id))).scalars().one()
    member_ids = await team_member_ids(db, team_id=team.id)
    a_teammate = await db.get(User, member_ids[0])

    # Auto-creates the Design row, same as the ops-facing test for the
    # identical scenario (test_design_detail_shows_the_students_real_entered_values).
    started = await client.get(f"/missions/design/attempts/{attempt.id}", headers=_headers(a_teammate))
    assert started.status_code == 200, started.text
    named = await client.patch(
        f"/missions/design/attempts/{attempt.id}", headers=_headers(a_teammate), json={"design_name": "Falcon-1"},
    )
    assert named.status_code == 200, named.text

    resp = await client.get(
        f"/competitions/judge/teams/{team.id}/mission-runs/{attempt.id}/design-detail", headers=_headers(judge),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["design_name"] == "Falcon-1"
    assert resp.json()["attempt_id"] == str(attempt.id)


@pytest.mark.asyncio
async def test_judge_mission_run_design_detail_404s_for_an_attempt_belonging_to_a_different_team(db, client):
    """Security boundary: a judge who knows a real attempt id can't view it
    through a team it doesn't belong to, even a team in a cohort they DO
    have access to — the route must check attempt.team_id == team_id, not
    just cohort access."""
    ops, program, cohort, team, judge, poster_item, mission, variant, mission_item = await _judge_setup_with_mission_run(db)
    await _assign_team(db, team_id=team.id, cohort_id=cohort.id)
    attempt = (await db.execute(select(MissionAttempt).where(MissionAttempt.mission_id == mission.id))).scalars().one()

    other_student_a = await _student(db)
    other_student_b = await _student(db)
    await db.commit()
    other_team = await create_team(
        db, name="Other Team", created_by=other_student_a.id, cohort_id=cohort.id, member_ids=[other_student_b.id],
    )
    await db.commit()

    resp = await client.get(
        f"/competitions/judge/teams/{other_team.id}/mission-runs/{attempt.id}/design-detail", headers=_headers(judge),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_judge_without_cohort_access_cannot_view_a_teams_mission_run_design_detail(db, client):
    ops, program, cohort, team, judge, poster_item, mission, variant, mission_item = await _judge_setup_with_mission_run(db)
    await _assign_team(db, team_id=team.id, cohort_id=cohort.id)
    attempt = (await db.execute(select(MissionAttempt).where(MissionAttempt.mission_id == mission.id))).scalars().one()
    unassigned_judge = await _judge(db)
    await db.commit()

    resp = await client.get(
        f"/competitions/judge/teams/{team.id}/mission-runs/{attempt.id}/design-detail",
        headers=_headers(unassigned_judge),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_judge_submits_a_score_then_can_revise_it_before_publish(db, client):
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)

    submitted = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 25, "execution": 20}, "bonus_points": 2, "submitted": True},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["total_points"] == 47
    assert submitted.json()["submitted"] is True

    revised = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 30, "execution": 25}, "bonus_points": 0, "submitted": True},
    )
    assert revised.status_code == 200
    assert revised.json()["total_points"] == 55
    assert revised.json()["id"] == submitted.json()["id"]

    roster = await client.get(f"/competitions/judge/teams?cohort_id={cohort.id}", headers=_headers(judge))
    assert roster.json()[0]["already_scored"] is True


@pytest.mark.asyncio
async def test_an_autosaved_draft_never_counts_as_scored_until_submitted(db, client):
    """The judge scoring UI autosaves on every keystroke, but a draft alone
    must never mark a team done (2026-08-27 fix) — only an explicit submit
    does, and it's a one-way ratchet from there."""
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)

    draft = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 25, "execution": 20}, "bonus_points": 0},
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["submitted"] is False

    roster = await client.get(f"/competitions/judge/teams?cohort_id={cohort.id}", headers=_headers(judge))
    assert roster.json()[0]["already_scored"] is False

    finalized = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 25, "execution": 20}, "bonus_points": 0, "submitted": True},
    )
    assert finalized.status_code == 200
    assert finalized.json()["submitted"] is True
    assert finalized.json()["id"] == draft.json()["id"]

    roster_after = await client.get(f"/competitions/judge/teams?cohort_id={cohort.id}", headers=_headers(judge))
    assert roster_after.json()[0]["already_scored"] is True

    # A later autosaved edit (submitted omitted => False) must not un-score it.
    edited = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 30, "execution": 20}, "bonus_points": 0},
    )
    assert edited.status_code == 200
    assert edited.json()["submitted"] is True

    roster_still = await client.get(f"/competitions/judge/teams?cohort_id={cohort.id}", headers=_headers(judge))
    assert roster_still.json()[0]["already_scored"] is True


@pytest.mark.asyncio
async def test_score_rejects_an_out_of_range_or_incomplete_submission(db, client):
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)

    too_high = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 999, "execution": 20}},
    )
    assert too_high.status_code == http_status.HTTP_400_BAD_REQUEST

    missing_key = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 25}},
    )
    assert missing_key.status_code == http_status.HTTP_400_BAD_REQUEST


# ── Leaderboard + publish ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_leaderboard_averages_across_judges_and_ranks_unscored_last(db, client):
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)
    judge_two = await _judge(db)
    db.add(CompetitionJudge(id=uuid.uuid4(), cohort_id=cohort.id, user_id=judge_two.id))
    unscored_team = await create_team(db, name="Silent Comet", created_by=judge_two.id, cohort_id=cohort.id)
    await db.commit()

    await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 30, "execution": 20}, "bonus_points": 0, "submitted": True},
    )
    await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge_two),
        json={"criterion_scores": {"design": 20, "execution": 20}, "bonus_points": 0, "submitted": True},
    )

    board = await client.get(f"/competitions/admin/cohorts/{cohort.id}/leaderboard", headers=_headers(ops))
    assert board.status_code == 200
    rows = board.json()
    scored_row = next(r for r in rows if r["team_id"] == str(team.id))
    assert scored_row["score"] == 45.0  # avg(50, 40)
    assert scored_row["judges_scored"] == 2
    assert scored_row["rank"] == 1

    # Ops needs to see who scored what, not just the blended average.
    by_judge = {js["judge_user_id"]: js["total_points"] for js in scored_row["judge_scores"]}
    assert by_judge == {str(judge.id): 50, str(judge_two.id): 40}

    unscored_row = next(r for r in rows if r["team_id"] == str(unscored_team.id))
    assert unscored_row["judge_scores"] == []

    unscored_row = next(r for r in rows if r["team_id"] == str(unscored_team.id))
    assert unscored_row["status"] == "unscored"
    assert unscored_row["rank"] == 2


# ── Registration import, progression ─────────────────────────────────────

@pytest.mark.asyncio
async def test_export_workbook_has_a_scores_sheet_and_a_submissions_sheet(db, client):
    from datetime import datetime, timezone
    from app.models.lms.program import LmsProgramTeamItemProgress

    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster_item.id, team_id=team.id, status="done",
        submitted_url="https://canva.com/design/poster-v1", updated_by_user_id=judge.id,
        updated_at=datetime(2026, 8, 24, 14, 30, tzinfo=timezone.utc),
    ))
    await db.commit()
    await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 30, "execution": 20}, "bonus_points": 0, "submitted": True},
    )

    resp = await client.get(f"/competitions/admin/cohorts/{cohort.id}/export.xlsx", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment" in resp.headers["content-disposition"]

    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Scores", "Submissions"]

    scores = wb["Scores"]
    header = [c.value for c in scores[1]]
    assert header[:5] == ["Rank", "Team", "Avg Score", "Status", "Advanced To"]
    assert judge.full_name in header
    team_row = next(r for r in scores.iter_rows(min_row=2, values_only=True) if r[1] == "Falcon Eye")
    assert team_row[2] == 50.0  # 30 + 20

    submissions = wb["Submissions"]
    assert [c.value for c in submissions[1]] == ["Team", "Item", "Type", "Status", "Link", "Submitted At", "Submitted By"]
    sub_row = next(r for r in submissions.iter_rows(min_row=2, values_only=True) if r[0] == "Falcon Eye")
    assert sub_row[1] == "Poster"
    assert sub_row[4] == "https://canva.com/design/poster-v1"
    assert sub_row[6] == judge.full_name


@pytest.mark.asyncio
async def test_registration_import_preview_then_confirm_creates_teams(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["team_id", "team_name", "member_name", "email", "phone", "school"])
    sheet.append(["T1", "Falcon Eye", "Amir Salem", f"amir-{uuid.uuid4().hex[:6]}@example.com", "", ""])
    sheet.append(["T1", "Falcon Eye", "Lina Nasser", f"lina-{uuid.uuid4().hex[:6]}@example.com", "", ""])
    buf = io.BytesIO()
    wb.save(buf)

    preview_resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/preview",
        files={"file": ("roster.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_headers(ops),
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview_rows = preview_resp.json()["rows"]
    assert len(preview_rows) == 2
    assert all(r["issues"] == [] for r in preview_rows)

    # Nothing written yet — preview never touches the database.
    assert (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all() == []

    confirm_resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/confirm",
        json={"rows": [{k: v for k, v in r.items() if k != "issues"} for r in preview_rows]},
        headers=_headers(ops),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    body = confirm_resp.json()
    assert body["summary"] == {"total": 2, "created": 2, "matched": 0, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert [t.name for t in teams] == ["Falcon Eye"]


@pytest.mark.asyncio
async def test_registration_import_preview_flags_a_malformed_email_but_confirm_can_still_keep_it(db, client):
    """A malformed email (the exact 2026-08-28 prod-incident shape) is a
    warning ops can act on, not a hard block — confirming it as-is still
    creates the row, since nothing downstream chokes on a bad address."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["team_id", "team_name", "member_name", "email", "phone", "school"])
    sheet.append(["T1", "Falcon Eye", "Amir Salem", "456", "", ""])  # shifted-column garbage, the prod incident shape
    buf = io.BytesIO()
    wb.save(buf)

    preview_resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/preview",
        files={"file": ("roster.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_headers(ops),
    )
    assert preview_resp.status_code == 200, preview_resp.text
    [row] = preview_resp.json()["rows"]
    assert row["issues"] == ["Email is not valid"]

    # Confirming as-is (uncorrected) still writes the row — the note was
    # advisory, and ops chose not to act on it.
    confirm_resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/confirm",
        json={"rows": [{k: v for k, v in row.items() if k != "issues"}]},
        headers=_headers(ops),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["summary"] == {"total": 1, "created": 1, "matched": 0, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert [t.name for t in teams] == ["Falcon Eye"]
    bad_user = (await db.execute(select(User).where(User.email == "456"))).scalars().first()
    assert bad_user is not None


@pytest.mark.asyncio
async def test_registration_import_confirm_enqueues_a_ticket_email_per_created_row(db, arq_client, arq_redis):
    """Uploading a team roster should send each new member a ticket, same as
    manual registration — one `send_ticket_email` job per successfully
    imported row, not zero."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["team_id", "team_name", "member_name", "email", "phone", "school"])
    sheet.append(["T1", "Falcon Eye", "Amir Salem", f"amir-{uuid.uuid4().hex[:6]}@example.com", "", ""])
    sheet.append(["T1", "Falcon Eye", "Lina Nasser", f"lina-{uuid.uuid4().hex[:6]}@example.com", "", ""])
    buf = io.BytesIO()
    wb.save(buf)

    preview_resp = await arq_client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/preview",
        files={"file": ("roster.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_headers(ops),
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview_rows = preview_resp.json()["rows"]

    confirm_resp = await arq_client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/confirm",
        json={"rows": [{k: v for k, v in r.items() if k != "issues"} for r in preview_rows]},
        headers=_headers(ops),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["summary"] == {"total": 2, "created": 2, "matched": 0, "error": 0}

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 2


@pytest.mark.asyncio
async def test_registration_import_confirm_with_a_duplicate_email_enqueues_only_one_ticket(db, arq_client, arq_redis):
    """A sheet with the same email in two rows (a copy-paste mistake) makes
    the second row `matched` against the registration the first row just
    created — only the `created` row should get a send_ticket_email job, not
    both, since the two jobs firing back-to-back in the same request could
    otherwise race issue_ticket's read-then-write idempotency check and mail
    the student twice."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    dup_email = f"dup-{uuid.uuid4().hex[:6]}@example.com"
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["team_id", "team_name", "member_name", "email", "phone", "school"])
    sheet.append(["T1", "Falcon Eye", "Amir Salem", dup_email, "", ""])
    sheet.append(["T1", "Falcon Eye", "Amir Salem", dup_email, "", ""])
    buf = io.BytesIO()
    wb.save(buf)

    preview_resp = await arq_client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/preview",
        files={"file": ("roster.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_headers(ops),
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview_rows = preview_resp.json()["rows"]

    confirm_resp = await arq_client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/confirm",
        json={"rows": [{k: v for k, v in r.items() if k != "issues"} for r in preview_rows]},
        headers=_headers(ops),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["summary"] == {"total": 2, "created": 1, "matched": 1, "error": 0}

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1


@pytest.mark.asyncio
async def test_registration_import_confirm_can_opt_the_batch_out_of_ticket_and_welcome_emails(
    db, arq_client, arq_redis, monkeypatch,
):
    """`send_ticket_email: false` / `send_welcome_email: false` on the
    confirm request apply to the whole batch — ops importing a roster they
    plan to notify some other way (a WhatsApp broadcast, printed tickets)
    shouldn't be forced into two emails per row."""
    sent_welcome_emails = []

    async def _fake_send_set_password_email(user, *, purpose="welcome"):
        sent_welcome_emails.append(user.email)
        return True

    monkeypatch.setattr(
        "app.services.lms.ops_integration.send_set_password_email", _fake_send_set_password_email,
    )

    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["team_id", "team_name", "member_name", "email", "phone", "school"])
    sheet.append(["T2", "Silent Comet", "Zaid Omar", f"zaid-{uuid.uuid4().hex[:6]}@example.com", "", ""])
    buf = io.BytesIO()
    wb.save(buf)

    preview_resp = await arq_client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/preview",
        files={"file": ("roster.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_headers(ops),
    )
    assert preview_resp.status_code == 200, preview_resp.text
    preview_rows = preview_resp.json()["rows"]

    confirm_resp = await arq_client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/confirm",
        json={
            "rows": [{k: v for k, v in r.items() if k != "issues"} for r in preview_rows],
            "send_ticket_email": False, "send_welcome_email": False,
        },
        headers=_headers(ops),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["summary"] == {"total": 1, "created": 1, "matched": 0, "error": 0}

    assert await arq_redis.zrange("arq:queue", 0, -1) == []
    assert sent_welcome_emails == []


@pytest.mark.asyncio
async def test_registration_import_confirm_still_refuses_a_row_missing_a_required_field(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    await db.commit()

    row = {"row_number": 2, "team_id": "T1", "team_name": "Falcon Eye", "member_name": "", "email": "amir@example.com", "phone": None, "school": None}
    confirm_resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/registration-import/confirm",
        json={"rows": [row]},
        headers=_headers(ops),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    body = confirm_resp.json()
    assert body["summary"] == {"total": 1, "created": 0, "matched": 0, "error": 1}
    assert "Member name is required" in body["rows"][0]["reason"]


@pytest.mark.asyncio
async def test_advance_teams_via_http_moves_a_team_to_the_target_cohort(db, client):
    ops = await _ops(db)
    program, qualifier = await _program_and_cohort(db)
    finalists = Cohort(id=uuid.uuid4(), program_id=program.id, name="Finalists", status="registration_open")
    db.add(finalists)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Orientation",
    ))
    student = await _student(db)
    await db.commit()
    team = await create_team(db, name="Falcon Eye", created_by=student.id, cohort_id=qualifier.id)
    await db.commit()

    resp = await client.post(
        f"/competitions/admin/cohorts/{qualifier.id}/advance-teams", headers=_headers(ops),
        json={"team_ids": [str(team.id)], "to_cohort_id": str(finalists.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body[0]["team_name"] == "Falcon Eye" and body[0]["members_advanced"] == 1

    moved_team = (await db.execute(
        select(Team).where(Team.cohort_id == finalists.id, Team.name == "Falcon Eye")
    )).scalars().first()
    assert moved_team is not None

    # The Results tab needs to show this team already advanced — there's
    # no stored flag for it, so it's inferred from the same-named team
    # advance_teams itself just created in the sibling cohort.
    board = await client.get(f"/competitions/admin/cohorts/{qualifier.id}/leaderboard", headers=_headers(ops))
    row = next(r for r in board.json() if r["team_id"] == str(team.id))
    assert row["advanced_to"] == "Finalists"

    unadvanced_board = await client.get(f"/competitions/admin/cohorts/{finalists.id}/leaderboard", headers=_headers(ops))
    finalist_row = next(r for r in unadvanced_board.json() if r["team_id"] == str(moved_team.id))
    assert finalist_row["advanced_to"] is None  # nothing advances further from the last stage


async def _advanceable_team(db):
    """Shared setup for the two ticket-toggle tests below: a program with two
    cohorts and one single-member team in the source cohort, ready to advance.
    The member needs a linked Contact — advance_teams only creates a new-cohort
    Registration (and therefore a ticket) for a member whose contact_id is set,
    same as any other registration in this codebase."""
    ops = await _ops(db)
    program, qualifier = await _program_and_cohort(db)
    finalists = Cohort(id=uuid.uuid4(), program_id=program.id, name="Finalists", status="registration_open")
    db.add(finalists)
    contact = Contact(id=uuid.uuid4(), full_name="Judging Test Student", contact_roles=["student"], email=f"jstu-{uuid.uuid4().hex[:8]}@example.com")
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name=contact.full_name, email=contact.email,
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.commit()
    team = await create_team(db, name="Falcon Eye", created_by=student.id, cohort_id=qualifier.id)
    await db.commit()
    return ops, qualifier, finalists, team


@pytest.mark.asyncio
async def test_advancing_a_team_enqueues_a_ticket_for_its_new_registration(db, arq_client, arq_redis):
    ops, qualifier, finalists, team = await _advanceable_team(db)

    resp = await arq_client.post(
        f"/competitions/admin/cohorts/{qualifier.id}/advance-teams", headers=_headers(ops),
        json={"team_ids": [str(team.id)], "to_cohort_id": str(finalists.id)},
    )
    assert resp.status_code == 200, resp.text

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1


@pytest.mark.asyncio
async def test_advancing_a_team_can_opt_out_of_the_ticket_email(db, arq_client, arq_redis):
    ops, qualifier, finalists, team = await _advanceable_team(db)

    resp = await arq_client.post(
        f"/competitions/admin/cohorts/{qualifier.id}/advance-teams", headers=_headers(ops),
        json={"team_ids": [str(team.id)], "to_cohort_id": str(finalists.id), "send_ticket_email": False},
    )
    assert resp.status_code == 200, resp.text

    assert await arq_redis.zrange("arq:queue", 0, -1) == []


@pytest.mark.asyncio
async def test_publishing_closes_scoring_and_unpublish_reopens_it(db, client):
    ops, program, cohort, team, judge, poster_item = await _judge_setup(db)
    await db.commit()

    # The Results tab has to be able to show current state on load, not
    # only as the response to an action just taken.
    before = await client.get(f"/competitions/admin/cohorts/{cohort.id}/publication", headers=_headers(ops))
    assert before.status_code == 200 and before.json()["published"] is False

    published = await client.post(f"/competitions/admin/cohorts/{cohort.id}/publish", headers=_headers(ops))
    assert published.status_code == 200
    assert published.json()["published"] is True

    after_publish = await client.get(f"/competitions/admin/cohorts/{cohort.id}/publication", headers=_headers(ops))
    assert after_publish.json()["published"] is True

    blocked = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 25, "execution": 20}},
    )
    assert blocked.status_code == http_status.HTTP_409_CONFLICT

    unpublished = await client.post(f"/competitions/admin/cohorts/{cohort.id}/unpublish", headers=_headers(ops))
    assert unpublished.status_code == http_status.HTTP_204_NO_CONTENT

    after_unpublish = await client.get(f"/competitions/admin/cohorts/{cohort.id}/publication", headers=_headers(ops))
    assert after_unpublish.json()["published"] is False

    reopened = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 25, "execution": 20}},
    )
    assert reopened.status_code == 200


# ── Assign existing (self-registered) students (2026-09-14) ─────────────
# The Assign tab: students self-register via invite code first
# (routers/auth.py::student_signup — a Contact + User but no Registration
# yet), then ops finds them by search and assigns a Team ID here, rather
# than holding their info in a spreadsheet at all.

async def _self_registered_student(db, *, full_name: str = "Self Signup Student") -> User:
    email = f"selfsignup-{uuid.uuid4().hex[:8]}@example.com"
    contact = Contact(id=uuid.uuid4(), full_name=full_name, email=email, contact_roles=["student"])
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name=full_name, email=email, password_hash="x",
        roles=["student"], status="active", contact_id=contact.id, must_change_password=False,
    )
    db.add(user)
    await db.flush()
    return user


def _rows(resp):
    """Unwraps the paginated assignable-students shape (2026-10 rebuild:
    `{"items", "total", ...}`)."""
    body = resp.json()
    if isinstance(body, dict):
        return body["items"]
    return body


@pytest.mark.asyncio
async def test_assignable_students_reports_team_state_and_filters_unassigned(db, client):
    """Ops's own ask (2026-09-14): "see people not assigned to teams yet
    with that code I picked". Without the filter, every match comes back
    with its current team state (None/None if not on one yet); with it,
    already-teamed rows are dropped entirely."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    unassigned = await _self_registered_student(db, full_name="Not Yet Assigned")
    assigned = await _self_registered_student(db, full_name="Already Assigned")
    await db.commit()

    pre_assign = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [{"user_id": str(assigned.id), "team_id": "T1"}]},
        headers=_headers(ops),
    )
    assert pre_assign.status_code == 200, pre_assign.text

    full = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        headers=_headers(ops),
    )
    assert full.status_code == 200, full.text
    by_id = {r["id"]: r for r in _rows(full)}
    assert by_id[str(unassigned.id)]["team_id"] is None
    assert by_id[str(unassigned.id)]["team_name"] is None
    assert by_id[str(assigned.id)]["team_id"] == "T1"
    assert by_id[str(assigned.id)]["team_name"] == "T1"

    filtered = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"team_status": "no_team"},
        headers=_headers(ops),
    )
    assert filtered.status_code == 200, filtered.text
    filtered_ids = {r["id"] for r in _rows(filtered)}
    assert str(unassigned.id) in filtered_ids
    assert str(assigned.id) not in filtered_ids

    has_team = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"team_status": "has_team"},
        headers=_headers(ops),
    )
    assert has_team.status_code == 200, has_team.text
    has_team_ids = {r["id"] for r in _rows(has_team)}
    assert str(assigned.id) in has_team_ids
    assert str(unassigned.id) not in has_team_ids


@pytest.mark.asyncio
async def test_assignable_students_treats_a_manually_created_team_as_assigned(db, client):
    """A team made by hand in the Teams tab has no roster_team_id at all —
    `team_id` comes back None for its members, but `unassigned_only` must
    still exclude them (assignment is keyed on membership, not on
    roster_team_id being set)."""
    from app.services.teams import create_team

    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    student = await _self_registered_student(db)
    await db.commit()

    await create_team(db, name="Hand-Made Team", created_by=student.id, cohort_id=cohort.id, member_ids=[student.id])
    await db.commit()

    resp = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"team_status": "no_team"},
        headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text
    assert str(student.id) not in {r["id"] for r in _rows(resp)}

    unfiltered = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        headers=_headers(ops),
    )
    row = next(r for r in _rows(unfiltered) if r["id"] == str(student.id))
    assert row["team_id"] is None
    assert row["team_name"] == "Hand-Made Team"


@pytest.mark.asyncio
async def test_assignable_students_registered_only_excludes_unregistered_matches(db, client):
    """`registered_only` switches the candidate set from "matches my
    search, anywhere on the platform" to "actually has a Registration in
    this cohort" — a student who merely matches the search but never
    registered here must disappear once the filter is on, and the one who
    got assigned (which registers them) must show up as `registered`."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    never_registered = await _self_registered_student(db, full_name="Never Registered")
    will_register = await _self_registered_student(db, full_name="Will Register")
    await db.commit()

    assign = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [{"user_id": str(will_register.id), "team_id": "T1"}]},
        headers=_headers(ops),
    )
    assert assign.status_code == 200, assign.text

    unfiltered = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students", headers=_headers(ops),
    )
    by_id = {r["id"]: r for r in _rows(unfiltered)}
    assert by_id[str(never_registered.id)]["registered"] is False
    assert by_id[str(will_register.id)]["registered"] is True

    registered_only = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"registered_only": "true"}, headers=_headers(ops),
    )
    assert registered_only.status_code == 200, registered_only.text
    ids = {r["id"] for r in _rows(registered_only)}
    assert str(will_register.id) in ids
    assert str(never_registered.id) not in ids


@pytest.mark.asyncio
async def test_assignable_students_lms_status_filter(db, client):
    """`lms_status` reports/filters on this cohort's own LmsProgramAssignment
    — independent of team status, since assign-then-check-in on the
    checklist is a separate step from getting teamed up."""
    ops = await _ops(db)
    program, cohort = await _program_and_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Bring your kit",
    ))
    await db.flush()
    student = await _self_registered_student(db, full_name="Has Access After Assign")
    await db.commit()

    before = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"q": "Has Access After Assign"}, headers=_headers(ops),
    )
    row = next(r for r in _rows(before) if r["id"] == str(student.id))
    assert row["lms_access"] is False

    assign = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [{"user_id": str(student.id), "team_id": "T1"}]},
        headers=_headers(ops),
    )
    assert assign.status_code == 200, assign.text

    has_access = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"lms_status": "has_access"}, headers=_headers(ops),
    )
    assert str(student.id) in {r["id"] for r in _rows(has_access)}

    no_access = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"lms_status": "no_access"}, headers=_headers(ops),
    )
    assert str(student.id) not in {r["id"] for r in _rows(no_access)}


@pytest.mark.asyncio
async def test_assignable_students_honors_invite_code_filter(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    student = await _self_registered_student(db)
    student.invitation_code_used = "BATCH1"
    await db.commit()

    hit = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"invite_code": "BATCH1"},
        headers=_headers(ops),
    )
    assert hit.status_code == 200, hit.text
    assert str(student.id) in {r["id"] for r in _rows(hit)}

    miss = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"invite_code": "OTHERBATCH"},
        headers=_headers(ops),
    )
    assert miss.status_code == 200, miss.text
    assert str(student.id) not in {r["id"] for r in _rows(miss)}


@pytest.mark.asyncio
async def test_assignable_students_login_status_filter(db, client):
    """login_status (2026-09-16) reads User.last_login_at directly — account
    existing (self-registered here) says nothing about whether it's ever
    actually been opened."""
    from datetime import datetime, timezone

    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    never_logged_in = await _self_registered_student(db, full_name="Never Logged In Assignee")
    has_logged_in = await _self_registered_student(db, full_name="Has Logged In Assignee")
    has_logged_in.last_login_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    await db.commit()

    never = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"login_status": "never"}, headers=_headers(ops),
    )
    never_ids = {r["id"] for r in _rows(never)}
    assert str(never_logged_in.id) in never_ids
    assert str(has_logged_in.id) not in never_ids

    has = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"login_status": "has_logged_in"}, headers=_headers(ops),
    )
    has_ids = {r["id"] for r in _rows(has)}
    assert str(has_logged_in.id) in has_ids
    assert str(never_logged_in.id) not in has_ids


@pytest.mark.asyncio
async def test_assignable_students_a_large_batch_is_not_truncated_by_the_open_search_cap(db, client):
    """Found live (2026-09-15): with "Registered to this cohort" off, the
    platform-wide branch capped every query at 50 rows — including one
    already narrowed to a single invite-code batch, which is bounded on its
    own the same way a cohort roster is (_registered_cohort_users is fully
    uncapped for that same reason). A batch bigger than the cap silently lost
    members, and "All batches" (no invite_code) could end up showing *fewer*
    relevant people than one specific batch, since the unfiltered query
    burned its cap on unrelated platform students while a batch mostly
    didn't. The cap was then dropped entirely (not just for a selected
    batch) after the same symptom showed up again on the plain "no filter at
    all" case — an alphabetically-first slice of the whole platform is no
    more useful there than it was for one batch. This pins "querying past
    the old 50-row cap comes back whole" for both shapes so it regresses
    loudly if either cap comes back."""
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    batch_students = [
        await _self_registered_student(db, full_name=f"Batch Student {i:03d}") for i in range(55)
    ]
    for s in batch_students:
        s.invitation_code_used = "BIGBATCH"
    other_students = [
        await _self_registered_student(db, full_name=f"Zzz Other Student {i:03d}") for i in range(10)
    ]
    await db.commit()

    by_batch = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"invite_code": "BIGBATCH", "registered_only": "false", "page_size": 100},
        headers=_headers(ops),
    )
    assert by_batch.status_code == 200, by_batch.text
    assert by_batch.json()["total"] == 55
    batch_ids = {r["id"] for r in _rows(by_batch)}
    assert len(batch_ids) == 55
    assert {str(s.id) for s in batch_students} <= batch_ids

    unfiltered = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"registered_only": "false", "page_size": 100},
        headers=_headers(ops),
    )
    assert unfiltered.status_code == 200, unfiltered.text
    all_ids = {r["id"] for r in _rows(unfiltered)}
    assert {str(s.id) for s in batch_students} <= all_ids
    assert {str(s.id) for s in other_students} <= all_ids


@pytest.mark.asyncio
async def test_assign_students_registers_and_teams_up_self_registered_students(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    a = await _self_registered_student(db, full_name="Amir Salem")
    b = await _self_registered_student(db, full_name="Lina Nasser")
    await db.commit()

    resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [
            {"user_id": str(a.id), "team_id": "T1"},
            {"user_id": str(b.id), "team_id": "T1"},
        ]},
        headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"] == {"total": 2, "created": 2, "matched": 0, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1
    assert teams[0].name == "T1"  # unnamed placeholder — student names it later
    members = await team_member_ids(db, team_id=teams[0].id)
    assert {a.id, b.id} <= set(members)


@pytest.mark.asyncio
async def test_assign_students_is_idempotent_and_reports_matched_on_repeat(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    student = await _self_registered_student(db)
    await db.commit()

    first = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [{"user_id": str(student.id), "team_id": "T1"}]},
        headers=_headers(ops),
    )
    assert first.json()["summary"] == {"total": 1, "created": 1, "matched": 0, "error": 0}

    second = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [{"user_id": str(student.id), "team_id": "T1"}]},
        headers=_headers(ops),
    )
    assert second.status_code == 200, second.text
    assert second.json()["summary"] == {"total": 1, "created": 0, "matched": 1, "error": 0}

    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort.id))).scalars().all()
    assert len(teams) == 1


@pytest.mark.asyncio
async def test_assign_students_flags_an_unknown_user_id_without_failing_the_batch(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    real = await _self_registered_student(db)
    await db.commit()

    resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [
            {"user_id": str(uuid.uuid4()), "team_id": "T1"},
            {"user_id": str(real.id), "team_id": "T1"},
        ]},
        headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"] == {"total": 2, "created": 1, "matched": 0, "error": 1}
    error_row = next(r for r in body["rows"] if r["disposition"] == "error")
    assert "not found" in error_row["reason"].lower()


@pytest.mark.asyncio
async def test_assign_students_enqueues_a_ticket_email_only_for_newly_registered_rows(db, arq_client, arq_redis):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    a = await _self_registered_student(db)
    b = await _self_registered_student(db)
    await db.commit()

    # b is already registered+teamed before this call, so re-assigning them
    # (even to a different team) must not re-fire a ticket job — only a's
    # row is genuinely new.
    first = await arq_client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [{"user_id": str(b.id), "team_id": "T1"}]},
        headers=_headers(ops),
    )
    assert first.status_code == 200, first.text

    resp = await arq_client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [
            {"user_id": str(a.id), "team_id": "T2"},
            {"user_id": str(b.id), "team_id": "T2"},
        ]},
        headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["summary"] == {"total": 2, "created": 1, "matched": 1, "error": 0}

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 2  # one for b's first assign, one for a's


@pytest.mark.asyncio
async def test_judge_score_with_timing_adjustment_and_comments(db, client):
    ops, program, cohort, team, judge, _poster = await _judge_setup(db)
    resp = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={
            "criterion_scores": {"design": 28.5, "execution": 19.5},
            "criterion_comments": {"design": "Impressive CAD design", "execution": "Solid presentation"},
            "bonus_points": 2.0,
            "timing_adjustment": -1.5,
            "notes": "Late submission by 2 hours",
            "submitted": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_points"] == 48.5
    assert data["timing_adjustment"] == -1.5
    assert data["notes"] == "Late submission by 2 hours"
    assert data["criterion_comments"]["design"] == "Impressive CAD design"


@pytest.mark.asyncio
async def test_student_result_view_only_shows_own_team_once_published(db, client):
    ops, program, cohort, team, judge, _poster = await _judge_setup(db)
    student = await _student(db)
    from app.models.team import TeamMember
    db.add(TeamMember(team_id=team.id, user_id=student.id))
    await db.commit()

    # Before publishing: returns unpublished status
    pre_pub = await client.get(
        f"/competitions/student/cohorts/{cohort.id}/my-result",
        headers=_headers(student),
    )
    assert pre_pub.status_code == 200, pre_pub.text
    assert pre_pub.json()["published"] is False
    assert pre_pub.json()["status"] == "pending_publication"
    assert pre_pub.json()["final_score"] is None
    assert pre_pub.json()["qualification"] is None

    # Judge scores team (rubric max is 50 for design + execution, let's score 25 and 20)
    await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"design": 25.0, "execution": 20.0}, "bonus_points": 0, "submitted": True},
    )

    # Set team qualification status
    team.qualification = "Qualified"
    await db.commit()

    # Ops publishes
    pub = await client.post(f"/competitions/admin/cohorts/{cohort.id}/publish", headers=_headers(ops))
    assert pub.status_code == 200, pub.text

    # Student fetches result
    post_pub = await client.get(
        f"/competitions/student/cohorts/{cohort.id}/my-result",
        headers=_headers(student),
    )
    assert post_pub.status_code == 200, post_pub.text
    res = post_pub.json()
    assert res["published"] is True
    assert res["status"] == "scored"
    assert res["final_score"] == 45.0
    assert res["qualification"] == "Qualified"
    assert "judge_scores" not in res
    assert "judges" not in res

    # Unaffiliated student gets 404
    other_student = await _student(db)
    await db.commit()
    other_resp = await client.get(
        f"/competitions/student/cohorts/{cohort.id}/my-result",
        headers=_headers(other_student),
    )
    assert other_resp.status_code == 404


# ── Sub-criteria + operations-graded criteria (2026-09-30) ────────────────

SUB_RUBRIC = [
    {
        "key": "mission", "label": "Mission", "max_points": 15,
        "sub_criteria": [
            {"key": "clarity", "label": "Clarity", "max_points": 5},
            {"key": "implementation", "label": "Implementation", "max_points": 5},
            {"key": "creativity", "label": "Creativity", "max_points": 5},
        ],
    },
    {"key": "teamwork", "label": "Teamwork", "max_points": 10},
    {"key": "attendance", "label": "Attendance", "max_points": 40, "scored_by": "operations"},
]


@pytest.mark.asyncio
async def test_rubric_rejects_sub_criteria_whose_sum_mismatches_parent(db, client):
    ops = await _ops(db)
    program, _cohort = await _program_and_cohort(db)
    await db.commit()

    bad = await client.put(
        f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(ops),
        json={"name": "Bad", "criteria": [
            {"key": "mission", "label": "Mission", "max_points": 15,
             "sub_criteria": [
                 {"key": "clarity", "label": "Clarity", "max_points": 5},
                 {"key": "implementation", "label": "Implementation", "max_points": 5},
             ]},
        ]},
    )
    assert bad.status_code == http_status.HTTP_400_BAD_REQUEST

    good = await client.put(
        f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(ops),
        json={"name": "Good", "criteria": SUB_RUBRIC},
    )
    assert good.status_code == 200, good.text
    mission = next(c for c in good.json()["criteria"] if c["key"] == "mission")
    assert [s["key"] for s in mission["sub_criteria"]] == ["clarity", "implementation", "creativity"]
    assert next(c for c in good.json()["criteria"] if c["key"] == "attendance")["scored_by"] == "operations"


@pytest.mark.asyncio
async def test_judge_scores_sub_criteria_and_parent_auto_totals(db, client):
    ops, program, cohort, team, judge, _poster = await _judge_setup(db)
    seed = await client.put(
        f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(ops),
        json={"name": "Subs", "criteria": SUB_RUBRIC},
    )
    assert seed.status_code == 200, seed.text

    # A bare parent key is not an accepted leaf — judges score the subs.
    parent_key = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {"mission": 12, "teamwork": 8}},
    )
    assert parent_key.status_code == http_status.HTTP_400_BAD_REQUEST

    # Operations-graded keys are rejected on the judge surface too.
    with_ops = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {
            "mission.clarity": 4, "mission.implementation": 5, "mission.creativity": 3,
            "teamwork": 8, "attendance": 40,
        }, "submitted": True},
    )
    assert with_ops.status_code == http_status.HTTP_400_BAD_REQUEST

    ok = await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {
            "mission.clarity": 4, "mission.implementation": 5, "mission.creativity": 3,
            "teamwork": 8,
        }, "submitted": True},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["total_points"] == 20  # mission auto-totals 12 + teamwork 8
    assert body["criterion_scores"]["mission"] == 12  # stored parent total
    assert body["criterion_scores"]["mission.clarity"] == 4

    detail = await client.get(f"/competitions/judge/teams/{team.id}", headers=_headers(judge))
    mission = next(c for c in detail.json()["rubric"]["criteria"] if c["key"] == "mission")
    assert mission["scored_by"] == "judge"
    assert [s["key"] for s in mission["sub_criteria"]] == ["clarity", "implementation", "creativity"]

    breakdown = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/teams/{team.id}/score-breakdown", headers=_headers(ops),
    )
    assert breakdown.status_code == 200
    row = next(j for j in breakdown.json()["judges"])
    mission_row = next(c for c in row["criteria"] if c["key"] == "mission")
    assert mission_row["awarded_points"] == 12
    assert [(s["key"], s["awarded_points"]) for s in mission_row["subs"]] == [
        ("clarity", 4), ("implementation", 5), ("creativity", 3),
    ]


@pytest.mark.asyncio
async def test_operations_scores_a_team_and_leaderboard_combines(db, client):
    ops, program, cohort, team, judge, _poster = await _judge_setup(db)
    seed = await client.put(
        f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(ops),
        json={"name": "Subs", "criteria": SUB_RUBRIC},
    )
    assert seed.status_code == 200, seed.text

    await client.put(
        f"/competitions/judge/teams/{team.id}/score", headers=_headers(judge),
        json={"criterion_scores": {
            "mission.clarity": 4, "mission.implementation": 5, "mission.creativity": 3,
            "teamwork": 8,
        }, "submitted": True},
    )

    # Flat operations criterion, partial submit allowed.
    scored = await client.put(
        f"/competitions/admin/cohorts/{cohort.id}/teams/{team.id}/ops-score", headers=_headers(ops),
        json={"criterion_scores": {"attendance": 38}, "notes": "Great turnout"},
    )
    assert scored.status_code == 200, scored.text
    assert scored.json()["ops_criterion_scores"]["attendance"] == 38

    board = await client.get(f"/competitions/admin/cohorts/{cohort.id}/leaderboard", headers=_headers(ops))
    row = next(r for r in board.json() if r["team_id"] == str(team.id))
    assert row["ops_score"] == 38
    assert row["ops_max_points"] == 40
    assert row["score"] == 58.0  # judge avg 20 + operations 38

    breakdown = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/teams/{team.id}/score-breakdown", headers=_headers(ops),
    )
    assert breakdown.json()["ops_score"] == 38
    assert breakdown.json()["ops_criterion_notes"] == "Great turnout"

    # Judge keys are refused on the operations endpoint.
    bad = await client.put(
        f"/competitions/admin/cohorts/{cohort.id}/teams/{team.id}/ops-score", headers=_headers(ops),
        json={"criterion_scores": {"teamwork": 5}},
    )
    assert bad.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_operations_sub_criteria_require_all_leaves(db, client):
    ops, program, cohort, team, _judge, _poster = await _judge_setup(db)
    seed = await client.put(
        f"/competitions/admin/programs/{program.id}/rubric", headers=_headers(ops),
        json={"name": "Ops subs", "criteria": [
            {"key": "mission", "label": "Mission", "max_points": 15, "scored_by": "operations",
             "sub_criteria": [
                 {"key": "clarity", "label": "Clarity", "max_points": 5},
                 {"key": "implementation", "label": "Implementation", "max_points": 5},
                 {"key": "creativity", "label": "Creativity", "max_points": 5},
             ]},
        ]},
    )
    assert seed.status_code == 200, seed.text

    partial = await client.put(
        f"/competitions/admin/cohorts/{cohort.id}/teams/{team.id}/ops-score", headers=_headers(ops),
        json={"criterion_scores": {"mission.clarity": 5}},
    )
    assert partial.status_code == http_status.HTTP_400_BAD_REQUEST

    full = await client.put(
        f"/competitions/admin/cohorts/{cohort.id}/teams/{team.id}/ops-score", headers=_headers(ops),
        json={"criterion_scores": {
            "mission.clarity": 5, "mission.implementation": 4, "mission.creativity": 3,
        }},
    )
    assert full.status_code == 200, full.text
    assert full.json()["ops_criterion_scores"]["mission"] == 12

    board = await client.get(f"/competitions/admin/cohorts/{cohort.id}/leaderboard", headers=_headers(ops))
    row = next(r for r in board.json() if r["team_id"] == str(team.id))
    assert row["score"] == 12.0  # no judge scores yet — operations alone still ranks
    assert row["status"] == "scored"


# ── Assign rebuild (2026-10): staff mode, pagination, register-users,
# single-team move, observer auto-role ────────────────────────────────

async def _staff_user(db, *, roles, full_name="Staff Member"):
    user = User(
        id=uuid.uuid4(), full_name=full_name, email=f"{full_name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=list(roles), status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_assignable_staff_mode_lists_non_students_with_card_and_roles(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    instructor = await _staff_user(db, roles=["instructor"], full_name="Staff Instructor")
    intern = await _staff_user(db, roles=["intern"], full_name="Staff Intern")
    student = await _self_registered_student(db, full_name="Plain Student")
    await db.commit()

    resp = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "staff", "page_size": 100}, headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 2
    by_id = {r["id"]: r for r in body["items"]}
    assert str(instructor.id) in by_id and str(intern.id) in by_id
    assert str(student.id) not in by_id
    row = by_id[str(instructor.id)]
    assert "instructor" in row["roles"]
    assert row["is_observer"] is False
    assert row["registered"] is False

    narrowed = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "staff", "role": "intern", "page_size": 100}, headers=_headers(ops),
    )
    ids = {r["id"] for r in _rows(narrowed)}
    assert str(intern.id) in ids
    assert str(instructor.id) not in ids


@pytest.mark.asyncio
async def test_assignable_pagination_and_card_sort(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    for i in range(5):
        await _self_registered_student(db, full_name=f"Paged Student {i:02d}")
    await db.commit()

    p1 = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"page": 1, "page_size": 2, "sort": "full_name", "direction": "asc"},
        headers=_headers(ops),
    )
    assert p1.status_code == 200, p1.text
    b1 = p1.json()
    assert b1["page"] == 1 and b1["page_size"] == 2
    assert b1["total"] >= 5 and len(b1["items"]) == 2

    p2 = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"page": 2, "page_size": 2, "sort": "full_name", "direction": "asc"},
        headers=_headers(ops),
    )
    ids1 = {r["id"] for r in _rows(p1)}
    ids2 = {r["id"] for r in _rows(p2)}
    assert not ids1 & ids2

    cards = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"sort": "card_number", "page_size": 100}, headers=_headers(ops),
    )
    assert cards.status_code == 200, cards.text
    assert "card_id" in _rows(cards)[0]


@pytest.mark.asyncio
async def test_register_users_adds_to_program_without_team(db, client):
    from app.models.sessions.registration import Registration

    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    student = await _self_registered_student(db)
    instructor = await _staff_user(db, roles=["instructor"], full_name="Observe Me")
    await db.commit()

    resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/register-users",
        json={"user_ids": [str(student.id), str(instructor.id)]},
        headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["summary"] == {"total": 2, "created": 2, "matched": 0, "error": 0}

    regs = (await db.execute(
        select(Registration).where(Registration.cohort_id == cohort.id)
    )).scalars().all()
    assert len(regs) == 2

    # Staff account gained the observer role + shows under observers.
    await db.refresh(instructor)
    assert "observer" in instructor.role_values
    obs = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/assignable-students",
        params={"mode": "observer", "page_size": 100}, headers=_headers(ops),
    )
    assert str(instructor.id) in {r["id"] for r in _rows(obs)}

    # Idempotent re-add reports matched.
    again = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/register-users",
        json={"user_ids": [str(student.id)]}, headers=_headers(ops),
    )
    assert again.json()["summary"] == {"total": 1, "created": 0, "matched": 1, "error": 0}


@pytest.mark.asyncio
async def test_register_users_auto_creates_contact(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    lonely = User(
        id=uuid.uuid4(), full_name="No Contact", email=f"nocontact-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["instructor"], status="active", contact_id=None,
    )
    db.add(lonely)
    await db.commit()

    resp = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/register-users",
        json={"user_ids": [str(lonely.id)]}, headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["summary"]["created"] == 1
    await db.refresh(lonely)
    assert lonely.contact_id is not None


@pytest.mark.asyncio
async def test_assign_moves_user_to_single_team(db, client):
    from app.models.team import TeamMember

    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    student = await _self_registered_student(db)
    await db.commit()

    first = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [{"user_id": str(student.id), "team_id": "T1"}]},
        headers=_headers(ops),
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/competitions/admin/cohorts/{cohort.id}/assign-students",
        json={"rows": [{"user_id": str(student.id), "team_id": "T2"}]},
        headers=_headers(ops),
    )
    assert second.status_code == 200, second.text

    memberships = (await db.execute(
        select(TeamMember.team_id)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.cohort_id == cohort.id, TeamMember.user_id == student.id)
    )).scalars().all()
    assert len(memberships) == 1


@pytest.mark.asyncio
async def test_add_member_to_observer_team_grants_observer_role_and_moves(db, client):
    from app.models.team import TeamMember
    from app.services.competitions.team_management import create_empty_team

    ops = await _ops(db)
    _program, cohort = await _program_and_cohort(db)
    instructor = await _staff_user(db, roles=["instructor"], full_name="Team Observer")
    student = await _self_registered_student(db)
    await db.commit()

    team_a = await create_empty_team(db, cohort_id=cohort.id, name="Obs A", created_by=ops.id, is_observer=True)
    team_b = await create_empty_team(db, cohort_id=cohort.id, name="Obs B", created_by=ops.id, is_observer=True)
    assert team_a.roster_team_id == "Obs A"
    await db.commit()

    add = await client.post(
        f"/competitions/admin/teams/{team_a.id}/members",
        json={"user_id": str(instructor.id)}, headers=_headers(ops),
    )
    assert add.status_code in (200, 201), add.text
    await db.refresh(instructor)
    assert "observer" in instructor.role_values

    move = await client.post(
        f"/competitions/admin/teams/{team_b.id}/members",
        json={"user_id": str(instructor.id)}, headers=_headers(ops),
    )
    assert move.status_code in (200, 201), move.text
    memberships = (await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == instructor.id)
    )).scalars().all()
    assert memberships == [team_b.id]

    # Partition still enforced: student onto observer team is rejected.
    bad = await client.post(
        f"/competitions/admin/teams/{team_a.id}/members",
        json={"user_id": str(student.id)}, headers=_headers(ops),
    )
    assert bad.status_code == 400
