"""LMS Program checklist authoring (2026-08-21 redesign) —
`/lms/admin/programs/*` and `/lms/admin/cohorts/{cohort_id}/program-override/*`.
Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms.course import Course
from app.models.missions.mission import Mission, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Checklist Admin", email=f"cka-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _program(db) -> Program:
    program = Program(
        id=uuid.uuid4(), code=f"CKA-{uuid.uuid4().hex[:8]}", name="Checklist Admin Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    return program


async def _cohort(db, program: Program) -> Cohort:
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Checklist Admin Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


async def _course(db, *, author) -> Course:
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:6]}", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    return course


async def _mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Admin Test Mission", slug=f"admin-test-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy="solo",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Cadet", position=1, points=10)
    db.add(variant)
    await db.flush()
    return mission, variant


# ── program CRUD ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_get_update_delete_lms_program(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()

    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops),
        json={"program_id": str(program.id), "name": "TDRA Summer Sprint", "description": "A sprint."},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "TDRA Summer Sprint" and body["certificate_required"] is True and body["items"] == []
    lms_program_id = body["id"]

    dup = await client.post(
        "/lms/admin/programs", headers=_headers(ops),
        json={"program_id": str(program.id), "name": "Second Checklist For Same Program"},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT

    got = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert got.status_code == 200 and got.json()["name"] == "TDRA Summer Sprint"

    updated = await client.patch(
        f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops),
        json={"certificate_required": False},
    )
    assert updated.status_code == 200
    assert updated.json()["certificate_required"] is False
    assert updated.json()["name"] == "TDRA Summer Sprint"  # untouched field survives a partial patch

    deleted = await client.delete(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert deleted.status_code == 204
    gone = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_upload_program_image_sets_image_url(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )).json()["id"]

    get_before = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert get_before.json()["image_url"] is None

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/image", headers=_headers(ops),
        files={"file": ("cover.jpg", b"\xff\xd8\xff\xe0fakejpegbytes", "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["image_url"] is not None

    get_after = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert get_after.json()["image_url"] is not None


@pytest.mark.asyncio
async def test_upload_program_image_rejects_empty_file(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )).json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/image", headers=_headers(ops),
        files={"file": ("cover.jpg", b"", "image/jpeg")},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_student_cannot_create_a_program(db, client):
    student = await _user(db, roles=["student"])
    await db.commit()
    resp = await client.post("/lms/admin/programs", headers=_headers(student), json={"name": "Nope"})
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


# ── item CRUD + validation ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_items_of_every_type_in_order(db, client):
    ops = await _user(db)
    program = await _program(db)
    course = await _course(db, author=ops)
    mission, variant = await _mission(db, author=ops)
    await db.commit()

    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Full Checklist"},
    )
    lms_program_id = created.json()["id"]

    course_item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": course.title, "course_id": str(course.id)},
    )
    assert course_item.status_code == 201 and course_item.json()["position"] == 1

    mission_item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={
            "item_type": "mission_run", "title": mission.title,
            "mission_id": str(mission.id), "variant_id": str(variant.id),
        },
    )
    assert mission_item.status_code == 201 and mission_item.json()["position"] == 2

    manual_item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "Attend the ceremony", "requires_confirmation": True},
    )
    assert manual_item.status_code == 201 and manual_item.json()["position"] == 3

    listed = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert [i["item_type"] for i in listed.json()["items"]] == ["course", "mission_run", "manual"]


@pytest.mark.asyncio
async def test_add_session_item_with_all_fields(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )).json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={
            "item_type": "session", "title": "Kickoff call",
            "session_date": "2026-09-15", "session_starts_at": "17:00:00",
            "session_location": "Building 4, Room 210", "session_meeting_url": "https://meet.example.com/kickoff",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["session_date"] == "2026-09-15"
    assert body["session_starts_at"] == "17:00:00"
    assert body["session_location"] == "Building 4, Room 210"
    assert body["session_meeting_url"] == "https://meet.example.com/kickoff"


@pytest.mark.asyncio
async def test_add_session_item_with_no_fields_succeeds(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )).json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "session", "title": "Placeholder session"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["session_date"] is None


@pytest.mark.asyncio
async def test_session_item_cannot_be_team_scoped(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )).json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "session", "title": "Kickoff call", "scope": "team"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_add_submission_item_with_deadline(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )).json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={
            "item_type": "submission", "title": "Final poster", "submission_prompt": "Paste your link",
            "deadline_at": "2026-09-15T17:00:00Z",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["deadline_at"] is not None


@pytest.mark.asyncio
async def test_deadline_rejected_on_a_non_submission_item(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )).json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "Attend", "deadline_at": "2026-09-15T17:00:00Z"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_add_item_rejects_a_missing_required_field(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )
    lms_program_id = created.json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": "No course_id"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_add_item_rejects_an_unknown_course(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )
    lms_program_id = created.json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": "Ghost course", "course_id": str(uuid.uuid4())},
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_add_item_rejects_a_duplicate_course_and_a_taken_position(db, client):
    ops = await _user(db)
    program = await _program(db)
    course = await _course(db, author=ops)
    other_course = await _course(db, author=ops)
    await db.commit()
    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )
    lms_program_id = created.json()["id"]
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": course.title, "course_id": str(course.id)},
    )

    dup_course = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": course.title, "course_id": str(course.id)},
    )
    assert dup_course.status_code == http_status.HTTP_409_CONFLICT

    taken_position = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": other_course.title, "course_id": str(other_course.id), "position": 1},
    )
    assert taken_position.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_a_submission_items_scope_is_locked_after_creation(db, client):
    """Individual vs. team is picked once, at creation — flipping it later
    (2026-08-29 incident) silently orphans anything already submitted,
    since the two scopes read/write entirely separate progress tables.
    Editing anything else on the same item is still fine."""
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )).json()["id"]
    item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "submission", "title": "Poster", "submission_prompt": "Paste your link", "scope": "individual"},
    )
    item_id = item.json()["id"]

    flipped = await client.patch(
        f"/lms/admin/programs/{lms_program_id}/items/{item_id}", headers=_headers(ops),
        json={"item_type": "submission", "title": "Poster", "submission_prompt": "Paste your link", "scope": "team"},
    )
    assert flipped.status_code == http_status.HTTP_400_BAD_REQUEST

    renamed = await client.patch(
        f"/lms/admin/programs/{lms_program_id}/items/{item_id}", headers=_headers(ops),
        json={"item_type": "submission", "title": "Poster (renamed)", "submission_prompt": "Paste your link", "scope": "individual"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Poster (renamed)"
    assert renamed.json()["scope"] == "individual"


@pytest.mark.asyncio
async def test_delete_item_removes_it(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )
    lms_program_id = created.json()["id"]
    item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "Check-off"},
    )
    item_id = item.json()["id"]

    deleted = await client.delete(f"/lms/admin/programs/{lms_program_id}/items/{item_id}", headers=_headers(ops))
    assert deleted.status_code == 204
    listed = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert listed.json()["items"] == []


# ── cohort override ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cohort_override_requires_a_program_checklist_to_override(db, client):
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "Nope"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_cohort_override_created_on_first_item_and_lists_separately(db, client):
    """Fork-on-write (operator ask, 2026-08-22): a cohort with no override
    yet shows the program's own checklist as an editable, `is_inherited`
    starting point — never a 404 — and the first real edit forks a copy of
    it into the cohort's own override rather than replacing it outright."""
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    program_course = await _course(db, author=ops)
    override_course = await _course(db, author=ops)
    await db.commit()

    program_checklist = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base Checklist"},
    )
    lms_program_id = program_checklist.json()["id"]
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": program_course.title, "course_id": str(program_course.id)},
    )

    inherited = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert inherited.status_code == 200
    assert inherited.json()["is_inherited"] is True
    assert [i["course_id"] for i in inherited.json()["items"]] == [str(program_course.id)]

    added = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items", headers=_headers(ops),
        json={"item_type": "course", "title": override_course.title, "course_id": str(override_course.id)},
    )
    assert added.status_code == 201

    override = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert override.status_code == 200
    assert override.json()["is_inherited"] is False
    # The forked copy of the program's course, plus the newly added one.
    assert {i["course_id"] for i in override.json()["items"]} == {str(program_course.id), str(override_course.id)}

    # The program-level checklist itself is untouched by the fork.
    program_after = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert [i["course_id"] for i in program_after.json()["items"]] == [str(program_course.id)]


