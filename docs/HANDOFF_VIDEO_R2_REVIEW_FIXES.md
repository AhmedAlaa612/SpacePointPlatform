# Handoff: fix 6 findings from a pre-deploy code review of `claude/competition-video-optimization`

**Status:** not started. Written 2026-09-04, against `claude/competition-video-optimization-cm8b21`
at commit `347f19f` (`git diff main...HEAD`, ~21 commits / 118 files).

**Why this doc exists:** the operator is about to deploy this branch's video/R2 work to the VPS
ahead of a 400-student competition in a few days. A `/code-review --level max` pass against
`main...HEAD` came back with 6 findings, verified against the actual code (not just diagnosed from
the diff). This doc hands each one to whoever implements the fix, in enough detail that they don't
need to re-derive the root cause — but the exact fix for #1 and #2 below involves a real design
choice (how to split the ARQ worker), so read the reasoning, don't just pattern-match the code
block.

**Priority order below is deliberate.** #1–#3 are in the exact pipeline the operator is about to
run live and should land before any VPS deploy. #4 is real but currently unreachable from the
frontend. #5–#6 are pre-existing issues in unrelated code (a Roadmap/Design-mission rewrite) that
rode along in this diff only because `main` was behind — fix them if convenient, but they are not
blockers for this deploy and touching them is not required to close this doc.

---

## Read first: how #1 and #2 are connected

`backend/app/workers/main.py` sets `max_jobs = 1` **globally** for the one ARQ worker process,
with a comment explaining *why* — `transcode_video` is CPU-bound and saturates all 4 vCPUs on the
shared VPS, so no concurrent transcodes, ever. That reasoning is correct. What it doesn't account
for is that `max_jobs` is not per-function — it caps the *whole worker's* concurrency, so
`send_ticket_email`, `sync_registration_lms_job`, `send_cohort_interest_notifications`, and the
`heartbeat` cron job all now queue up behind whatever's running too. A single `transcode_video` job
has a 3600s timeout (see the comment right above it in the same file) — during the competition, one
course migration or one guideline-video upload can back up registration emails and LMS syncs for
up to an hour.

The correct fix is to stop sharing one queue between CPU-bound and IO-bound work, which also
happens to make #1 (the deploy preflight) both correct and simple. Do them together:

### Fix for #2 — split the transcode job onto its own low-concurrency queue

1. In `backend/app/workers/main.py`, remove `transcode_video` from the main `WorkerSettings`
   (which also flips back to arq's default concurrency, or an explicit higher `max_jobs` if you
   want to be deliberate about it — the IO-bound jobs here are cheap and short).
2. Add a second `WorkerSettings` class (e.g. `VideoWorkerSettings`) in the same file or a sibling
   module, with `functions = [func(transcode_video, timeout=3600)]`, `max_jobs = 1`, and its own
   `queue_name` (arq's `Worker.__init__`/`RedisSettings` support this — check the installed arq
   version, `arq==0.28.x` per `backend/requirements.txt`, at
   `/usr/local/lib/python3.11/dist-packages/arq/worker.py` for the exact `queue_name` kwarg shape;
   the constant is `arq.constants.default_queue_name = 'arq:queue'`, so pick something like
   `"arq:queue:video"`).
3. `enqueue_transcode` (`backend/app/services/video_service.py:476`) calls
   `safe_enqueue(arq_redis, "transcode_video", ...)` — check `app/workers/settings.py::safe_enqueue`
   for whether it already threads through `_queue_name`/kwargs to `arq_redis.enqueue_job`; if not,
   add a `_queue_name="arq:queue:video"` (or whatever you picked) to that `enqueue_job` call so
   transcode jobs land on the dedicated queue instead of the default one.
4. `ops/deploy-backend.sh` currently runs **one** `spacepoint-worker` container
   (`arq app.workers.main.WorkerSettings`, line 235). It needs a second container,
   `spacepoint-worker-video` (or similar), running `arq app.workers.main.VideoWorkerSettings`,
   recreated with the same zero-downtime swap pattern already used for the main worker (lines
   220–266: start `-new`, wait for `/health/worker`-equivalent, retire the old one). If
   `/health/worker` reads a single heartbeat key, you'll need either a second heartbeat cron job
   scoped to the video worker or a distinct health signal — check
   `backend/app/workers/heartbeat.py` and whatever `/health/worker` reads before assuming one
   heartbeat covers both containers.
