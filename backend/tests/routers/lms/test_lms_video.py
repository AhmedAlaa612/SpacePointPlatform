"""LM1-6 tests — upload sets pending, transcode flips status via a fake
encoder (no real ffmpeg — it only exists in the Docker image), and the
token gate on the streaming routes. Ported to the standardized video
service (2026-09) — `ModuleVideo` is gone, replaced by `Video`
(owner_type="module_item"), and `create_video_token`/`decode_video_token`
now carry a `video_id` instead of an `item_id`.

Token issuance and streaming now go through the generic
`routers/video.py` surface (`/videos/{video_id}/...`), keyed by
`video.id` rather than `item.id` — `routers/lms/video.py` keeps only the
upload endpoint. `test_token_issuance_...`/`test_streaming_routes_...`
below exercise that generic router; the module_item enrollment check they
cover (`_check_module_item`) lives there now, not in this app.

Redis-free (`client` fixture; `get_arq_redis` is overridden to None, so
upload's dispatch reads "dropped" — that's the correct, already-proven-safe
behavior, not a test gap, see conftest.py).
"""

import uuid
from datetime import timedelta

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token, create_video_token
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.user import User
from app.models.videos import Video
from app.services import storage
from app.services.lms import enroll
from app.services.video_service import HLS_BUCKET, SOURCE_BUCKET, EncodeResult, run_encrypted_transcode


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="LMS Video User",
        email=f"lms-video-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=list(roles) if roles else ["student"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course_module_item(db, *, author) -> tuple[Course, CourseModule, ModuleItem]:
    course = Course(id=uuid.uuid4(), title="C", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="video", content={})
    db.add(item)
    await db.flush()
    return course, module, item


# ── upload ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_requires_content_role_and_a_video_item(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    student = await _user(db, roles=["student"])
    denied = await client.post(
        f"/lms/admin/items/{item.id}/video", headers=_headers(student),
        files={"file": ("v.mp4", b"fake-bytes", "video/mp4")},
    )
    assert denied.status_code == http_status.HTTP_403_FORBIDDEN

    text_item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=2, kind="text", content={"body": "x"})
    db.add(text_item)
    await db.commit()
    wrong_kind = await client.post(
        f"/lms/admin/items/{text_item.id}/video", headers=_headers(ops),
        files={"file": ("v.mp4", b"fake-bytes", "video/mp4")},
    )
    assert wrong_kind.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_upload_sets_pending_and_reports_dispatch(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/items/{item.id}/video", headers=_headers(ops),
        files={"file": ("lesson.mp4", b"fake-video-bytes", "video/mp4")},
    )
    assert resp.status_code == http_status.HTTP_202_ACCEPTED
    body = resp.json()
    assert body["transcode_status"] == "pending"
    # no live Redis in this suite (conftest.py) — safe_enqueue correctly no-ops
    assert body["dispatch"] == "dropped"

    video = (await db.execute(
        select(Video).where(Video.owner_type == "module_item", Video.owner_id == item.id)
    )).scalars().first()
    assert video.status == "pending"
    assert video.upload_mode == "hls_encrypted"
    assert video.source_bucket == SOURCE_BUCKET


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(db, client, monkeypatch):
    import app.routers.lms.video as video_router
    monkeypatch.setattr(video_router, "MAX_UPLOAD_BYTES", 10)

    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/items/{item.id}/video", headers=_headers(ops),
        files={"file": ("v.mp4", b"way-too-many-bytes-for-the-limit", "video/mp4")},
    )
    assert resp.status_code == http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


@pytest.mark.asyncio
async def test_reupload_cleans_up_old_hls_objects_even_with_a_pre_migration_layout(db, client):
    """A video whose HLS objects sit under `item_id` (the layout a row
    backfilled from the old ModuleVideo table has — see `_ready_video`'s own
    note) must still get its old segment/playlist/key deleted when replaced
    by a new upload, not just have a dangling storage prefix nobody cleans
    up because it doesn't match the row's own id."""
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()
    old_video = await _ready_video(db, item)
    old_prefix = old_video.playlist_path.rsplit("/", 1)[0]
    await db.commit()

    resp = await client.post(
        f"/lms/admin/items/{item.id}/video", headers=_headers(ops),
        files={"file": ("lesson.mp4", b"fake-new-video-bytes", "video/mp4")},
    )
    assert resp.status_code == http_status.HTTP_202_ACCEPTED

    assert await storage.list_files(HLS_BUCKET, f"{old_prefix}/") == []


