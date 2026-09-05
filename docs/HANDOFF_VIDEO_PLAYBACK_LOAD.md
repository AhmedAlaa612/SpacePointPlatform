# Video playback under load — diagnosis and fixes (round 3)

**Status:** cause identified by reading the code; fixes implemented and unit-tested; **not yet
measured against the VPS.** Written 2026-09-05, continuing the investigation that ended with
"13-23s median, dominant bottleneck unidentified" after PR #44 (R2 + compression), PR #51 (query
collapse) and PR #52 (drop the redundant re-check).

**Read §1 before running another load test.** The previous round's central confusion — why
removing two of three DB-heavy calls per video start changed nothing — has an answer, and it
invalidates the reasoning that produced #51 and #52.

**Still open and NOT addressed here: §6.** The external-client connection failures are a
network-layer question that needs shell access to the VPS. Nothing in this round touches them.

---

## 1. Why #51 and #52 did nothing

Both PRs optimised **how many queries** a video start runs. The cost was never the queries. It was
**how long a pooled database connection stays checked out**, and that is set by the network call
that happens *after* the queries, while the connection is still held.

`get_db` yields one `AsyncSession` for the entire request:

```python
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

A session holds its connection from its first query until the session closes — which, as a FastAPI
dependency, means **the end of the request**. So `GET /videos/{id}/playlist` did this:

1. check out a connection (1 of 15 per worker: `pool_size=10 + max_overflow=5`)
2. run the token/video queries — milliseconds
3. **download the playlist from R2 — ~270ms, connection still held**
4. **presign every segment line, one awaited thread hop each — connection still held**
5. return, releasing the connection

Steps 3-4 are 99% of the hold and contain no database work at all. Removing queries from step 2
cannot shorten a hold whose length is decided by step 3. That is exactly the null result #51 and
#52 produced.

### The evidence that was misread

`pg_stat_activity` sampled mid-burst showed connections **idle**, in `wait_event=ClientRead`, never
saturated. The previous round read that as "Postgres is not the bottleneck" and moved on.

Postgres was indeed not the bottleneck. But `idle` + `ClientRead` on a connection the application
is holding is not evidence of slack — it is the *signature of this bug*. It says: the app has
checked this connection out, told Postgres nothing, and Postgres is waiting for it to speak. It was
waiting through an R2 round trip. The pool was the constrained resource, and its own metrics looked
healthy precisely because the constraint was hold time rather than query time.

### Arithmetic that fits the observed numbers

Per video start: 2 requests do R2 work (`/playlist`, `/key`). 400 students → 800 such requests
against 45 connections app-wide (3 workers × 15).

- If a connection is held ~300ms: 800 × 0.3 / 45 ≈ **5.3s** of pure pool queueing.
- Hold time is worse than 300ms, because of §2 below.

That is the right order of magnitude for a 13s median, and — critically — it is *not* proportional
to query count, which is why two rounds of query optimisation slid straight off it.

---

## 2. Three compounding costs in the same path

### 2.1 boto3's connection pool was 10, under a 40-thread limiter

`storage_r2._client()` built its `botocore.Config` without `max_pool_connections`. The default is
**10**. Meanwhile `anyio`'s default worker-thread limiter is **40** per process — and every R2 call
in this codebase runs through `anyio.to_thread.run_sync`.

So up to 40 threads per worker shared an HTTP pool of 10. urllib3 handles that overflow with
`block=False`: it opens a **brand-new connection**, uses it, and **discards it on release**. No
error, no exception — just a silent full TLS handshake on roughly three out of every four R2 calls,
plus the handshake CPU on a 4-vCPU box already running the event loop.

This also explains a measurement the previous round recorded without remarking on it: a "warm"
357-byte download costing 265-285ms, barely better than the 530ms cold one. A genuinely reused
keep-alive connection to R2 should serve 357 bytes in roughly one RTT. Those downloads were not
warm; the pool was throwing the connection away each time.

Fixed: `max_pool_connections` is now `settings.R2_MAX_POOL_CONNECTIONS` (default 64, sized above the
thread limiter).

### 2.2 Presigning cost one awaited thread hop per segment

`_rewrite_playlist` looped over the playlist and did `await storage.get_signed_url(...)` per segment
line. Presigning is pure local HMAC — no network, nothing billed — but each call was a separate
`await anyio.to_thread.run_sync`: one worker-thread-limiter acquisition and one full lap of the
event loop, paid **sequentially, inside the request**, with the DB connection held.

Under 400 concurrent starts an event-loop lap is not free, and those threads are the same 40 the R2
downloads are competing for.

**This is also why the load test under-measures the real risk.** The test video
(`48775531-...`, 357-byte playlist) is about 5 segments. A 30-minute lecture at 10s segments is
~180. The per-request cost scales with video length, so real course videos are several times worse
here than anything measured so far.

Fixed: `storage.get_signed_urls()` signs the whole playlist in **one** thread hop. O(1) trips
instead of O(segments).

### 2.3 400 students downloaded the same bytes 800 times

The stored `.m3u8` and the AES key are **viewer-independent by construction**. The playlist is
rewritten per-request *after* download, so the bytes on R2 are identical for everyone; the key is 16
bytes of AES material for the video, not for the viewer.

400 students starting one video therefore fetched the same playlist 400 times and the same key 400
times — 800 identical round trips for bytes the process already had.

Fixed: `app/services/hls_cache.py`, an in-process TTL cache with **single-flight**. Single-flight is
the part that matters: a plain TTL cache does nothing for a cold burst, because all 400 requests
miss together and stampede anyway. The first caller starts one task; every concurrent caller for the
same object awaits that same task. A burst now costs one round trip per object per worker process —
**~6 instead of 800**.

Details worth knowing:
- `asyncio.shield` on the await, so one student closing their tab does not cancel the shared fetch
  for everyone queued behind them.
- Failures are never cached — a missing object becomes servable the moment it is fixed.
- `HLS_OBJECT_CACHE_SECONDS=0` disables it entirely, as a one-env-var escape hatch.
- Staleness bound: a re-encode writes to the same paths, so a re-encoded video can serve old
  playlist/key bytes for up to the TTL (default 300s). A re-encode already breaks in-flight
  playback, so this is judged acceptable; `hls_cache.clear()` exists if it ever needs a hook.

### 2.4 The connection is now released before any of it

`_video_from_token` returns a frozen `_PlaybackRef` snapshot and calls `await db.close()` **before**
the route touches R2. Hold time is now decided by one query instead of by network latency. The
snapshot (rather than the detached ORM `Video`) is deliberate: it makes a lazy-load off a
connection nobody holds impossible rather than merely unlikely.

Its two `db.get` calls also collapsed into one round trip — same idea as #51, but this time the
round trip it saves is one the connection is genuinely held across.

---

## 3. Instrumentation — every response is now timed

This is §5.2 of the previous handoff, and it is the part to actually trust going forward. Every
number in the whole investigation so far was client-observed wall clock: DNS + TCP + TLS + nginx
accept/queue + upstream, collapsed into one figure with no way to tell which part moved.

`app/core/timing.py` adds two headers to **every** response:

- `X-Process-Time: 0.0143` — total seconds inside the app.
- `Server-Timing: total;dur=14.3, db;dur=1.2, r2_download;dur=8.0, presign;dur=0.4` — per-phase
  milliseconds, which browsers render natively in devtools' network panel.

**The subtraction is the point.** Client-observed 20s minus `X-Process-Time` 0.05s means the app was
never involved and the other 19.95s is network, TLS, nginx queueing, or a per-IP throttle (§6).
Nothing before this could distinguish those.

It is raw ASGI middleware, not `BaseHTTPMiddleware`, on purpose: the latter wraps every request in
an anyio task group and pipes the body through a memory stream, which is real overhead on the exact
event loop under investigation — a measuring instrument that changes what it measures.

Requests over `SLOW_REQUEST_SECONDS` (default 1.0) also log their phase breakdown, because during a
bad burst the interesting requests are the ones whose client gave up before reading any header.

---

## 4. What to measure next, in order

1. **Re-run the VPS-local realistic test.** Then read `Server-Timing` on a few responses. If the
   median has moved and `r2_download` is near zero on all but the first request, the diagnosis in
   §1-2 is confirmed and the cache is doing its job.
2. **Compare `X-Process-Time` against the client-observed number.** This is the measurement the
   investigation has been missing since the start. Whatever gap remains is outside the app, and
   points at §6 rather than at any more code.
3. **Re-run the external-laptop test.** If the in-app time is small but the client still sees 20s+
   and connection failures, that is §6, conclusively, and no further backend work is warranted.
4. **Re-test with a realistically long video, not the 50-second clip.** Per §2.2 the old per-segment
   cost scaled with video length; the batched version should now be flat. Worth confirming rather
   than assuming, since real lectures are ~180 segments and every number in this investigation was
   taken against ~5.

Do all of these against the same `realistic_load.py` and the same N=400 so the numbers stay
comparable to the previous handoff's table.

---

## 5. Tuning knobs added

| Setting | Default | What it does |
|---|---|---|
| `R2_MAX_POOL_CONNECTIONS` | 64 | boto3 HTTP pool per worker. Must stay above anyio's thread limiter (40) or §2.1 comes back. |
| `HLS_OBJECT_CACHE_SECONDS` | 300 | Playlist/key cache TTL. `0` disables the cache entirely. |
| `SLOW_REQUEST_SECONDS` | 1.0 | Slow-request log threshold. `0` disables the log; headers stay on. |

The anyio thread limiter itself (40/worker, 120 app-wide) is left alone. With the cache in place
almost nothing reaches a thread any more, so raising it would be tuning a queue nothing queues on.
`anyio.to_thread.current_default_thread_limiter().total_tokens` is where it lives if that changes.

---

## 6. Still unresolved: the external-client connection failures

**Not investigated in this round — it needs shell access to the VPS, which this round did not have.**

Run 3 of the previous handoff (external laptop, 400 users) produced 16 `ConnectError: All connection
attempts failed`, a failure mode that never appeared in any VPS-local run, plus *worse* overall
numbers than the VPS-local test that was supposed to be the noisier one. Nothing in §1-2 explains
that; those are latency bugs, not connection-refusal bugs.

A burst of ~400 near-simultaneous new TCP/TLS connections from one external IP is the exact shape
`fail2ban`, `ufw` rate limiting, iptables conntrack limits, or an nginx `limit_conn`/`limit_req`
zone would throttle. Read-only commands, still un-run:

```bash
sudo iptables -L -n -v
sudo fail2ban-client status          # then: status <each jail>
grep -rn "limit_req\|limit_conn" /etc/nginx/
sudo ufw status verbose
nginx -V 2>&1 | head -1
grep -n "worker_processes\|worker_connections\|multi_accept" /etc/nginx/nginx.conf
```

**This matters for interpreting the whole test, not just for fixing a bug.** If a per-source-IP
limit is throttling the synthetic test, then the synthetic test is not measuring what competition
day looks like: 400 real students arrive from many different IPs (or a handful of venue NATs), and a
per-IP limit that mangles one laptop's burst may not touch them at all. Understand it before
concluding anything about readiness — in either direction.

Also still unchecked from the previous handoff: nginx's `events {}` block and `worker_connections`
(default 768), which caps accepted connections independently of anything in the backend.

---

## 7. Things already ruled out — do not re-test

Carried forward from the previous handoff, all directly measured:

- **Docker CPU/memory caps** — `ops/deploy-backend.sh` sets no `--cpus`/`--memory`/`--cpuset-cpus`.
  Containers get the full host.
- **Postgres connection *count*** — never above ~40 of 45, mostly idle. (But see §1: "idle" was the
  clue, not the all-clear.)
- **nginx `Connection: close` to upstream** — real bug, fixed (`websocket-upgrade.conf`'s
  `map` sent `close` on every non-WS request); `hey` before/after showed no measurable difference.
  Correct to keep, not the bottleneck.
- **Raw R2 latency** — ~270ms/object measured. Real, but §2.1 explains why it was that high, and
  §2.3 removes almost all of the calls.

Reproducing an R2 measurement from inside the container needs `PYTHONPATH=/app` and `-w /app`;
running a script file directly does *not* put `/app` on `sys.path` the way `-m` or `-c` does. This
cost real time to rediscover once already:

```bash
docker exec -e PYTHONPATH=/app -w /app spacepoint-api python3 -c "
import asyncio, time
from app.services import storage
async def main():
    t0 = time.perf_counter()
    data = await storage.download_file('lms-hls', '<a real playlist_path>', backend='r2')
    print(time.perf_counter() - t0, len(data))
