# Video playback load investigation — competition-day readiness

**Status: UNRESOLVED.** Written 2026-09-05, after PR #44 (R2/compression rollout), PR #51 (query
collapse), and PR #52 (drop redundant re-check) all deployed and live. The realistic end-to-end
load test still shows 13-23s median latency for a video to become playable under a synchronized
400-user burst. Two real fixes landed and neither meaningfully moved that number — the dominant
bottleneck is still unidentified. Competition is in a few days.

**Audience:** an agent (or the same one, later, with fresh context) continuing this investigation.
Read this fully before running another test — several plausible-looking hypotheses below were
already tested and ruled out; don't re-spend time on them.

---

## 0. The actual production question

400 students will watch course videos concurrently in a few days. The thing that matters is: when
a student clicks play, how long until video actually plays, under a realistic burst of ~400
students doing that within a few seconds of each other? "A few seconds" is fine. What we're
currently measuring is a **13-23 second median**, which is not fine, and we don't yet know why.

---

## 1. The real request sequence (this matters — see §3)

A real browser does **three** sequential, dependent calls per video start, not one:
1. `GET /videos/{id}/token` (Authorization: Bearer <student JWT>) → mints a short-lived
   (`_VIDEO_TOKEN_MINUTES = 4*60`, 4h) signed video token.
2. `GET /videos/{id}/playlist?token=<from step 1>` → fetches and rewrites the `.m3u8` playlist.
3. `GET /videos/{id}/key?token=<from step 1>` → fetches the AES-128 decryption key.

All three live in `backend/app/routers/video.py`. Segments (the actual `.ts` video bytes) are
**not** among these three for an R2-backed video — the rewritten playlist points hls.js straight at
presigned R2 URLs, bypassing the API entirely for segment data.

---

## 2. Fixes already made, and their actual measured effect

### 2.1 nginx keepalive-to-upstream fix (no measurable effect)

Found: `/etc/nginx/conf.d/websocket-upgrade.conf` had
```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
```
which sends `Connection: close` to the FastAPI upstream on every non-WebSocket request (the
classic copy-pasted WS-proxy snippet, applied unmodified). Changed `close` → `""` so ordinary API
requests can reuse a persistent connection to uvicorn.

**Effect: none.** `hey -n 4000 -c 400` against `/videos/{id}/token` before and after this change
were statistically identical (~1.5s avg both times). Correct fix to keep, but not the bottleneck.

### 2.2 PR #51 — collapse `_check_module_item` into one joined query

Was: `db.get(ModuleItem)` → `db.get(CourseModule)` → `select(Enrollment)`, three sequential round
trips. Now: one joined query. Merged and deployed.

**Effect: modest.** Single-endpoint `hey -c 400` against `/token` alone: avg 1.548s → 1.469s
(~5% better), throughput 227 → 261 req/s. Real but small.

### 2.3 PR #52 — stop re-running the full enrollment check on playlist/key/segment

Found: `_video_from_token` (used by `playlist`, `segment`, `key`) called `_load_and_check`, which
re-runs the **entire** owner-type access check (the enrollment join, or instructor/guideline
checks) on every call — not just once at token-mint time. A realistic click→token→playlist→key
sequence was paying that check 3x per video start. Fixed: `_video_from_token` now does a plain
`db.get(Video, video_id)`, keeping the token signature/expiry check, video-id-match check, and
user-still-exists check, but dropping the redundant owner-type re-check. Documented trade-off:
revoking enrollment mid-session no longer cuts playback instantly, only at token expiry (4h).

**Confirmed actually deployed** — verified directly, not assumed:
```
docker exec spacepoint-api grep -n "_load_and_check\|db.get(Video, video_id)" /app/app/routers/video.py
```
showed `_load_and_check` only at the `/token` route, and `db.get(Video, video_id)` inside
`_video_from_token` (line ~193). Image build time (22:42:42) and container creation time
(22:46:14) both postdate the PR #52 merge.