# ── transcode (fake encoder — no real ffmpeg) ──────────────────────────────

async def _fake_encoder(source_path):
    return EncodeResult(
        playlist=b"#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"key\"\nsegment_000.ts\n#EXT-X-ENDLIST\n",
        segments={"segment_000.ts": b"fake-ts-bytes"},
        key=b"0" * 16,
        duration_seconds=42,
    )


@pytest.mark.asyncio
async def test_run_transcode_flips_pending_to_ready_via_fake_encoder(db):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    video = Video(
        id=uuid.uuid4(), owner_type="module_item", owner_id=item.id, provider="upload",
        upload_mode="hls_encrypted", source_bucket=SOURCE_BUCKET,
        source_path=f"{item.id}/source.mp4", status="pending",
    )
    db.add(video)
    await db.commit()
    await storage.upload_to_path(SOURCE_BUCKET, video.source_path, b"source-bytes", "video/mp4")

    await run_encrypted_transcode(db, video.id, encoder=_fake_encoder)

    await db.refresh(video)
    assert video.status == "ready"
    assert video.duration_seconds == 42
    assert video.playlist_path == f"{video.id}/playlist.m3u8"
    stored_playlist = await storage.download_file(HLS_BUCKET, video.playlist_path)
    assert b"segment_000.ts" in stored_playlist


async def _failing_encoder(source_path):
    raise RuntimeError("ffmpeg blew up")


@pytest.mark.asyncio
async def test_run_transcode_records_failure_on_encoder_error(db):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    video = Video(
        id=uuid.uuid4(), owner_type="module_item", owner_id=item.id, provider="upload",
        upload_mode="hls_encrypted", source_bucket=SOURCE_BUCKET,
        source_path=f"{item.id}/source.mp4", status="pending",
    )
    db.add(video)
    await db.commit()
    await storage.upload_to_path(SOURCE_BUCKET, video.source_path, b"source-bytes", "video/mp4")

    await run_encrypted_transcode(db, video.id, encoder=_failing_encoder)

    await db.refresh(video)
    assert video.status == "failed"
    assert "ffmpeg blew up" in video.status_error


# ── token issuance + streaming gate ────────────────────────────────────────

async def _ready_video(db, item) -> Video:
    """`video.id` (uuid4) is deliberately distinct from `item.id` here — same
    shape a row backfilled from the old ModuleVideo table has (its
    playlist_path/key_path/segments still sit under the historical
    `item_id` prefix, not this row's own, freshly-generated id). Storage
    paths below are all keyed by `item.id`, matching playlist_path/key_path
    — this is what get_segment must resolve against, not video.id."""
    video = Video(
        id=uuid.uuid4(), owner_type="module_item", owner_id=item.id, provider="upload",
        upload_mode="hls_encrypted", source_bucket=SOURCE_BUCKET,
        source_path=f"{item.id}/source.mp4", status="ready",
        playlist_path=f"{item.id}/playlist.m3u8", key_path=f"{item.id}/key.bin",
        duration_seconds=10,
    )
    db.add(video)
    await db.flush()
    await storage.upload_to_path(
        HLS_BUCKET, video.playlist_path,
        b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\nsegment_000.ts\n#EXT-X-ENDLIST\n',
        "application/vnd.apple.mpegurl",
    )
    await storage.upload_to_path(HLS_BUCKET, f"{item.id}/segment_000.ts", b"ts-bytes", "video/mp2t")
    await storage.upload_to_path(HLS_BUCKET, video.key_path, b"1" * 16, "application/octet-stream")
    return video


