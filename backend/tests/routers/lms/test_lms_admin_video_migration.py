"""`/lms/admin/courses/video-backend-status` and
`/lms/admin/courses/{course_id}/videos/migrate-to-r2` (2026-09) — the admin
UI's "where does each course's video live, and migrate it" surface, mirroring
scripts/video_migrate_to_r2.py's --status/--reencode as an API.

Redis-free (`client` fixture) — `migrate-to-r2` only needs to enqueue, and
`get_arq_redis` overridden to None exercises the same "dropped" no-op path
`enqueue_transcode`/`safe_enqueue` already proves safe elsewhere.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.user import User
from app.models.videos import Video


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="LMS Admin User",
        email=f"lms-admin-videomig-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=list(roles) if roles else ["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course_module_item(db, *, author, title="C") -> tuple[Course, CourseModule, ModuleItem]:
    course = Course(id=uuid.uuid4(), title=title, created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="video", content={})
    db.add(item)
    await db.flush()
    return course, module, item


def _video(item, *, storage_backend, status="ready") -> Video:
    return Video(
        id=uuid.uuid4(), owner_type="module_item", owner_id=item.id, provider="upload",
        upload_mode="hls_encrypted", source_bucket="video-sources", source_path=f"{item.id}/source.mp4",
        status=status, playlist_path=f"{item.id}/playlist.m3u8", key_path=f"{item.id}/key.bin",
        duration_seconds=10, storage_backend=storage_backend,
    )


@pytest.mark.asyncio
async def test_status_route_is_not_shadowed_by_the_course_id_path_param(db, client):
    """The literal path "/courses/video-backend-status" must resolve to this
    endpoint, never get swallowed by "/courses/{course_id}" as an invalid
    UUID — this is the actual regression this test guards, not just the
    response shape."""
    ops = await _user(db)
    await db.commit()
    resp = await client.get("/lms/admin/courses/video-backend-status", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_200_OK
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_status_groups_by_course_and_counts_each_backend(db, client):
    ops = await _user(db)
    course, module, item = await _course_module_item(db, author=ops, title="Mixed Course")
    other_item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=2, kind="video", content={})
    db.add(other_item)
    await db.flush()
    db.add(_video(item, storage_backend=None))
    db.add(_video(other_item, storage_backend="r2"))
    empty_course, _, _ = await _course_module_item(db, author=ops, title="No Videos Yet")
    await db.commit()

    resp = await client.get("/lms/admin/courses/video-backend-status", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_200_OK
    by_id = {row["course_id"]: row for row in resp.json()}

    assert by_id[str(course.id)]["r2"] == 1
    assert by_id[str(course.id)]["vps"] == 1
    # A course with zero videos is omitted, not shown as 0/0.
    assert str(empty_course.id) not in by_id


@pytest.mark.asyncio
async def test_migrate_queues_only_vps_videos_and_reports_the_rest(db, client):
    ops = await _user(db)
    course, module, item = await _course_module_item(db, author=ops)
    already_migrated_item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=2, kind="video", content={})
    db.add(already_migrated_item)
    await db.flush()
    vps_video = _video(item, storage_backend=None)
    r2_video = _video(already_migrated_item, storage_backend="r2")
    db.add(vps_video)
    db.add(r2_video)
    await db.commit()

    resp = await client.post(f"/lms/admin/courses/{course.id}/videos/migrate-to-r2", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_200_OK
    body = resp.json()
    assert body == {"queued": 1, "already_on_r2": 1}

    # Enqueueing (dropped, no live Redis in this suite) must never itself
    # flip status/storage_backend — that swap belongs entirely to
    # run_encrypted_transcode's own zero-downtime path, not the trigger route.
    await db.refresh(vps_video)
    assert vps_video.storage_backend is None
    assert vps_video.status == "ready"


@pytest.mark.asyncio
async def test_migrate_404s_for_unknown_course(db, client):
    ops = await _user(db)
    await db.commit()
    resp = await client.post(f"/lms/admin/courses/{uuid.uuid4()}/videos/migrate-to-r2", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_video_admin_routes_require_lms_content_role(db, client):
    student = await _user(db, roles=["student"])
    await db.commit()
    status_resp = await client.get("/lms/admin/courses/video-backend-status", headers=_headers(student))
    assert status_resp.status_code == http_status.HTTP_403_FORBIDDEN
    migrate_resp = await client.post(
        f"/lms/admin/courses/{uuid.uuid4()}/videos/migrate-to-r2", headers=_headers(student),
    )
    assert migrate_resp.status_code == http_status.HTTP_403_FORBIDDEN