**Effect: none, arguably worse.** Realistic sequential test (see §3) was *not* meaningfully better
after this fix, and one variant of the retest actually came back slower. This is the confusing part
— removing 2 of 3 expensive DB-heavy calls per video start should have helped substantially if DB/
ORM overhead were the dominant cost, and it visibly didn't.

---

## 3. The realistic load test — results, in order, all at N=400

Script (`realistic_load.py`, both variants below): `httpx.AsyncClient` with explicit
`Limits(max_connections=N, max_keepalive_connections=N)` (default is only 100 — already corrected
for), N simulated users each doing token→playlist→key in sequence with `random.uniform(0, 1.5)`s
jitter before starting (to mimic real staggered clicks, not a perfectly synchronized instant).
Reports per-user end-to-end wall time from click to key-in-hand (i.e., video ready to decrypt/play).

| Run | Where client ran | Which fixes live | succeeded/failed | avg | p50 | p90 | p99 | max |
|---|---|---|---|---|---|---|---|---|
| 1 | VPS, inside `spacepoint-api` container | #51 only (pre-#52) | 400/0 | 11.468s | 13.280s | 15.660s | 16.173s | 16.345s |
| 2 | VPS, inside `spacepoint-api` container | #51 + #52 | 400/0 | 13.205s | 13.480s | 17.756s | 19.527s | 19.589s |
| 3 | External: user's Windows laptop, real WAN | #51 + #52 | **384/16** | 20.282s | 23.041s | 28.814s | 33.316s | 34.261s |

Run 3's 16 failures were all `ConnectError: All connection attempts failed` — a failure mode that
**never appeared** in runs 1-2. This is new and unexplained.

**Why run 2 vs run 1 is confusing**: #52 removed 2 of 3 expensive enrollment-check DB round trips
per user, and the realistic test got *worse*, not better. This means DB/ORM overhead — the thing
both #51 and #52 targeted — is very likely **not** the dominant cost in this test. Something else
is, and it hasn't been identified yet.

