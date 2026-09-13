"""Application Content > Video Links (2026-09) — the facilitator-editable
lineup behind Phase 1's "watch and summarize" videos. Covers growing/
shrinking the count and the empty-list rejection on the admin PUT, that
the applicant-facing list reflects whatever count is configured (not a
hardcoded 3), and the regression test for the bug this all started from:
signup used to seed `VideoSubmission` rows from a frozen literal instead
of these settings (see services/instructors/application_videos.py).
"""

import json
import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.instructors.video_submission import VideoSubmission
from app.models.user import User
from app.services.instructors.application_videos import DEFAULT_VIDEO_URLS


async def _facilitator(db) -> User:
    u = User(
        id=uuid.uuid4(), full_name="Video Config Facilitator",
        email=f"facilitator-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["facilitator"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _applicant(db) -> User:
    u = User(
        id=uuid.uuid4(), full_name="Video Config Applicant",
        email=f"applicant-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["applicant"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_get_application_videos_defaults_to_the_three_legacy_urls(db, client):
    facilitator = await _facilitator(db)
    await db.commit()

    resp = await client.get("/instructors/facilitator/application/videos", headers=_headers(facilitator))
    assert resp.status_code == http_status.HTTP_200_OK
    assert [v["url"] for v in resp.json()] == DEFAULT_VIDEO_URLS


@pytest.mark.asyncio
async def test_facilitator_can_grow_the_video_lineup_to_four(db, client):
    facilitator = await _facilitator(db)
    await db.commit()

    put_resp = await client.put(
        "/instructors/facilitator/application/videos", headers=_headers(facilitator),
        json={"videos": [
            {"video_no": 1, "title": "A", "url": "https://youtu.be/aaaaaaaaaaa"},
            {"video_no": 2, "title": "B", "url": "https://youtu.be/bbbbbbbbbbb"},
            {"video_no": 3, "title": "C", "url": "https://youtu.be/ccccccccccc"},
            {"video_no": 4, "title": "D", "url": "https://youtu.be/ddddddddddd"},
        ]},
    )
    assert put_resp.status_code == http_status.HTTP_200_OK

    get_resp = await client.get("/instructors/facilitator/application/videos", headers=_headers(facilitator))
    body = get_resp.json()
    assert len(body) == 4
    assert body[3] == {"video_no": 4, "title": "D", "url": "https://youtu.be/ddddddddddd"}


@pytest.mark.asyncio
async def test_shrinking_then_growing_again_does_not_resurrect_stale_data(db, client):
    """A removed slot's title/url must not silently come back if the count
    is later increased again — set_configured_videos deletes those
    settings rather than leaving them to be picked back up."""
    facilitator = await _facilitator(db)
    await db.commit()

    await client.put(
        "/instructors/facilitator/application/videos", headers=_headers(facilitator),
        json={"videos": [
            {"video_no": 1, "title": "A", "url": "https://youtu.be/aaaaaaaaaaa"},
            {"video_no": 2, "title": "B", "url": "https://youtu.be/bbbbbbbbbbb"},
            {"video_no": 3, "title": "Stale", "url": "https://youtu.be/staaaaaaale"},
        ]},
    )
    # Shrink to 2 — drops the third slot.
    shrink_resp = await client.put(
        "/instructors/facilitator/application/videos", headers=_headers(facilitator),
        json={"videos": [
            {"video_no": 1, "title": "A", "url": "https://youtu.be/aaaaaaaaaaa"},
            {"video_no": 2, "title": "B", "url": "https://youtu.be/bbbbbbbbbbb"},
        ]},
    )
    assert shrink_resp.status_code == http_status.HTTP_200_OK
    shrunk = (await client.get("/instructors/facilitator/application/videos", headers=_headers(facilitator))).json()
    assert len(shrunk) == 2

    # Grow back to 3 with a brand-new third slot.
    grow_resp = await client.put(
        "/instructors/facilitator/application/videos", headers=_headers(facilitator),
        json={"videos": [
            {"video_no": 1, "title": "A", "url": "https://youtu.be/aaaaaaaaaaa"},
            {"video_no": 2, "title": "B", "url": "https://youtu.be/bbbbbbbbbbb"},
            {"video_no": 3, "title": "Fresh", "url": "https://youtu.be/freeeeeeesh"},
        ]},
    )
    assert grow_resp.status_code == http_status.HTTP_200_OK

    get_resp = await client.get("/instructors/facilitator/application/videos", headers=_headers(facilitator))
    body = get_resp.json()
    assert body[2] == {"video_no": 3, "title": "Fresh", "url": "https://youtu.be/freeeeeeesh"}
    assert "Stale" not in [v["title"] for v in body]


@pytest.mark.asyncio
async def test_update_application_videos_rejects_an_empty_list(db, client):
    facilitator = await _facilitator(db)
    await db.commit()

    resp = await client.put(
        "/instructors/facilitator/application/videos", headers=_headers(facilitator), json={"videos": []},
    )
    assert resp.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_applicant_video_list_reflects_the_configured_count_not_a_hardcoded_three(db, client):
    facilitator = await _facilitator(db)
    await db.commit()
    await client.put(
        "/instructors/facilitator/application/videos", headers=_headers(facilitator),
        json={"videos": [{"video_no": 1, "title": "Only one", "url": "https://youtu.be/onlyoneeeee"}]},
    )

    applicant = await _applicant(db)
    await db.commit()
    resp = await client.get("/instructors/videos", headers=_headers(applicant))
    assert resp.status_code == http_status.HTTP_200_OK
    body = resp.json()
    assert len(body) == 1
    assert body[0]["youtube_url"] == "https://youtu.be/onlyoneeeee"


@pytest.mark.asyncio
async def test_signup_seeds_video_submissions_from_the_configured_lineup_not_a_hardcoded_literal(db, client):
    """Regression test for the bug: routers/auth.py's signup handler used to
    carry its own frozen copy of the original 3 URLs and never read what
    the facilitator saved here, so an edited URL never reached a new
    applicant despite the admin page's own copy claiming it would ("takes
    effect for new applicants immediately")."""
    facilitator = await _facilitator(db)
    await db.commit()
    await client.put(
        "/instructors/facilitator/application/videos", headers=_headers(facilitator),
        json={"videos": [
            {"video_no": 1, "title": "Custom One", "url": "https://youtu.be/customoneee"},
            {"video_no": 2, "title": "Custom Two", "url": "https://youtu.be/customtwoee"},
        ]},
    )

    payload = {
        "full_name": "Signup Video Test",
        "email": f"signup-video-{uuid.uuid4().hex[:8]}@example.com",
        "password": "s3cret-pass",
        "background_areas": ["Engineering"],
        "has_own_transportation": True,
        "country": "AE",
    }
    resp = await client.post(
        "/auth/instructor-apply",
        data={"payload": json.dumps(payload)},
        files={"cv": ("", b"", "application/octet-stream")},
    )
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(select(User).where(User.email == payload["email"]))).scalars().first()
    rows = (await db.execute(
        select(VideoSubmission).where(VideoSubmission.user_id == user.id).order_by(VideoSubmission.video_no)
    )).scalars().all()
    assert [r.youtube_url for r in rows] == ["https://youtu.be/customoneee", "https://youtu.be/customtwoee"]