@pytest.mark.asyncio
async def test_fork_cohort_override_copies_deadline_and_session_fields(db, client):
    """Regression guard: fork_cohort_override's copy constructor must carry
    the new deadline/session_* columns, or forking a cohort override
    silently drops that data."""
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    await db.commit()

    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base"},
    )).json()["id"]
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={
            "item_type": "submission", "title": "Poster", "submission_prompt": "Paste your link",
            "deadline_at": "2026-09-15T17:00:00Z",
        },
    )
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={
            "item_type": "session", "title": "Kickoff call",
            "session_date": "2026-09-15", "session_starts_at": "17:00:00",
            "session_location": "Building 4, Room 210", "session_meeting_url": "https://meet.example.com/kickoff",
        },
    )

    # Triggers fork_cohort_override via the first cohort-override write.
    await client.post(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "Extra step"},
    )

    override = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    items_by_type = {i["item_type"]: i for i in override.json()["items"]}
    assert items_by_type["submission"]["deadline_at"] is not None
    assert items_by_type["session"]["session_date"] == "2026-09-15"
    assert items_by_type["session"]["session_starts_at"] == "17:00:00"
    assert items_by_type["session"]["session_location"] == "Building 4, Room 210"
    assert items_by_type["session"]["session_meeting_url"] == "https://meet.example.com/kickoff"