**Why run 3 vs run 2 is confusing**: the working theory going into run 3 was "the load-generator
script running inside the same container as the server competes with it for the same 4 vCPUs,
inflating the VPS-local numbers." Testing from a genuinely separate machine (the user's laptop)
was supposed to produce a *cleaner, likely better* number. Instead it came back **worse**, plus
real connection failures. This weakens (doesn't fully rule out — see §5.1) the client-CPU-
contention theory, and surfaces a new question: something about a burst of ~400 near-simultaneous
new connections from **one external client IP** may be hitting a limit or protection that a
VPS-local test (loopback-adjacent, or at least not "one external IP") never triggers.

For contrast, the single-endpoint (`/token` only) `hey` tests never showed this cliff:
- `hey -c 400` (post-#51): avg 1.469s, p99 3.476s, 4000/4000 succeeded.
- `hey -c 1000` (post-#51): avg 3.826s, p99 5.954s, 4000/4000 succeeded, throughput flat at ~230
  req/s regardless of concurrency (confirms a real, stable capacity ceiling, not a cliff).

So: hitting **one** endpoint at 1000 concurrent, from an external client, degrades gracefully with
zero errors. Hitting the **real 3-endpoint sequence** at 400 concurrent, from an external client,
degrades to 20s+ median with real connection failures. The gap between those two results is the
actual mystery — it's not fully explained by "3x the requests" (that alone would predict roughly
3x the single-endpoint latency, i.e. ~4-5s, not 20s+).

---

## 4. Things directly measured and ruled out (don't re-test these)

- **Docker CPU/memory caps**: `ops/deploy-backend.sh`'s `docker run` commands for
  `spacepoint-api`/`spacepoint-worker`/`spacepoint-worker-video` have no `--cpus`, `--memory`, or
  `--cpuset-cpus` flags. Containers have full access to the host's vCPUs. Confirmed by reading the
  script directly, not inferred.
- **Postgres connection pool exhaustion**: `pg_stat_activity` sampled mid-burst (single-endpoint
  test era) showed at most ~40 of 45 app-side pool slots in use, most `idle` — never saturated. Also
  `wait_event=ClientRead` on active sessions, meaning Postgres was idle waiting on the app, not
  the other way around.
- **R2 network latency / thread-pool ceiling** — measured directly (see below), real but small
  relative to the 13-23s numbers:
  - `anyio.to_thread.current_default_thread_limiter().total_tokens` = **40** per worker process
    (× 3 uvicorn workers = 120 total concurrent R2-bound operations app-wide). This is anyio's
    default, never explicitly configured — a real, tunable value if it ever needs to go higher.
  - Single **cold** R2 download of the test video's 357-byte playlist: 0.530s (mostly first-
    connection TLS/DNS setup cost).
  - Same download, **warm**, repeated 5x in the same process: 0.265-0.285s each, consistent.
  - 20 **concurrent** warm downloads (`asyncio.gather`, same process): all 20 finished in 0.588s
    total — parallelizes fine at this scale, no obvious queuing blow-up.
  - Rough math: 400 users × 2 R2 calls (playlist + key) ÷ ~120 available threads × ~270ms/call ≈
    under 2s worst case if this were the only factor. Real, but not close to explaining 13-23s.
  - Reproduce with `backend`'s own storage service, from inside the container
    (`PYTHONPATH=/app`, cwd `/app` — running a script file directly does NOT put `/app` on
    `sys.path` the way `-m` or an interactive `-c` would; this cost real time to figure out, don't
    re-discover it):
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
- **nginx `Connection: close` on every request** (§2.1) — fixed, confirmed via `hey` before/after,
  no measurable effect on latency either way.

---

## 5. Open hypotheses — not yet tested, in rough priority order

### 5.1 Per-source-IP protection at the network layer (highest priority — explains the NEW failures)

Run 3's 16 `ConnectError`s, and its overall worse numbers vs. even the VPS-local run, are the single
most concrete anomaly here. A burst of ~400 near-simultaneous new TCP/TLS connections from **one
external IP** (the laptop) is exactly the shape of traffic that `fail2ban`, `ufw` rate-limiting,
`iptables` conntrack limits, or an nginx `limit_conn`/`limit_req` zone would treat as suspicious and
throttle or drop — and none of the VPS-local tests (runs 1-2) would ever trigger this, because they
either use loopback or don't originate from a single "foreign" IP in the same way. This was **not
yet checked** in this investigation. Check on the VPS:
```bash
sudo iptables -L -n -v
sudo fail2ban-client status
sudo fail2ban-client status sshd   # or whatever jails exist — check each
grep -rn "limit_req\|limit_conn" /etc/nginx/
sudo ufw status verbose
```
If something here is rate-limiting by source IP, that would explain both the connection failures
and why external-client numbers are worse than VPS-local ones. It would also mean **the real
production risk is different from what we've been testing** — 400 real students each come from
different IPs (or at most small clusters sharing a venue's WiFi NAT), so a per-IP limit that
throttles our single-laptop synthetic test might not throttle real traffic at all. This needs to be
understood, not just patched, before concluding anything about real readiness.

### 5.2 No server-side request timing exists anywhere

Every single number in this whole investigation (this doc included) is **client-observed wall-clock
time** — it conflates DNS, TCP/TLS handshake, network RTT, nginx queuing, and actual backend
processing into one figure. There is no `X-Process-Time` response header, no access log with
`$request_time`/`$upstream_response_time`, nothing that isolates "how long did the backend itself
take" from "how long did everything around it take." This is very likely the highest-leverage next
step: add temporary timing instrumentation (a FastAPI middleware measuring wall time inside the
app, logged or returned as a response header) and re-run the exact same tests. That would finally
tell us whether the 13-23s is being spent inside the app/DB, or upstream of it (nginx, network,
TLS, or the per-IP throttling in §5.1).

### 5.3 nginx's own `worker_connections`/`worker_processes`/listen backlog — never inspected

This whole investigation checked the `location /api/` proxy block and the WebSocket-upgrade `map`,
but never looked at the `events {}` block or `worker_processes` directive in `nginx.conf` itself.
Worth a look:
```bash
nginx -V 2>&1 | head -1
grep -n "worker_processes\|worker_connections\|multi_accept" /etc/nginx/nginx.conf
```
A too-low `worker_connections` (default 768) combined with a low `worker_processes` count could
cap total concurrent connections nginx will even accept, independent of anything on the backend.

### 5.4 Re-verify #52's deployment produced the expected DB-side reduction

We confirmed the *code* is deployed (§2.3) but never re-confirmed the *effect* at the DB level —
e.g., re-sample `pg_stat_activity` mid-burst after #52 and compare active/idle-in-transaction counts
to the pre-#52 baseline. If DB load genuinely dropped as expected but end-to-end latency didn't
move, that's strong independent confirmation the bottleneck is elsewhere (supports §5.1/§5.2/§5.3
over any remaining DB-side theory).

### 5.5 Test-harness quirks worth double-checking, lower priority

- `MAX_JITTER = 1.5` seconds in the realistic script is still a fairly tight synchronized window —
  worth trying a wider jitter (e.g. 3-5s) to see if the shape changes, since real students clicking
  play in response to an instructor's "go" will likely spread out more than 1.5s in practice.
- Windows' own ephemeral port range / `TcpTimedWaitDelay` can constrain how many near-simultaneous
  outbound connections one machine can open — worth ruling out with a smaller N (e.g. 100) from the
  same laptop to see if failures still occur, which would point at the client OS rather than the
  server.

---

## 6. Recommended next steps, in order

1. Check §5.1 (per-IP network-layer limits) first — it's the most concrete, most likely to explain
   both the new connection failures and the external-vs-internal discrepancy, and is a quick set of
   read-only commands, not a code change.
2. If nothing in §5.1 explains it, add the timing middleware from §5.2 and re-run — this finally
   separates "backend is slow" from "everything around the backend is slow," which nothing so far
   has actually distinguished.
3. Only after 1-2 give a real answer, decide whether more code changes (further query optimization,
   R2 thread-pool tuning, nginx tuning) are actually warranted — two rounds of plausible-looking
   code fixes (#51, #52) already went in without moving the real number, which is a strong signal
   to stop guessing at code changes and find the actual bottleneck first.
4. Re-run the realistic test (VPS-local AND external-laptop variants, both) after each change to
   keep the two data points comparable to this doc's baseline.

---

## 7. Reference: exact commands used, for reproducing any measurement above

- Get a fresh student JWT (works from VPS or laptop, adjust host accordingly):
  `POST /auth/login` with `{"email": "edabdelaal@gmail.com", "password": "test123"}`, read
  `.access_token` from the response.
- Test video used throughout: `48775531-1332-4493-9508-87eda849b0c5` (a `module_item`-owned,
  `ready`, R2-backed video — the first video in the Introduction course, found via joining
  `courses` → `course_modules` → `module_items` → `videos`).
- Single-endpoint synthetic tool: `hey -n 4000 -c <N> -H "Authorization: Bearer $TOKEN"
  https://portal.spacepoint.ae/api/videos/<id>/token`.
- Realistic multi-step tool: `realistic_load.py` (§3) — run inside `spacepoint-api`
  (`docker exec -e TOKEN=... -e USERS=400 spacepoint-api python3 /tmp/realistic_load.py`) or from an
  external machine with `httpx` installed, hitting the public `https://portal.spacepoint.ae` domain
  either way (never bypass nginx for this one — the whole point is testing the real path).
