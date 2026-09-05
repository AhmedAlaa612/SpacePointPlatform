"""Playlist rewriting for an object-store-backed video — see
routers/video.py::_rewrite_playlist.

The behavioural contract (segments become absolute presigned URLs, the
`#EXT-X-KEY` line stays relative and token-gated) is unchanged and is already
covered end-to-end for the local backend in
tests/routers/lms/test_lms_video.py. What is pinned here is the *cost shape*:
the whole playlist is signed in one batched call rather than one awaited
thread hop per segment. That distinction is invisible in a functional
assertion and invisible in a load test run against a 50-second clip, but it
is the difference between a fixed per-request cost and one that grows with
video length — a half-hour lecture at 10s segments has ~180 segment lines.
"""

import uuid

import pytest

from app.routers import video as video_router
from app.routers.video import _PlaybackRef, _rewrite_playlist


def _playlist(segments: int) -> bytes:
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-TARGETDURATION:10",
        '#EXT-X-KEY:METHOD=AES-128,URI="key.key",IV=0x00000000000000000000000000000000',
    ]
    for i in range(segments):
        lines += ["#EXTINF:10.000000,", f"segment_{i:03d}.ts"]
    lines.append("#EXT-X-ENDLIST")
    return ("\n".join(lines) + "\n").encode()


def _ref() -> _PlaybackRef:
    return _PlaybackRef(
        video_id=uuid.uuid4(),
        playlist_path="some-owner-id/playlist.m3u8",
        key_path="some-owner-id/key.key",
        backend="r2",
    )


@pytest.fixture
def signer(monkeypatch):
    """Records every batch handed to the storage layer."""
    calls: list[list[str]] = []

    async def _get_signed_urls(bucket, paths, expires_in=3600, *, backend=None):
        calls.append(list(paths))
        return [f"https://r2.example/{p}?sig=abc&exp={expires_in}" for p in paths]

    monkeypatch.setattr(video_router.storage, "get_signed_urls", _get_signed_urls)
    return calls


@pytest.mark.asyncio
async def test_the_whole_playlist_is_signed_in_one_batch(signer):
    out = (await _rewrite_playlist(_playlist(180), _ref(), "tok", expires_in=600)).decode()

    assert len(signer) == 1, "one batched call, regardless of segment count"
    assert len(signer[0]) == 180
    # Keys are built from the playlist's own directory, never from video.id —
    # pre-migration rows have a prefix that is the old owner-row id.
    assert signer[0][0] == "some-owner-id/segment_000.ts"
    assert signer[0][-1] == "some-owner-id/segment_179.ts"
    assert out.count("https://r2.example/") == 180


@pytest.mark.asyncio
async def test_segment_urls_land_in_their_original_positions(signer):
    out = (await _rewrite_playlist(_playlist(3), _ref(), "tok", expires_in=600)).decode().splitlines()

    # Batching splices URLs back by index; a mis-splice would reorder playback
    # without failing anything else.
    assert out[4] == "#EXTINF:10.000000," and "segment_000.ts" in out[5]
    assert out[6] == "#EXTINF:10.000000," and "segment_001.ts" in out[7]
    assert out[8] == "#EXTINF:10.000000," and "segment_002.ts" in out[9]
    assert out[0] == "#EXTM3U"
    assert out[-1] == "#EXT-X-ENDLIST"


@pytest.mark.asyncio
async def test_the_key_line_stays_relative_and_token_gated(signer):
    out = (await _rewrite_playlist(_playlist(2), _ref(), "tok-123", expires_in=600)).decode()

    # The AES key never moves to the object store: segments there are already
    # AES-128 encrypted, so an expired segment URL yields ciphertext, and the
    # key stays behind the API's access check.
    assert 'URI="key?token=tok-123"' in out
    assert "METHOD=AES-128" in out
    assert "key.key" not in out


@pytest.mark.asyncio
async def test_a_playlist_with_no_segments_signs_nothing(signer):
    out = (await _rewrite_playlist(_playlist(0), _ref(), "tok", expires_in=600)).decode()

    assert signer == [], "an empty batch must not cost a thread hop at all"
    assert out.startswith("#EXTM3U")


@pytest.mark.asyncio
async def test_a_non_object_store_video_is_rewritten_to_relative_paths(signer):
    ref = _PlaybackRef(
        video_id=uuid.uuid4(),
        playlist_path="owner/playlist.m3u8",
        key_path="owner/key.key",
        backend=None,
    )
    out = (await _rewrite_playlist(_playlist(2), ref, "tok", expires_in=600)).decode()

    assert signer == [], "nothing to presign when segments are served by this API"
    assert "segment/segment_000.ts?token=tok" in out
    assert "segment/segment_001.ts?token=tok" in out