async def test_editing_an_inherited_item_by_its_program_item_id_forks_and_translates(db, client):
    """The GET above hands back the program's own item ids while nothing's
    forked yet — PATCHing one of those ids directly (before ever fetching a
    real override id) must still land on the right, newly-forked copy."""
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    course = await _course(db, author=ops)
    await db.commit()

    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base"},
    )).json()["id"]
    add = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": course.title, "course_id": str(course.id)},
    )
    program_item_id = add.json()["id"]

    inherited = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert inherited.json()["is_inherited"] is True
    assert inherited.json()["items"][0]["id"] == program_item_id

    edited = await client.patch(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items/{program_item_id}", headers=_headers(ops),
        json={"item_type": "course", "title": "Renamed for this cohort", "course_id": str(course.id)},
    )
    assert edited.status_code == 200
    assert edited.json()["id"] != program_item_id  # a real, distinct override copy
    assert edited.json()["title"] == "Renamed for this cohort"

    # The program's own item is untouched.
    program_after = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert program_after.json()["items"][0]["title"] == course.title

    override = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert override.json()["is_inherited"] is False
    assert [i["title"] for i in override.json()["items"]] == ["Renamed for this cohort"]


@pytest.mark.asyncio
async def test_a_submission_items_scope_is_also_locked_on_a_cohort_override(db, client):
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    await db.commit()
    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base"},
    )).json()["id"]
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "placeholder"},  # give the program a checklist to override
    )
    added = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items", headers=_headers(ops),
        json={"item_type": "submission", "title": "Poster", "submission_prompt": "Paste your link", "scope": "team"},
    )
    item_id = added.json()["id"]

    flipped = await client.patch(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items/{item_id}", headers=_headers(ops),
        json={"item_type": "submission", "title": "Poster", "submission_prompt": "Paste your link", "scope": "individual"},
    )
    assert flipped.status_code == http_status.HTTP_400_BAD_REQUEST


async def test_deleting_an_inherited_item_forks_everything_else_in(db, client):
    """Deleting one inherited item shouldn't wipe the whole checklist —
    it should fork every other program item in, then drop just that one."""
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    keep_course = await _course(db, author=ops)
    drop_course = await _course(db, author=ops)
    await db.commit()

    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base"},
    )).json()["id"]
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": keep_course.title, "course_id": str(keep_course.id)},
    )
    drop_add = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": drop_course.title, "course_id": str(drop_course.id)},
    )
    drop_item_id = drop_add.json()["id"]

    delete = await client.delete(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items/{drop_item_id}", headers=_headers(ops),
    )
    assert delete.status_code == 204

    override = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert override.json()["is_inherited"] is False
    assert [i["course_id"] for i in override.json()["items"]] == [str(keep_course.id)]

    # The program's own checklist still has both.
    program_after = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert {i["course_id"] for i in program_after.json()["items"]} == {str(keep_course.id), str(drop_course.id)}


# ── reorder ───────────────────────────────────────────────────────────────

async def test_reorder_program_items_rewrites_positions(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()

    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base"},
    )).json()["id"]
    a = (await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "A"},
    )).json()
    b = (await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "B"},
    )).json()
    c = (await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "C"},
    )).json()

    reordered = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items/reorder", headers=_headers(ops),
        json={"item_ids": [c["id"], a["id"], b["id"]]},
    )
    assert reordered.status_code == 200
    assert [i["title"] for i in reordered.json()] == ["C", "A", "B"]
    assert [i["position"] for i in reordered.json()] == [1, 2, 3]

    fetched = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert [i["title"] for i in fetched.json()["items"]] == ["C", "A", "B"]


async def test_reorder_program_items_rejects_a_mismatched_id_set(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()

    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base"},
    )).json()["id"]
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "A"},
    )

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items/reorder", headers=_headers(ops),
        json={"item_ids": [str(uuid.uuid4())]},
    )
    assert resp.status_code == 400


async def test_reordering_an_inherited_cohort_list_forks_it(db, client):
    """Dragging within a cohort's still-inherited (unforked) checklist must
    fork first and translate the dragged ids, same as edit/delete already do."""
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    await db.commit()

    lms_program_id = (await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base"},
    )).json()["id"]
    a = (await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "A"},
    )).json()
    b = (await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "B"},
    )).json()

    inherited = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert inherited.json()["is_inherited"] is True

    reordered = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items/reorder", headers=_headers(ops),
        json={"item_ids": [b["id"], a["id"]]},
    )
    assert reordered.status_code == 200
    assert [i["title"] for i in reordered.json()] == ["B", "A"]
    assert {i["id"] for i in reordered.json()} != {a["id"], b["id"]}  # real, distinct forked copies

    override = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert override.json()["is_inherited"] is False
    assert [i["title"] for i in override.json()["items"]] == ["B", "A"]

    # The program's own checklist keeps its original order.
    program_after = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert [i["title"] for i in program_after.json()["items"]] == ["A", "B"]
