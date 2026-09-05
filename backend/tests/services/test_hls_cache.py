"""The HLS playlist/key cache — see services/hls_cache.py.

What actually matters under a competition-day burst is the *single-flight*
behaviour, not the TTL: 400 students press play within a couple of seconds of
each other, so a plain TTL cache would have all 400 miss together and all 400
hit R2 anyway. These tests pin the collapse, not just the memoisation.
"""

import asyncio

import pytest

from app.core.config import settings
from app.services import hls_cache, storage


@pytest.fixture(autouse=True)
def _clean_cache():
    hls_cache.clear()
    yield
    hls_cache.clear()


class _CountingDownloader:
    """Stands in for storage.download_file, counting real calls and holding
    each one open until released, so a burst can be observed mid-flight."""

    def __init__(self, payload: bytes = b"playlist-bytes"):
        self.payload = payload
        self.calls = 0
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()

    async def __call__(self, bucket, path, *, backend=None):
        self.calls += 1
        self.entered.set()
        await self.gate.wait()
        return self.payload


@pytest.mark.asyncio
async def test_a_concurrent_burst_collapses_to_one_download(monkeypatch):
    monkeypatch.setattr(settings, "HLS_OBJECT_CACHE_SECONDS", 300)
    downloader = _CountingDownloader()
    monkeypatch.setattr(storage, "download_file", downloader)

    # 400 students starting the same video at the same moment.
    waiters = [
        asyncio.create_task(hls_cache.download_cached("lms-hls", "vid/playlist.m3u8", backend="r2"))
        for _ in range(400)
    ]
    # Every waiter has reached the cache and the one shared fetch has started.
    await asyncio.wait_for(downloader.entered.wait(), timeout=5)
    assert downloader.calls == 1, "the burst must not stampede the object store"

    downloader.gate.set()
    assert await asyncio.gather(*waiters) == [b"playlist-bytes"] * 400
    assert downloader.calls == 1


@pytest.mark.asyncio
async def test_a_later_request_is_served_from_the_cache(monkeypatch):
    monkeypatch.setattr(settings, "HLS_OBJECT_CACHE_SECONDS", 300)
    downloader = _CountingDownloader()
    downloader.gate.set()
    monkeypatch.setattr(storage, "download_file", downloader)

    for _ in range(3):
        assert await hls_cache.download_cached("lms-hls", "vid/playlist.m3u8", backend="r2") == b"playlist-bytes"
    assert downloader.calls == 1


@pytest.mark.asyncio
async def test_distinct_objects_do_not_share_an_entry(monkeypatch):
    monkeypatch.setattr(settings, "HLS_OBJECT_CACHE_SECONDS", 300)

    async def _download(bucket, path, *, backend=None):
        return f"{backend}:{bucket}/{path}".encode()

    monkeypatch.setattr(storage, "download_file", _download)

    assert await hls_cache.download_cached("lms-hls", "a/playlist.m3u8", backend="r2") == b"r2:lms-hls/a/playlist.m3u8"
    assert await hls_cache.download_cached("lms-hls", "a/key.key", backend="r2") == b"r2:lms-hls/a/key.key"
    assert await hls_cache.download_cached("lms-hls", "b/key.key", backend="r2") == b"r2:lms-hls/b/key.key"
    # Same path, different backend, is a different object.
    assert await hls_cache.download_cached("lms-hls", "a/key.key", backend=None) == b"None:lms-hls/a/key.key"


@pytest.mark.asyncio
async def test_a_failed_fetch_is_not_cached_and_does_not_wedge_the_key(monkeypatch):
    """A missing object must become servable the instant it is fixed, and one
    failure must not leave a permanently-awaited task every later caller joins."""
    monkeypatch.setattr(settings, "HLS_OBJECT_CACHE_SECONDS", 300)
    attempts = {"n": 0}

    async def _flaky(bucket, path, *, backend=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise FileNotFoundError(path)
        return b"recovered"

    monkeypatch.setattr(storage, "download_file", _flaky)

    with pytest.raises(FileNotFoundError):
        await hls_cache.download_cached("lms-hls", "vid/key.key", backend="r2")
    assert await hls_cache.download_cached("lms-hls", "vid/key.key", backend="r2") == b"recovered"


@pytest.mark.asyncio
async def test_one_caller_disconnecting_does_not_cancel_the_fetch_for_the_rest(monkeypatch):
    """During a bad burst the requests most likely to be cancelled (client gave
    up, nginx timed out) are exactly the ones queued behind a slow fetch. If a
    cancellation propagated into the shared task, one impatient student would
    fail everyone waiting with them."""
    monkeypatch.setattr(settings, "HLS_OBJECT_CACHE_SECONDS", 300)
    downloader = _CountingDownloader(b"late-bytes")
    monkeypatch.setattr(storage, "download_file", downloader)

    leaver = asyncio.create_task(hls_cache.download_cached("lms-hls", "v/p.m3u8", backend="r2"))
    stayer = asyncio.create_task(hls_cache.download_cached("lms-hls", "v/p.m3u8", backend="r2"))
    await asyncio.sleep(0)

    leaver.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leaver

    downloader.gate.set()
    assert await stayer == b"late-bytes"
    assert downloader.calls == 1


@pytest.mark.asyncio
async def test_ttl_of_zero_bypasses_the_cache_entirely(monkeypatch):
    """The escape hatch: one env var takes the cache out of the picture if it
    is ever suspected of serving stale bytes mid-competition."""
    monkeypatch.setattr(settings, "HLS_OBJECT_CACHE_SECONDS", 0)
    downloader = _CountingDownloader()
    downloader.gate.set()
    monkeypatch.setattr(storage, "download_file", downloader)

    for _ in range(3):
        await hls_cache.download_cached("lms-hls", "vid/playlist.m3u8", backend="r2")
    assert downloader.calls == 3