5. Update `HANDOFF_VIDEO_R2_EXECUTION.md` §0.3 item 1 and §4.2's `max_jobs = 1` references once
   this lands — that doc currently describes the single-worker shape and will be stale.

**If a full second worker container is more than you want to take on right before the deploy**, the
minimum acceptable fallback is: leave one worker, but raise `max_jobs` (e.g. to 4–6) and instead
make `transcode_video` itself acquire an app-level lock (a Redis key, see Fix for #1 below) so only
one transcode runs at a time while other job types are free to interleave around it. This is a
smaller change but doesn't fix the "one worker process, IO jobs wait behind a live transcode"
problem as cleanly — prefer the queue split if time allows.

### Fix for #1 — deploy preflight must see a swap-in-place re-encode

`ops/deploy-backend.sh:82-89` checks `SELECT count(*) FROM videos WHERE status='processing'`. But
`run_encrypted_transcode` (`backend/app/services/video_service.py:532`) computes:

```python
swap_in_place = bool(video.playlist_path) and video.status == "ready" and target != video.storage_backend
if not swap_in_place:
    video.status = "processing"
    ...
```

— a re-encode of an already-`ready` video onto a *different* backend (exactly what "Migrate to R2"
and `--reencode` do) deliberately **never** sets `status = "processing"`, by design (so students
keep watching the old copy while the new one encodes — see that function's own comment). The DB
alone cannot tell "idle" from "mid-swap-in-place-reencode" for a `ready` row. The deploy preflight
is blind to exactly the case this branch introduces.

Don't try to infer this from arq's internal Redis keys (`arq:in-progress:{job_id}` — checked while
writing this doc, see `arq.constants.in_progress_key_prefix`; the key doesn't encode which function
or queue the job belongs to, so filtering it down to "specifically a transcode" means deserializing
`arq:job:{job_id}` and is more fragile than it's worth). Instead, add an explicit, app-owned lock:

1. In `run_encrypted_transcode`, right after resolving `target`/`swap_in_place` (video_service.py
   ~line 530) and before the `try:` block that downloads/encodes, set a Redis key such as
   `SETEX transcoding:{video_id} <job_timeout_seconds> 1` (reuse whatever Redis client the worker
   already holds — `app/workers/settings.py` or the `arq_redis` connection). Delete it in a
   `finally` around the existing try/except/except (currently at lines 538–606) so it's cleared on
   success, failure, and cancellation alike. Use `finally`, not a delete at the end of the `try`,
   or a cancelled/failed job leaves the lock stuck until the SETEX TTL expires — which is why the
   TTL should match the job's own 3600s timeout as a backstop, not rely on the `finally` alone.
2. In `ops/deploy-backend.sh`'s `preflight()`, alongside the existing `status='processing'` query,
   add a check for any `transcoding:*` key: `redis-cli -u "$REDIS_URL" --scan --pattern
   'transcoding:*' | wc -l` (source `REDIS_URL` from `$ENV_FILE`, or resolve it the same way the
   script already resolves DB access — check whether `redis-cli` is installed on the VPS host or
   whether this needs to run via `docker exec` into a running container instead, since the deploy
   host itself may not have Python/redis-cli). Treat a nonzero count the same as the existing
   `processing` count — `drift=1`, refuse to proceed without `--check`.
3. Update the preflight's echoed warning text (lines 86–88) to mention swap-in-place re-encodes,
   not just fresh transcodes, so whoever reads the output understands why it's blocked.

Verify by starting a `--reencode` job against a `ready` video, confirming the row's `status` stays
`"ready"` in Postgres the whole time (proving the blind spot is real), confirming the new
`transcoding:{id}` key exists in Redis while it runs, and confirming `deploy-backend.sh --check`
now reports drift while it's set and clean once it clears.

---

## #3 — "Migrate to R2" can double-encode a video still on its first transcode

**File:** `backend/app/routers/lms/admin.py:880-895` (`migrate_course_videos_to_r2`)

```python
rows = (await db.execute(
    select(Video)
    .join(ModuleItem, ModuleItem.id == Video.owner_id)
    .join(CourseModule, CourseModule.id == ModuleItem.module_id)
    .where(
        Video.owner_type == "module_item", Video.upload_mode == "hls_encrypted",
        CourseModule.course_id == course_id,
    )
)).scalars().all()

already_on_r2 = sum(1 for v in rows if v.storage_backend == "r2")
to_migrate = [v for v in rows if v.storage_backend != "r2"]
for video in to_migrate:
    await enqueue_transcode(arq_redis, video.id, target_backend="r2")
```

This only filters on `storage_backend != "r2"`. A video whose *first-ever* transcode is still
running (`status` in `("pending", "processing")`, `storage_backend` still `None`/`"vps"`) is
included, so clicking "Migrate to R2" while a fresh upload is still processing queues a second
`transcode_video` job for the same video id. With `max_jobs=1` (or even after the #2 fix, since the
video queue is still serial by design) the second job runs immediately after the first finishes,
silently re-encoding the same source again — wasted CPU time during exactly the window you're
trying to conserve it in.

**Fix:** exclude in-flight rows from `to_migrate`:

```python
to_migrate = [v for v in rows if v.storage_backend != "r2" and v.status not in ("pending", "processing")]
```

Decide what `MigrateCourseVideosOut` should report for the excluded rows — right now it only has
`queued`/`already_on_r2`; consider adding a third count (e.g. `still_processing`) so the admin UI
can show *why* a video wasn't queued, rather than it silently not appearing in `queued`. Check
`frontend/src/api/lms_admin.ts` / wherever `MigrateCourseVideosOut` is consumed to see if the extra
field needs UI work or can just be logged for now.

Verify by uploading a video, immediately (before its transcode finishes) hitting
`POST /courses/{id}/videos/migrate-to-r2`, and confirming only one `transcode_video` job total ever
runs for that video (check ARQ job history / worker logs, not just the response body).

---

## #4 — admin guideline-video preview endpoint always returns an empty URL

**File:** `backend/app/routers/lms/admin.py:1708-1722` (`get_program_item_guideline_video_url`)

```python
async def get_program_item_guideline_video_url(...) -> dict[str, str]:
    ...
    info = await get_playback_info(db, video)
    return {"url": info.get("url") or ""}
```

Every guideline video reachable here was uploaded with `mode="hls_encrypted"` — hardcoded in
`upload_program_item_guideline_video` earlier in the same file. `get_playback_info()`
(`video_service.py`) has no `"url"` key in its return dict for `hls_encrypted` mode (only `embed`,
`direct`, and `hls_encrypted` shapes exist, and `hls_encrypted`'s shape carries `video_id` +
`status`, not a bare `url` — see the student-facing twin in `routers/lms/student.py` for the
correct pattern). So this endpoint's `url` is always `""`, regardless of whether the video finished
processing.

**Currently low-risk**: grep the frontend for callers of
`getLmsProgramItemGuidelineVideoUrlApi` (`frontend/src/api/lms_admin.ts`) — as of this branch it's
exported but not called from any component, so nothing user-facing is broken today. Fix it anyway
so it doesn't bite whoever wires up an admin preview next:

```python
return {"url": info.get("url") or "", "video_info": info}
```

matching the shape `routers/lms/student.py::program_item_guideline_video_url` and
`routers/instructors/training.py::stream_video` already use, and update the response type
annotation (`-> dict[str, str]` is now wrong) and the frontend API type in
`frontend/src/api/lms_admin.ts` to match `VideoPlaybackInfo`. Check whether an admin-side player
component should also be wired up to actually use `video_info` while you're in there, or leave that
as a separate follow-up if out of scope.

---

## #5 — confirm_design_step's auto-finalize can eat a legitimate step confirmation

**Files:** `backend/app/routers/missions/design.py:560-598` (`confirm_design_step`),
`backend/app/services/missions/verifiers/design.py:47-65` (`mark_design_complete`)

**Not related to the video work** — this is in the Roadmap/Design-mission rewrite that came along
because `main` was behind this branch. Fix if convenient; not a deploy blocker for the video
migration.

`confirm_design_step` computes its own dashboard, checks `required <= confirmed and
dash["all_valid"]`, and if true calls `mark_design_complete(db, attempt=attempt)`. But
`mark_design_complete` (verifiers/design.py:60) *independently recomputes* the dashboard and
re-checks `all_valid` itself, raising `HTTPException(400, ...)` if it's now false — and that
`HTTPException` is not caught anywhere in `confirm_design_step`, so it propagates out of the route,
aborting the whole request. Because the DB session hasn't committed yet (the `design.confirmed_steps`
change at line 574-575 was only `flush()`ed, not `commit()`ed — `commit()` happens at line 597,
after the auto-finalize block), the step confirmation itself gets rolled back too. A student whose
confirm click was legitimately valid at the time they clicked can lose that confirmation entirely
if state changes between the two dashboard computations (e.g. a teammate edits/removes a component
in the same window).

**Fix:** don't let a stale-by-the-time-we-get-there auto-finalize attempt take down an otherwise-valid
step confirmation:

```python
if required <= confirmed and dash["all_valid"]:
    try:
        await mark_design_complete(db, attempt=attempt)
    except HTTPException:
        # Valid when we checked above; became invalid before mark_design_complete's own
        # recompute (concurrent edit). The step confirmation above still stands — just
        # don't auto-finalize this time. The student (or next confirm) gets another shot.
        pass
```

Verify with a test that flushes a step confirmation, mutates the design (e.g. removes a component)
between the two dashboard computations — you may need to call `compute_dashboard` /
`mark_design_complete` directly in a test rather than relying on real request timing — and confirms
the response is 200 with the step marked confirmed, not a 400 that also lost the confirmation.

---

## #6 — dead `max_depth_of_discharge_pct` threshold (optional cleanup)

**File:** `backend/app/services/missions/design/service.py:89` (`variant_thresholds`)

**Not related to the video work, not a bug** — this key is computed and returned in every
dashboard's `thresholds` dict, but nothing reads it back out anymore (confirmed by grep: no other
file under `backend/app/services/missions/design/` references
`max_depth_of_discharge_pct`/`depth_of_discharge`/`dod_pct`). It was the threshold for
`calc_energy_budget`/`EnergyBudgetResult`, which this same branch's Design-mission rewrite removed
entirely (see `backend/alembic/versions/e7b2f14a9c60_design_battery.py`'s own docstring for the
Energy & Battery budget's removal).

**This is genuinely optional** — leaving it costs nothing functionally, it's just a value nobody
consumes anymore. If you do clean it up: remove the line from `variant_thresholds()`, and decide
whether to also touch `backend/scripts/missions_seed_design.py` (still sets this key on seeded
variant configs) and the two test fixtures that assert on it
(`backend/tests/routers/lms/test_lms_program_student.py:39`,
`backend/tests/routers/missions/test_missions_design_v2_router.py:45`) — those will need updating
in the same change if `thresholds` output shape changes, or can be left alone if you only strip the
dead *consumption* and leave the config key itself as inert data. Confirm which by checking whether
`thresholds` is asserted against a fixed dict shape in those tests or just spot-checked for specific
keys.

---

## Go/no-go for this doc

- [ ] #1 — deploy preflight detects an in-flight swap-in-place re-encode (Redis lock added, script
      checks it, verified against a real running `--reencode`)
- [ ] #2 — `transcode_video` no longer shares a worker queue with IO-bound jobs (or, at minimum,
      the fallback lock-based approach is in place and documented)
- [ ] #3 — `migrate_course_videos_to_r2` excludes videos still on their first transcode
- [ ] #4 — admin guideline-video URL endpoint returns `video_info`, matching its student-facing twin
- [ ] #5 — `confirm_design_step` catches `mark_design_complete`'s `HTTPException` instead of losing
      the step confirmation (optional — not a video-deploy blocker)
- [ ] #6 — dead threshold removed or explicitly left as documented inert config (optional)
- [ ] `HANDOFF_VIDEO_R2_EXECUTION.md` updated wherever it describes the single-worker /
      `max_jobs=1`-for-everything shape, if #2 changes that
- [ ] Re-run `/code-review --level max` against `main...HEAD` after these land, to confirm nothing
      new was introduced and nothing here was missed