@pytest.mark.asyncio
async def test_token_issuance_requires_enrollment_and_ready_video(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    await db.commit()

    student = await _user(db, roles=["student"])
    pending_video = Video(
        id=uuid.uuid4(), owner_type="module_item", owner_id=item.id, provider="upload",
        upload_mode="hls_encrypted", source_bucket="b", source_path="p", status="pending",
    )
    db.add(pending_video)
    await db.commit()

    not_ready = await client.get(f"/videos/{pending_video.id}/token", headers=_headers(student))
    # not enrolled -> 404 before the readiness check is even reached
    assert not_ready.status_code == http_status.HTTP_404_NOT_FOUND

    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()
    still_not_ready = await client.get(f"/videos/{pending_video.id}/token", headers=_headers(student))
    assert still_not_ready.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_streaming_routes_require_a_valid_matching_unexpired_token(db, client):
    ops = await _user(db, roles=["operations"])
    course, module, item = await _course_module_item(db, author=ops)
    student = await _user(db, roles=["student"])
    await enroll(db, user_id=student.id, course_id=course.id)
    await db.commit()
    video = await _ready_video(db, item)
    await db.commit()

    # valid token -> playlist rewritten with token-bearing relative URLs
    # (relative, not absolute — so they resolve correctly regardless of any
    # reverse-proxy prefix in front of the API; see _rewrite_playlist).
    # These routes are keyed by video.id now (routers/video.py), not item.id.
    token = create_video_token(student.id, video.id)
    ok = await client.get(f"/videos/{video.id}/playlist", params={"token": token})
    assert ok.status_code == 200
    assert f"segment/segment_000.ts?token={token}" in ok.text
    assert f'URI="key?token={token}"' in ok.text

    seg = await client.get(f"/videos/{video.id}/segment/segment_000.ts", params={"token": token})
    assert seg.status_code == 200 and seg.content == b"ts-bytes"

    key = await client.get(f"/videos/{video.id}/key", params={"token": token})
    assert key.status_code == 200 and key.content == b"1" * 16

    # garbage token -> 403
    bad = await client.get(f"/videos/{video.id}/playlist", params={"token": "not-a-real-token"})
    assert bad.status_code == http_status.HTTP_403_FORBIDDEN

    # expired token -> 403
    expired = create_video_token(student.id, video.id, expires_delta=timedelta(seconds=-1))
    expired_resp = await client.get(f"/videos/{video.id}/playlist", params={"token": expired})
    assert expired_resp.status_code == http_status.HTTP_403_FORBIDDEN

    # token minted for a different video -> 403 (its video_id doesn't match the URL's)
    other_item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=2, kind="video", content={})
    db.add(other_item)
    await db.commit()
    other_video = await _ready_video(db, other_item)
    await db.commit()
    wrong_video_token = create_video_token(student.id, other_video.id)
    mismatched = await client.get(f"/videos/{video.id}/playlist", params={"token": wrong_video_token})
    assert mismatched.status_code == http_status.HTTP_403_FORBIDDEN

    # valid token, but for a student who is NOT enrolled -> 404, not 403
    stranger = await _user(db, roles=["student"])
    await db.commit()
    stranger_token = create_video_token(stranger.id, video.id)
    not_enrolled = await client.get(f"/videos/{video.id}/playlist", params={"token": stranger_token})
    assert not_enrolled.status_code == http_status.HTTP_404_NOT_FOUND

    # path traversal in the segment name -> 404, never touches storage
    traversal = await client.get(f"/videos/{video.id}/segment/..%2F..%2Fetc%2Fpasswd", params={"token": token})
    assert traversal.status_code == http_status.HTTP_404_NOT_FOUND

    # segment_1000.ts (B1): "%03d" in the encoder is a *minimum* width, so a
    # video past 999 segments (66m36s at 4s/segment) writes segment_1000.ts —
    # a fixed \d{3} regex 404s on it mid-playback. 4+ digits must resolve.
    await storage.upload_to_path(HLS_BUCKET, f"{item.id}/segment_1000.ts", b"late-ts-bytes", "video/mp2t")
    late_seg = await client.get(f"/videos/{video.id}/segment/segment_1000.ts", params={"token": token})
    assert late_seg.status_code == 200 and late_seg.content == b"late-ts-bytes"
