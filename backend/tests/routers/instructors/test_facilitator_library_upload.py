"""Facilitator Curriculum Library uploads (2026-08-31) — a video is just
another file through the same generic `/library` upload endpoint a PDF or
slide deck already uses; this covers that a video round-trips with the
right format/resource_type, and the new fail-fast size guard that protects
the endpoint's synchronous read-into-memory from a stray multi-GB upload
(video files being the reason one is likely now).
"""

import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.instructors.library import LibraryModule
from app.models.user import User


async def _facilitator(db) -> User:
    u = User(
        id=uuid.uuid4(), full_name="Library Facilitator",
        email=f"facilitator-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["facilitator"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _module(db) -> LibraryModule:
    m = LibraryModule(id=uuid.uuid4(), name=f"Module {uuid.uuid4().hex[:6]}")
    db.add(m)
    await db.flush()
    return m


@pytest.mark.asyncio
async def test_video_upload_round_trips_as_a_file_resource(client, db):
    facilitator = await _facilitator(db)
    module = await _module(db)
    await db.commit()

    resp = await client.post(
        f"/instructors/facilitator/library?module_id={module.id}&title=Orientation",
        headers=_headers(facilitator),
        files={"file": ("orientation.mp4", b"\x00\x00\x00 ftypmp4 fake video bytes", "video/mp4")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["format"] == "MP4"
    assert body["resource_type"] == "file"
    assert body["file_url"]  # a resolved signed URL, not blank (only PDFs are)


@pytest.mark.asyncio
async def test_upload_rejects_an_oversized_file(client, db, monkeypatch):
    import app.routers.instructors.facilitator as facilitator_router
    monkeypatch.setattr(facilitator_router, "MAX_LIBRARY_FILE_BYTES", 10)

    facilitator = await _facilitator(db)
    module = await _module(db)
    await db.commit()

    too_big = b"x" * 11
    resp = await client.post(
        f"/instructors/facilitator/library?module_id={module.id}&title=Huge",
        headers=_headers(facilitator),
        files={"file": ("huge.mp4", too_big, "video/mp4")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_video_embed_round_trips_with_playback_info(client, db):
    """The other half of the "Video" tab in Add Resource — a pasted
    YouTube/Vimeo link, not just a file upload. format="EMBED", and
    video_info carries the iframe-ready shape the frontend's shared
    <VideoPlayer> consumes directly."""
    facilitator = await _facilitator(db)
    module = await _module(db)
    await db.commit()

    resp = await client.post(
        "/instructors/facilitator/library/video-embed",
        params={"module_id": str(module.id), "title": "Intro", "url": "https://youtu.be/dQw4w9WgXcQ"},
        headers=_headers(facilitator),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["format"] == "EMBED"
    assert body["resource_type"] == "file"
    assert body["file_url"] == "https://youtu.be/dQw4w9WgXcQ"
    assert body["video_info"]["provider"] == "youtube"
    assert body["video_info"]["embed_url"] == "https://youtu.be/dQw4w9WgXcQ"
    assert body["video_info"]["status"] == "ready"


@pytest.mark.asyncio
async def test_video_embed_rejects_an_unrecognized_host(client, db):
    facilitator = await _facilitator(db)
    module = await _module(db)
    await db.commit()

    resp = await client.post(
        "/instructors/facilitator/library/video-embed",
        params={"module_id": str(module.id), "title": "Intro", "url": "https://example.com/video.mp4"},
        headers=_headers(facilitator),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_uploaded_video_carries_video_info_too(client, db):
    """Not just embeds — an uploaded video's response also carries video_info
    now (it didn't before), which is what lets the row render through the
    same shared <VideoPlayer> as an embed instead of a hardcoded
    upload/direct guess."""
    facilitator = await _facilitator(db)
    module = await _module(db)
    await db.commit()

    resp = await client.post(
        f"/instructors/facilitator/library?module_id={module.id}&title=Orientation",
        headers=_headers(facilitator),
        files={"file": ("orientation.mp4", b"\x00\x00\x00 ftypmp4 fake video bytes", "video/mp4")},
    )
    assert resp.status_code == 201, resp.text
    info = resp.json()["video_info"]
    assert info["provider"] == "upload"
    assert info["mode"] == "direct"
    assert info["status"] == "ready"
    assert info["url"]


@pytest.mark.asyncio
async def test_replace_file_also_rejects_an_oversized_file(client, db, monkeypatch):
    facilitator = await _facilitator(db)
    module = await _module(db)
    await db.commit()

    created = await client.post(
        f"/instructors/facilitator/library?module_id={module.id}&title=Clip",
        headers=_headers(facilitator),
        files={"file": ("clip.mp4", b"small fake video", "video/mp4")},
    )
    assert created.status_code == 201, created.text
    resource_id = created.json()["id"]

    import app.routers.instructors.facilitator as facilitator_router
    monkeypatch.setattr(facilitator_router, "MAX_LIBRARY_FILE_BYTES", 10)

    too_big = b"x" * 11
    resp = await client.put(
        f"/instructors/facilitator/library/{resource_id}/file",
        headers=_headers(facilitator),
        files={"file": ("huge.mp4", too_big, "video/mp4")},
    )
    assert resp.status_code == 413