asyncio.run(main())
"
```

---

## 8. Files changed

| File | Change |
|---|---|
| `app/core/timing.py` | **new** — ASGI timing middleware, `phase()` context manager |
| `app/services/hls_cache.py` | **new** — single-flight TTL cache for playlist/key bytes |
| `app/routers/video.py` | `_PlaybackRef` snapshot; release DB before R2; batched presigning; cached playlist/key; phase instrumentation |
| `app/services/storage_r2.py` | `max_pool_connections`; `get_signed_urls()` batch |
| `app/services/storage.py` | `get_signed_urls()` facade, falls back to a loop for non-object-store backends |
| `app/core/config.py` | three settings (§5) |
| `app/main.py` | mount `TimingMiddleware`; expose the timing headers through CORS |

Tests: `tests/services/test_hls_cache.py` (single-flight collapse, cancellation safety, failures not
cached), `tests/routers/test_video_playlist_rewrite.py` (one batched signing call regardless of
segment count; splice order; key line still relative), `tests/core/test_request_timing.py`.

`tests/routers/lms/test_lms_video.py` had one assertion still encoding the **pre-#52** contract
(non-enrolled student with a valid token → 404). It was failing on `main` before this branch —
#52 changed the behaviour deliberately and did not update the test. It now asserts the trade-off
#52 actually made, so reinstating the per-request enrollment check has to be a conscious decision
rather than a silent regression.
