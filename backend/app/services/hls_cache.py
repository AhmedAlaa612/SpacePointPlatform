"""In-process cache for the two HLS objects every viewer of a video fetches
identically: the stored `.m3u8` playlist and the AES-128 key.

**Why this is safe.** Both objects are viewer-independent by construction.
The stored playlist carries plain relative filenames and is rewritten
per-request *after* download (routers/video.py::_rewrite_playlist), so the
bytes on the object store are the same for everyone. The key is 16 bytes of
AES material for the video, not for the viewer. Nothing about either depends
on who is asking — the access check that decides *whether* to hand them over
still runs per request, upstream of this, and is unaffected.

**Why it matters.** 400 students starting the same video is 400 identical
playlist downloads plus 400 identical key downloads from R2 — 800 network
round trips, each one occupying a worker thread and (before the routes were
changed to release it first) a database connection, to fetch bytes the
process already had. With this, the same burst costs one round trip per
object per worker process.

**Single-flight is the point, more than the TTL.** A plain TTL cache does
nothing for a cold burst: 400 requests arrive together, all miss, and all
400 stampede the origin anyway. So the first caller starts a task and every
concurrent caller for the same key awaits that same task. The TTL only
extends the benefit past the first burst.

Deliberately per-process and unshared: three uvicorn workers keep three
copies, which is three round trips instead of 800 and needs no Redis in the
path of video playback. Failures are never cached — a missing object must
stay a 404 the moment it is fixed, not for the length of a TTL.
"""

import asyncio
import time

from app.core.config import settings
from app.core.timing import phase
from app.services import storage

# key -> (bytes, monotonic expiry). Bounded because the key space is
# "objects this process has served", which is finite but not fixed —
# a growing course catalogue must not become a slow memory leak.
_cache: dict[tuple[str | None, str, str], tuple[bytes, float]] = {}
_inflight: dict[tuple[str | None, str, str], "asyncio.Task[bytes]"] = {}

# Playlists are a few KB and keys are 16 bytes, so this bounds the cache at a
# few megabytes even when full. Evicts oldest-inserted first (dicts preserve
# insertion order); an entry that is still hot simply gets re-fetched once.
_MAX_ENTRIES = 512


def clear() -> None:
    """Drop everything. For tests, and for a future admin hook if a re-encode
    ever needs to take effect faster than the TTL."""
    _cache.clear()


async def download_cached(bucket: str, path: str, *, backend: str | None) -> bytes:
    """`storage.download_file`, memoised per (backend, bucket, path).

    Falls straight through to the uncached call when the TTL is configured to
    0, so the cache can be taken out of the picture entirely with one env var
    if it is ever suspected of serving stale bytes.
    """
    ttl = settings.HLS_OBJECT_CACHE_SECONDS
    if ttl <= 0:
        with phase("r2_download"):
            return await storage.download_file(bucket, path, backend=backend)

    key = (backend, bucket, path)
    now = time.monotonic()

    hit = _cache.get(key)
    if hit is not None and hit[1] > now:
        return hit[0]

    task = _inflight.get(key)
    if task is None:
        task = asyncio.get_running_loop().create_task(
            _fetch_and_store(key, bucket, path, backend, ttl)
        )
        _inflight[key] = task

    # shield: if THIS request is cancelled (the student closed the tab, or
    # nginx timed the connection out), the in-flight fetch must survive for
    # the other requests waiting on it. Without it, one client disconnecting
    # cancels the fetch for everyone queued behind it — precisely the
    # requests most likely to disconnect during a bad burst.
    with phase("r2_download"):
        return await asyncio.shield(task)


async def _fetch_and_store(key, bucket: str, path: str, backend: str | None, ttl: int) -> bytes:
    try:
        data = await storage.download_file(bucket, path, backend=backend)
    finally:
        # Cleared in `finally`, not on success: a failed fetch must not leave
        # a permanently-awaited task behind that every later caller joins and
        # re-raises from.
        _inflight.pop(key, None)
    if len(_cache) >= _MAX_ENTRIES:
        for stale in list(_cache)[: len(_cache) - _MAX_ENTRIES + 1]:
            _cache.pop(stale, None)
    _cache[key] = (data, time.monotonic() + ttl)
    return data
