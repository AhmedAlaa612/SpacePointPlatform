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
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.team import Team
from app.models.user import User
from app.services.teams import create_team

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
    sheet.append(["team_name", "member_name", "email", "phone", "school"])
    sheet.append(["Falcon Eye", "Amir Salem", f"amir-{uuid.uuid4().hex[:6]}@example.com", "", ""])
    sheet.append(["Falcon Eye", "Lina Nasser", f"lina-{uuid.uuid4().hex[:6]}@example.com", "", ""])
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
    sheet.append(["team_name", "member_name", "email", "phone", "school"])
    sheet.append(["Falcon Eye", "Amir Salem", "456", "", ""])  # shifted-column garbage, the prod incident shape
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
    sheet.append(["team_name", "member_name", "email", "phone", "school"])
    sheet.append(["Falcon Eye", "Amir Salem", f"amir-{uuid.uuid4().hex[:6]}@example.com", "", ""])
    sheet.append(["Falcon Eye", "Lina Nasser", f"lina-{uuid.uuid4().hex[:6]}@example.com", "", ""])
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
    sheet.append(["team_name", "member_name", "email", "phone", "school"])
    sheet.append(["Falcon Eye", "Amir Salem", dup_email, "", ""])
    sheet.append(["Falcon Eye", "Amir Salem", dup_email, "", ""])
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
    sheet.append(["team_name", "member_name", "email", "phone", "school"])
    sheet.append(["Silent Comet", "Zaid Omar", f"zaid-{uuid.uuid4().hex[:6]}@example.com", "", ""])
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

    row = {"row_number": 2, "team_name": "Falcon Eye", "member_name": "", "email": "amir@example.com", "phone": None, "school": None}
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
