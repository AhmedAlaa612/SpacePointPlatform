"""LMS Program checklist — Staff Sandbox & Live Student Preview System tests.

Covers:
- POST /lms/admin/preview-assignment (get or create test assignment)
- Identical student view GET /lms/programs/{assignment_id} with is_test=True
- Staff taking student actions: complete self-check, submit deliverable URL
- Gating unlock behavior in sandbox mode
- POST /lms/admin/preview-assignment/{assignment_id}/reset (progress reset)
- Staff test row visibility in cohort program roster
- Competitions judge isolation (external judges do not see test teams)
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.team import Team
from app.models.user import User


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops_user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Preview Tester", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _judge_user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Competition Judge", email=f"judge-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["judge"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _program_with_items(db, *, author) -> tuple[Program, Cohort, LmsProgram, list[LmsProgramItem]]:
    program = Program(
        id=uuid.uuid4(), code=f"SBX-{uuid.uuid4().hex[:8]}", name="Sandbox Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()

    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Sandbox Cohort Alpha", status="running")
    db.add(cohort)
    await db.flush()

    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Sandbox Checklist")
    db.add(lms_program)
    await db.flush()

    item1 = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Step 1: Read the Welcome Guide",
    )
    item2 = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="submission", title="Step 2: Submit Project URL", gated=True,
        submission_prompt="Paste your GitHub link",
    )
    item3 = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=3,
        item_type="manual", title="Step 3: Final Reflection", gated=True,
    )
    db.add_all([item1, item2, item3])
    await db.flush()
    return program, cohort, lms_program, [item1, item2, item3]


@pytest.mark.asyncio
async def test_create_preview_assignment_and_take_student_actions(client, db):
    ops = await _ops_user(db)
    _prog, cohort, lms_program, items = await _program_with_items(db, author=ops)

    # 1. Create preview assignment via admin endpoint
    res = await client.post(
        "/lms/admin/preview-assignment",
        headers=_headers(ops),
        json={"lms_program_id": str(lms_program.id), "cohort_id": str(cohort.id)},
    )
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assignment_id = data["assignment_id"]
    assert data["is_test"] is True
    assert data["cohort_id"] == str(cohort.id)

    # 2. Re-calling endpoint is idempotent
    res2 = await client.post(
        "/lms/admin/preview-assignment",
        headers=_headers(ops),
        json={"lms_program_id": str(lms_program.id), "cohort_id": str(cohort.id)},
    )
    assert res2.json()["assignment_id"] == assignment_id

    # 3. View identical student checklist
    chk_res = await client.get(f"/lms/programs/{assignment_id}", headers=_headers(ops))
    assert chk_res.status_code == http_status.HTTP_200_OK
    chk_data = chk_res.json()
    assert chk_data["is_test"] is True
    assert len(chk_data["items"]) == 3
    assert chk_data["items"][0]["status"] == "pending"
    assert chk_data["items"][0]["locked"] is False
    assert chk_data["items"][1]["locked"] is True  # gated item is locked

    # 4. Ops executes student action: complete step 1
    comp_res = await client.post(
        f"/lms/programs/{assignment_id}/items/{items[0].id}/complete",
        headers=_headers(ops),
        json={},
    )
    assert comp_res.status_code == http_status.HTTP_200_OK
    assert comp_res.json()["status"] == "done"

    # 5. Check checklist again: step 2 is now unlocked!
    chk_res2 = await client.get(f"/lms/programs/{assignment_id}", headers=_headers(ops))
    chk_data2 = chk_res2.json()
    assert chk_data2["items"][0]["status"] == "done"
    assert chk_data2["items"][1]["locked"] is False  # now unlocked

    # 6. Ops executes submit deliverable on step 2
    sub_res = await client.post(
        f"/lms/programs/{assignment_id}/items/{items[1].id}/submit",
        headers=_headers(ops),
        json={"url": "https://github.com/spacepoint/test-project"},
    )
    assert sub_res.status_code == http_status.HTTP_200_OK
    assert sub_res.json()["status"] == "done"
    assert sub_res.json()["submitted_url"] == "https://github.com/spacepoint/test-project"

    # 7. Check cohort roster: staff test row appears with is_test: True
    roster_res = await client.get(
        f"/lms/instructor/cohorts/{cohort.id}/program-progress",
        headers=_headers(ops),
    )
    assert roster_res.status_code == http_status.HTTP_200_OK
    roster_rows = roster_res.json()
    test_row = next((r for r in roster_rows if r["assignment_id"] == assignment_id), None)
    assert test_row is not None
    assert test_row["is_test"] is True
    assert test_row["items_done"] == 2

    # 8. Reset sandbox progress
    reset_res = await client.post(
        f"/lms/admin/preview-assignment/{assignment_id}/reset",
        headers=_headers(ops),
    )
    assert reset_res.status_code == http_status.HTTP_200_OK

    # 9. Verify checklist is reset back to step 1
    chk_res3 = await client.get(f"/lms/programs/{assignment_id}", headers=_headers(ops))
    chk_data3 = chk_res3.json()
    assert chk_data3["items"][0]["status"] == "pending"
    assert chk_data3["items"][1]["status"] == "pending"
    assert chk_data3["items"][1]["locked"] is True  # relocked after reset

    # 10. Delete preview assignment
    del_res = await client.delete(
        f"/lms/admin/preview-assignment/{assignment_id}",
        headers=_headers(ops),
    )
    assert del_res.status_code == http_status.HTTP_200_OK
    chk_res4 = await client.get(f"/lms/programs/{assignment_id}", headers=_headers(ops))
    assert chk_res4.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_preview_assignment_without_cohort(client, db):
    ops = await _ops_user(db)
    _prog, _cohort, lms_program, _items = await _program_with_items(db, author=ops)

    # Create standalone preview without cohort
    res = await client.post(
        "/lms/admin/preview-assignment",
        headers=_headers(ops),
        json={"lms_program_id": str(lms_program.id), "cohort_id": None},
    )
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assert data["cohort_id"] is None
    assert data["is_test"] is True

    # View checklist
    chk_res = await client.get(f"/lms/programs/{data['assignment_id']}", headers=_headers(ops))
    assert chk_res.status_code == http_status.HTTP_200_OK
    assert len(chk_res.json()["items"]) == 3


@pytest.mark.asyncio
async def test_judge_isolation_excludes_test_teams_by_default(client, db):
    ops = await _ops_user(db)
    judge = await _judge_user(db)
    _prog, cohort, _lms_program, _items = await _program_with_items(db, author=ops)

    # Assign judge to cohort
    from app.models.competitions.judging import CompetitionJudge
    db.add(CompetitionJudge(id=uuid.uuid4(), cohort_id=cohort.id, user_id=judge.id))

    # Add 1 real team and 1 test team
    real_team = Team(id=uuid.uuid4(), name="Real Team Alpha", cohort_id=cohort.id, is_test=False)
    test_team = Team(id=uuid.uuid4(), name="Staff Test Team", cohort_id=cohort.id, is_test=True)
    db.add_all([real_team, test_team])
    await db.flush()

    # External judge fetches teams: test team must NOT be visible
    judge_res = await client.get(f"/competitions/judge/teams?cohort_id={cohort.id}", headers=_headers(judge))
    assert judge_res.status_code == http_status.HTTP_200_OK
    judge_teams = judge_res.json()
    team_ids = [t["id"] for t in judge_teams]
    assert str(real_team.id) in team_ids
    assert str(test_team.id) not in team_ids

    # Admin caller with include_test=True can see test team
    admin = User(
        id=uuid.uuid4(), full_name="Admin Judge Tester", email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["admin"], status="active",
    )
    db.add(admin)
    await db.flush()
    db.add(CompetitionJudge(id=uuid.uuid4(), cohort_id=cohort.id, user_id=admin.id))
    await db.flush()

    admin_res = await client.get(
        f"/competitions/judge/teams?cohort_id={cohort.id}&include_test=true",
        headers=_headers(admin),
    )
    assert admin_res.status_code == http_status.HTTP_200_OK
    admin_team_ids = [t["id"] for t in admin_res.json()]
    assert str(real_team.id) in admin_team_ids
    assert str(test_team.id) in admin_team_ids
