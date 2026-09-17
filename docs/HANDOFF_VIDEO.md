# Video Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

**Status as of 2026-09-17: one shared video pipeline serves every feature that plays a video** —
LMS course module videos, Library resources, checklist guideline videos, and facilitator Training
videos all go through `backend/app/models/videos.py` (`Video`) + `backend/app/services/
video_service.py`, with a single owner-type-agnostic playback surface at `backend/app/routers/
video.py` (`/videos/{video_id}/token|playlist|segment/{name}|key`). This doc is the living
replacement for what used to only exist as event-specific migration runbooks — see
`docs/archive/HANDOFF_VIDEO_R2_EXECUTION.md` and `docs/archive/HANDOFF_COMPETITION_DAY_DEPLOY.md`
(both retired, moved to `docs/archive/` on this date, kept for historical rationale only) and
`docs/archive/HANDOFF_VIDEO_R2_REVIEW_FIXES.md` (a pre-deploy code-review punch list — every
finding in it has landed; §"What changed since the R2 migration runbooks" below cross-references
which). Everything below was verified against the code as of 2026-09-17, not copied from those
archived docs — several things changed shape between the plan and what's actually shipped (see
that section).

---

## 1. The shape: one `videos` table, four owner types, three provider/mode combinations

`backend/app/models/videos.py`. One `Video` row per `(owner_type, owner_id)` pair
(`UniqueConstraint("owner_type", "owner_id")` — replacing a row upserts in place, it never
accumulates history):

| `owner_type` | What it is | Attached from |
|---|---|---|
| `module_item` | An LMS course module's video item | `POST /lms/admin/items/{item_id}/video` (`routers/lms/video.py`) |
| `library_resource` | An Instructor Library resource that's a video | `routers/instructors/facilitator.py` (link/upload/embed, three-way toggle) |
| `program_item_guideline` | A checklist item's guideline video | `routers/lms/admin.py` (`upload_program_item_guideline_video`) |
| `training_video` | A facilitator Training video | `routers/instructors/facilitator.py` |

A row is one of three shapes, distinguished by `provider`/`upload_mode`:

- **`provider="youtube"|"vimeo"`** — `embed_url` holds the pasted link verbatim, played as an
  iframe (`frontend/src/lib/embed.ts::toEmbedUrl`). Nothing async: `status="ready"` immediately.
  Detected by `video_service.py::_detect_provider()`'s host regex, which must be kept in sync by
  hand with `frontend/src/lib/embed.ts::isKnownEmbedHost` — no shared source between the two
  languages (the same duplication pattern this codebase already uses for `_VIDEO_FORMATS`).
- **`provider="upload", upload_mode="direct"`** — `source_bucket`/`source_path` point at the
  uploaded file itself, served as a plain signed URL, byte-range playback only, no transcode.
  `status` flips to `"ready"` the moment the upload lands. This mode predates the R2 migration and
  is legacy at this point — see §3, every upload endpoint now requests `hls_encrypted` directly;
  `direct` only survives on rows uploaded before that switch (or where `--convert` hasn't reached
  them yet, per `scripts/video_migrate_to_r2.py`).
- **`provider="upload", upload_mode="hls_encrypted"`** — `source_bucket`/`source_path` are the
  pre-transcode source; `playlist_path`/`key_path` are the AES-128-encrypted HLS output an ARQ
  worker produces. `status` spends real time in `"processing"` here (`pending` → `processing` →
  `ready`/`failed`).

`status` is one of `pending|processing|ready|failed`, with `status_error` holding the exception
text (truncated to 2000 chars) on failure. `duration_seconds` is populated by ffprobe during
transcode (or left null for `direct`/embed).

**Naming note, since it trips up anyone reading the archived R2 runbooks**: PR #43
("Standardize video handling") renamed the pre-existing `ModuleVideo`/`module_videos` table to
`Video`/`videos`, `.item_id` → `.owner_id`, and `.transcode_status`/`.transcode_error` →
`.status`/`.status_error`. Everything in this doc already uses the current (post-#43) names — the
table above from the archived execution doc is the one place you'd still need it, and it's
reproduced there for exactly that reason.

---

## 2. Storage-backend routing — per video row, not a global switch

`Video.storage_backend` is `NULL` (VPS/local disk) or `"r2"` (Cloudflare R2) — **a fact about one
row's bytes, not a deployment-wide setting.** Two videos can be on different backends at the same
time; nothing forces an all-or-nothing cutover. See `app/models/videos.py`'s own comment on the
column for the full reasoning, and `app/services/storage.py`'s module docstring for the facade
this rides on (every storage function takes an optional `backend=` override; every caller except
the video path passes nothing and is unaffected).

**What actually decides where bytes go, read straight from the code:**

- **Every new upload — any `owner_type`, any mode — targets R2 unconditionally.**
  `video_service.py::_NEW_UPLOAD_BACKEND = "r2"`, set on `attach_upload()`'s `video.storage_backend`
  before the source bytes are written. This is **not** the `VIDEO_STORAGE_BACKEND` setting
  (`storage.py::default_video_backend()`, which still exists in `core/config.py` but is
  deliberately *not* what `video_service.py` reads for this) — the comment on
  `_NEW_UPLOAD_BACKEND` is explicit about why: a blank setting must not silently revive VPS
  uploads, so the target is hardcoded, and a deployment missing R2 credentials fails loudly on the
  first real upload instead of quietly writing to disk. VPS was a bootstrapping default from
  before R2 existed; the product no longer offers it as an upload destination anywhere.
- **Pre-existing rows stay wherever they were until something explicitly moves them** — a
  `--move`/`--reencode` run (`scripts/video_migrate_to_r2.py`, §5) or the admin "Migrate to R2"
  button (`POST /lms/admin/courses/{course_id}/videos/migrate-to-r2`, one course at a time).
- **What `storage_backend` actually governs differs by mode** (`video_service.py::_hls_backend`/
  `_source_backend`):
  - `hls_encrypted`: governs the HLS **output** (playlist/segments/key) — the served asset.
    `source_bucket`/`source_path` (the pre-transcode upload) always stay on the **default**
    backend regardless of the row's `storage_backend`, because only the ARQ worker ever reads
    them — a student request never touches the source, so there's no reason to ship it to an
    object store.
  - `direct`: governs the **source** — because in this mode the source IS the asset the browser
    fetches. This matters concretely: served from local storage, `direct` playback goes through
    `GET /files`, which Fernet-decrypts the *whole* blob into memory and answers one non-range
    response. A `<video>` element needs byte ranges (the moov atom at the end of any
    non-`+faststart` MP4, and every seek) — against a non-range origin each of those restarts the
    entire download, which presents as "flashes one frame, drops back to buffering forever." An
    object store answers ranges natively; that's the actual fix `--move --to r2 --mode direct`
    provides for old `direct` uploads.
  - Embed links (`youtube`/`vimeo`) host no bytes of the platform's own — `storage_backend` is
    irrelevant for them, and `move_to_backend()` is a no-op (`"skipped": "embed link"`).

**R2 mechanics** (`backend/app/services/storage_r2.py`): S3-compatible via boto3, one real R2
bucket (`R2_BUCKET`) holds everything — the app's own bucket names (`lms-hls`, `video-sources`,
...) become key prefixes (`f"{bucket}/{path}"`), so the six-function storage interface stays
identical whether the target is local disk, Supabase, or R2. Three R2-specific pins that matter:
`region_name="auto"` (R2 has no real regions, but SigV4 needs *something*), `signature_version=
"s3v4"` + `addressing_style="path"` (boto3's defaults drift toward virtual-host addressing, which
R2's endpoint doesn't serve), and presigned URLs capped at 7 days (`_MAX_PRESIGN_SECONDS`, AWS
SigV4's hard limit) — unlike local storage's ~10-year signed URLs, so R2 URLs must always be
re-signed at query time via `get_signed_url()`/`resolve_url()`, never stored as long-lived.
**Deliberately no Fernet encryption on R2** — objects are encrypted at rest by Cloudflare, the
bucket is private, access is presigned-URL-gated, and HLS segments are already AES-128 encrypted
by the transcode step regardless (see §4) — layering Fernet on top would also defeat the entire
point of the migration, since a Fernet blob can't be range-requested or played by a browser
without being proxied back through the API first.

**Buckets in use** (constants read from the code, not restated from memory):
`video_service.py::SOURCE_BUCKET = "video-sources"` (pre-transcode sources),
`video_service.py::HLS_BUCKET = "lms-hls"` (HLS output — **kept under its original LMS-only name
on purpose**; the code comment explains that renaming it once already broke playback of every
pre-existing video, since neither old nor new code persists the bucket name per row, they just
hardcode the constant and assume every row's `playlist_path`/`key_path` lives under it — do not
"clean this up").

---

## 3. Upload / ingest

Every upload endpoint (module video, Library, checklist guideline, Training) is a thin wrapper
over `video_service.py::attach_upload()`, capped at **4GB** app-level (`MAX_UPLOAD_BYTES`/
`MAX_LIBRARY_FILE_BYTES` = `4 * 1024 * 1024 * 1024`, checked in every one of
`routers/lms/video.py`, `routers/lms/admin.py`, `routers/instructors/facilitator.py` — confirmed
the same constant value in all three files). `attach_upload()`:

1. Upserts the one `Video` row for `(owner_type, owner_id)` — if one already exists,
   `_delete_storage()` best-effort-cleans up its old storage objects first (never raises; a
   storage 404 on an already-gone object shouldn't block the DB write).
2. Sets `storage_backend = "r2"` (`_NEW_UPLOAD_BACKEND`, §2) **before** uploading, since
   `_source_backend()` reads `upload_mode`/`storage_backend` off the row to decide where the bytes
   land — setting it after would upload to the wrong place.
3. Uploads to `{SOURCE_BUCKET}/{video.id}/source{ext}`. For `mode="direct"` this is the asset
   itself and `status` flips straight to `"ready"`. For `mode="hls_encrypted"` `status="pending"`
   and the caller is responsible for calling `enqueue_transcode()` separately — kept as a
   deliberate split so `attach_upload()` stays a pure DB+storage primitive, testable without a
   Redis dependency.

**Known real fix, currently live**: `--convert`/`--reencode` originally called
`redis.enqueue_job()` without `_queue_name="arq:queue:video"`, so jobs landed on arq's default
queue that neither worker drains — they'd sit `status='pending'` forever with no error anywhere.
Fixed (`scripts/video_migrate_to_r2.py::convert()`/`reencode()` and
`video_service.py::enqueue_transcode()` all pass `_queue_name="arq:queue:video"` explicitly today,
confirmed by reading the code). If a video is ever seen stuck `pending` for more than a couple of
minutes, that's still the first thing worth checking — re-running `--reencode --video-id <id>`
re-enqueues it correctly.

**Streaming uploads**: still not done. `data = await file.read()` reads the whole file into
memory before handing it to `attach_upload()` (confirmed present in `routers/lms/video.py`,
`routers/lms/admin.py`, `routers/instructors/facilitator.py`) — two full copies in RAM on a box
that doesn't have much to spare. Flagged as a real risk in the archived R2 execution plan's §6.3
("not a competition risk if nobody uploads during the event; a real risk the moment someone
does") and **still true today** — nothing in the code changes this.

---

## 4. Transcode pipeline

`video_service.py`'s `_ffmpeg_encode_hls_sync()`/`run_encrypted_transcode()`, run inside the ARQ
job body `workers/tasks/video.py::transcode_video()`.

### Probe → remux-or-encode decision

One `ffprobe` call (`_probe_source()`) replaces what used to be three separate probes — codec ×2
plus duration — a deliberate optimization since re-opening/re-parsing a 200-800MB 4K source three
times was pure waste on the critical path. `_can_copy()` decides whether the source can be
losslessly remuxed (`-c copy`, seconds of CPU) instead of re-encoded (minutes):

```python
_MAX_HEIGHT = 1080
_MAX_FPS = 30
_MAX_SOURCE_KBPS = 3000
```

A source only qualifies for `-c copy` if it's **already** H.264/AAC, ≤1080p, ≤30fps (with a
`+1` fps allowance so a 29.97 NTSC source doesn't trip the check), **and** ≤3000kbps. This is a
real fix over the pre-R2 version, which gated on codec alone — measured 2026-09-04: 8 of 127
videos were H.264 already, so they were copied through at their **original** resolution/bitrate
untouched (one 4K 50Mbps lecture served to students at 4K 50Mbps). `None` on any probed field is
treated as out-of-spec (the safe direction — a bad remux ships broken segments silently, a bad
encode just fails loudly and gets recorded on the row).

### Encode settings — deliberate design decisions, not defaults

```python
_SEGMENT_SECONDS = 10
_TARGET_MAX_KBPS = 2500
```

```
-map 0:v:0 -map 0:a:0?
-vf scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30
-c:v libx264 -preset veryfast -crf 23 -maxrate 2500k -bufsize 5000k
-profile:v high -level 4.1 -pix_fmt yuv420p
-force_key_frames expr:gte(t,n_forced*10)
-c:a aac -b:a 96k -ac 2
```

Every value here was a decision, confirmed still current in the code and re-checked here rather
than copied wholesale from the archived execution doc (which was written against a slightly
different intermediate shape — the settings below are what's actually in `video_service.py`
today):

- **10-second segments, not 4 (the original) or 20 (considered and rejected).** Cost was never
  the driver — R2's Class B free tier swallows this library's read volume at any of these
  lengths. What 10s buys: 2.5× fewer segment requests per playback, with a first-segment download
  small enough (~2-3MB at these bitrates) not to punish a slow connection at startup. 20s was
  rejected because with a **single rendition** (no ABR ladder — see §7 "Deliberately not built")
  there's no lower-bitrate variant for hls.js to fall back to, so a 20-second segment that can't
  be fetched in 20 seconds is an *unrecoverable* stall, not a hiccup. Apple's own HLS authoring
  guidance recommends 6s; 10s is already a deliberate step past that in the safe direction.
- **`scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease`, not
  `scale=-2:1080`.** The latter *upscales* anything already smaller than 1080p, producing a
  bigger, blurrier file. `min()` clamps instead of forcing — never upscale.
- **`-preset veryfast`, not `fast`/`medium`.** The API and the ARQ worker share one 4-vCPU VPS
  (see `HANDOFF_VPS_DEPLOYMENT.md` §2) — a slower preset was measured at ~0.36× realtime on this
  library's actual 4K-HEVC-off-an-iPhone sources, which made a full-library re-encode a 25-hour
  job. `veryfast` is roughly 3-4× quicker for a small bitrate cost that the `-maxrate` cap absorbs
  anyway.
- **`fps=30`, always** (not preserving 60fps sources). Measured: the same 2-minute test source
  encoded at 60fps landed near 2988kbps; the identical content at 30fps lands near 1800kbps with
  no perceptible quality loss on lecture/slide/screen-recorded material — the single biggest
  file-size lever available, and it roughly halves encode time too.
- **`-crf 23` capped by `-maxrate 2500k -bufsize 5000k`, not CRF alone.** An uncapped CRF can spike
  a high-motion lesson to 8Mbps+ and stall a student on a modest connection; the cap bounds worst
  case while CRF still does the real quality/size tradeoff on typical content.
- **`-map 0:v:0 -map 0:a:0?` — explicit stream selection, not implicit.** This library's sources
  are iPhone recordings, which carry several `mebx` timed-metadata data streams alongside video
  and audio; none belong in an mpegts segment, and leaving stream selection implicit let ffmpeg
  try (and fail) to mux them in. The trailing `?` on the audio map keeps a silent source from
  failing the whole encode outright.
- **`-profile:v high -level 4.1 -pix_fmt yuv420p`** — guarantees decode on older Android/Safari,
  cheap insurance for a device population the platform doesn't control.
- **`-b:a 96k -ac 2`** (down from 128-192k on the sources) — speech at 96k stereo AAC is
  transparent; the sources carry more bitrate than the mostly-room-tone audio needs.
- **`-force_key_frames expr:gte(t,n_forced*10)`** — forces keyframes exactly at each 10-second
  segment boundary so `-hls_time` cuts land precisely instead of drifting to wherever the
  encoder's own GOP structure happened to place the nearest keyframe. Only meaningful on the
  re-encode path — the `-c copy` path can't move existing keyframes, so its segments land on the
  first source keyframe at or after the target boundary, which is expected and fine.

**AES-128 encryption**: a fresh random 16-byte key + IV per encode (`os.urandom(16)` twice), fed
to ffmpeg via `-hls_key_info_file`. The key-info file's URI line is a placeholder — the serving
route (§5) rewrites the playlist's `#EXT-X-KEY` line to a token-gated URL per request, never a
static one.

### The zero-downtime swap-in-place re-encode

`run_encrypted_transcode()`'s central design decision, and the reason a re-encode of 127
already-working videos was safe to run against a live platform:

- `swap_in_place = bool(video.playlist_path) and video.status == "ready" and target !=
  video.storage_backend` — true exactly when re-encoding a currently-servable video **onto a
  different backend** (e.g. "Migrate to R2").
- If `swap_in_place`, `status` is **never** downgraded to `"processing"` — the row keeps serving
  its existing, complete output for the entire encode. The new output is written to `target`
  (a different backend, hence a different physical location) and only once it's fully written
  does the row's commit repoint `playlist_path`/`key_path`/`storage_backend` to the new location
  and set `status="ready"` — one atomic commit, no request-observable in-between state. If the
  encode fails, the row is left exactly as it was (`status`/`status_error` are only touched when
  `not swap_in_place`).
- **Prefix stability is what makes this — and the per-video rollback — work at all.**
  `prefix = video.playlist_path.rsplit("/", 1)[0] if video.playlist_path else str(video_id)` —
  a re-encode reuses the row's **established** prefix rather than always writing to
  `str(video_id)`. Every video that predates the `unify_video_service` migration (PR #43) carries
  an `owner_id`-shaped prefix (the migration copied `playlist_path` verbatim onto a freshly
  generated `video.id`, so `prefix != str(video.id)` for those rows specifically) — reusing it
  means the old backend's tree and the new backend's tree sit at the *same key*, on different
  physical stores, untouched by each other. Rolling a video back to its old backend
  (`--move --to vps --video-id <id>`) is then just flipping `storage_backend` back — no re-upload,
  no re-encode, the old bytes were never touched.
- **Best-effort Redis lock for deploy safety**: `SETEX transcoding:{video_id} 3600 1`, set right
  before the encode starts and deleted in a `finally` (so it clears on success, failure, *and*
  `asyncio.CancelledError` — which is a `BaseException`, not `Exception`, and would otherwise skip
  a plain `except Exception` handler and leave the row stuck `"processing"` forever with nothing
  to retry it, since arq's job-timeout cancellation raises exactly that). This lock is the *only*
  signal `ops/deploy-backend.sh --check`'s preflight has for "a swap-in-place re-encode is
  mid-flight" — a swap-in-place re-encode never changes `status`, so the DB alone is blind to it
  (see `HANDOFF_VPS_DEPLOYMENT.md` §3). Never lets a Redis hiccup here fail an otherwise-good
  transcode — wrapped in its own `try/except`, and this function is also called directly with no
  live Redis at all in the test suite (`test_lms_video.py`, `test_lms_admin.py`).
- `target_backend=None` (the default on both `run_encrypted_transcode()` and the `transcode_video`
  ARQ job) means **"no override — write to wherever this row's `storage_backend` already says,"**
  not "target the VPS explicitly." This is deliberate, not just the simplest reading: the value
  crosses an ARQ job boundary (Redis-serialized), so a sentinel meaning "explicit VPS" would be
  indistinguishable from "no override" once it round-trips through Redis. There is consequently
  **no way to ask for an explicit re-encode back onto the VPS** — rolling a video back to the VPS
  is always `--move --to vps` (a copy, free, instant, no ffmpeg), never a second transcode. The
  migration script's own docstring calls this out explicitly (`NO "--reencode --to vps"`).

---

## 5. Storage migration/status tool

`backend/scripts/video_migrate_to_r2.py`, run inside `spacepoint-api` or `spacepoint-worker`
(confirmed present and matches this description — the tool grew more capabilities than the
archived R2 execution doc originally planned; this is read directly from the current script):

| Flag | What it does | Mutates anything? |
|---|---|---|
| `--status` | Report where every video's bytes currently live (`r2`/`vps`), grouped by `owner_type` and, for `module_item`, by course | No |
| `--sizes` | Report each video's source size vs. HLS output size (compression ratio) by listing object sizes — no download | No |
| `--link-legacy-library` | One-time fix for a real migration bug: `unify_video_service` backfilled a `Video` row for every video-format `library_resources` row but never pointed `library_resources.file_url` at it, so any pre-migration Library video served `video_info: null`. Only relinks `file_url`; run `--convert` right after | Yes (unless `--dry-run`) |
| `--move --to r2\|vps` | Copies a video's student-facing bytes to another backend and repoints `storage_backend`, **without re-encoding**. Right for `direct`-mode videos (nothing to re-transcode) and for rolling a single video back (`--to vps --video-id <id>`) | Yes |
| `--convert` | One-time mode change: an existing `direct`-mode video becomes `hls_encrypted` (compressed, streamed through the shared pipeline), then enqueued for transcode targeting R2. Safe to re-run — filters to `upload_mode="direct"`, and a row flips out of that mode the moment it converts | Yes |
| `--reencode` | Re-runs the HLS transcode at **current** encode targets, output always to R2 — this, not `--move`, is how the existing HLS library actually gets onto R2 (copying old HLS output to R2 would be copying junk the old remux gate under-compressed). Keeps serving the existing output for the whole encode, per §4's swap-in-place design | Yes |

Every mutating command accepts `--course <id>` (module_item videos only, via a join through
`ModuleItem`/`CourseModule`), `--owner-type`, `--video-id`, and `--limit`, and skips rows already
on the target backend so a re-run after a partial batch only retries what's left. `--dry-run` on
every command that mutates.

**Non-negotiable pre-`--reencode` checklist, from the script's own docstring**: `max_jobs=1` must
already be deployed on the video worker (confirmed live — `workers/main.py::VideoWorkerSettings`,
§6); dump `videos`' mutated columns to a CSV first as a restore-statuses safety net; never run
`deploy-backend.sh` while a batch is draining (`docker rm -f` is SIGKILL, bypasses the
`CancelledError` handler, leaves rows stuck `processing`).

The admin UI mirrors a slice of this as an API: `POST /lms/admin/courses/{course_id}/videos/
migrate-to-r2` (`routers/lms/admin.py::migrate_course_videos_to_r2`) — "migrate 3 courses today,
the rest next week" as a button instead of an SSH session. Confirmed fixed in the current code
(this was flagged as bug #3 in the archived pre-deploy review): a video whose **first-ever**
transcode is still in flight (`status in (pending, processing)`) is excluded from the migrate
batch and reported separately as `still_processing`, rather than being queued for a second,
redundant transcode job racing the first.

---

## 6. Workers — two ARQ processes, deliberately split

`backend/app/workers/main.py`:

```python
class WorkerSettings:        # IO-bound: email, LMS sync, inventory reminders, heartbeat cron
    functions = [send_ticket_email, send_import_batch_emails, ..., sync_registration_lms_job, ...]
    # arq's default concurrency (10) — transcode_video is deliberately NOT in this list

class VideoWorkerSettings:   # transcode_video only, its own Redis queue
    queue_name = "arq:queue:video"
    functions = [func(transcode_video, timeout=3600)]
    max_jobs = 1
```

Split for a concrete reason, confirmed in the code comments: `max_jobs` caps a whole worker
process's concurrency, not per-function. If `transcode_video` shared the main queue, a single
hour-long re-encode (3600s timeout) would back up every IO-bound job behind it — registration
emails, LMS sync — for up to an hour. `max_jobs=1` on the dedicated video worker exists because
ffmpeg is CPU-bound and the API/worker share one 4-vCPU VPS; concurrent encodes would saturate it.

`enqueue_transcode()` (`video_service.py`) and every migration-script enqueue call explicitly pass
`_queue_name="arq:queue:video"` — confirmed in the code, this is what makes the split actually
take effect rather than silently falling back to the default queue (see §3's "known real fix").
See `HANDOFF_VPS_DEPLOYMENT.md` §2/§3 for how `spacepoint-worker-video` is deployed as its own
Docker container, with its own (asymmetric) recreate-swap ordering.

---

## 7. Playback — token, playlist, segment, key

`backend/app/routers/video.py`, mounted at `/videos` with no owner-type prefix — **this replaced
the old LMS-only `/lms/items/{item_id}/video/token` and `/lms/videos/{item_id}/...` paths**
(`routers/lms/video.py` now keeps only the upload endpoint; its own module docstring says so
explicitly). This is the surface whose paths show up constantly in production logs:

| Endpoint | What it does |
|---|---|
| `GET /videos/{video_id}/token` | Issues a short-lived JWT (`create_video_token`, 4 hours — `_VIDEO_TOKEN_MINUTES = 4 * 60`) after running the owner-type-specific access check (§"Access checks" below). 400 if the video isn't `hls_encrypted`; 409 if `status != "ready"`. This is the **one point** where a feature's access rule and a video's identity meet. |
| `GET /videos/{video_id}/playlist?token=` | Decodes the token, loads the `Video` row, downloads the stored `.m3u8` from whichever backend it lives on, and rewrites it per-request (see below) before returning it. |
| `GET /videos/{video_id}/segment/{name}?token=` | Only reachable when the video's HLS output is **not** on an object store — an `"r2"` row's rewritten playlist already points hls.js straight at R2, so this route never actually sees a request for one of those in practice. Segment name is validated against `^segment_\d{3,}\.ts$` (`_SEGMENT_NAME_RE`) — note `\d{3,}`, not a fixed `\d{3}`: ffmpeg's `%03d` is a *minimum* width, so segment 1000 (past ~4h10m of playback at 10s segments) writes as `segment_1000.ts`, and a fixed-width regex would 404 it — a hard, network-failure-indistinguishable mid-playback stop that was a real bug before this was widened. |
| `GET /videos/{video_id}/key?token=` | Serves the raw 16-byte AES-128 key, same access model as the other two. |

**Token validation is deliberately NOT re-running the owner-type access check on every subsequent
call** (`_video_from_token()`'s own docstring is explicit about this): the enrollment/instructor/
guideline check ran once, at token-mint time, and the signed short-lived token itself is the
proof it passed. Re-checking on every playlist/segment/key call was measured to **triple**
per-video-start DB/CPU cost under a real competition-day load test (400 simulated users, the
realistic click→token→playlist→key sequence ran to a ~13s median despite the token endpoint alone
looking fine at ~1.5s in isolation) — so what's actually re-verified on every call is narrower:
the token's signature/expiry, that it names *this* video id (can't be replayed against a
different one), that the signing user still exists, and that the video is still `status="ready"`.
**Trade-off, stated plainly in the code**: revoking a student's enrollment mid-session no longer
cuts off an already-started playback instantly — only once the 4-hour token itself expires. Same
trade-off most short-lived-signed-URL video systems make.

### Access checks (`_ACCESS_CHECKS`, one per `owner_type`)

- `module_item` → enrolled in the owning course. One joined query (`Enrollment` ⋈ `CourseModule`
  ⋈ `ModuleItem`) rather than three sequential round trips — found under the same competition-day
  load test to be the real bottleneck (uvicorn's single-threaded event loop stacking up per-request
  ORM overhead across round trips, not Postgres, which was idle waiting on the client).
- `program_item_guideline` → the student has a progress row for this checklist item on *some*
  assignment of their own (not scoped to one specific assignment — the same guideline video can be
  shared across many students' assignments). Falls back to "can author checklist items at all"
  (`require_lms_content`) for a non-student caller — the authoring UI's own guideline-video
  "Preview" button hits this exact endpoint as a facilitator/operations account, never assigned
  the checklist item as a student.
- `library_resource` / `training_video` → any authenticated instructor (`require_instructor`,
  including its "admin always passes" rule) — no ownership/enrollment concept for either.

### Playlist rewriting

Stored playlists carry plain relative filenames (one file serves every viewer); rewritten
per-request so each segment/key reference is scoped to the request. Two shapes, chosen by
**where this video's bytes actually live** (`_hls_backend(video)`, per-row):

- **R2** (`storage_backend == "r2"`): each segment line becomes an **absolute presigned URL**
  straight to R2 — segments never touch the API at all. Presigning is a local HMAC computation, no
  network call, no billed R2 operation, so signing ~30 lines for a 5-minute lesson at 10s segments
  costs microseconds.
- **Local/Supabase**: relative `segment/{name}?token=` paths, resolved by this same router's
  `/segment/{name}` route.
- **The `#EXT-X-KEY` line stays relative and token-gated in BOTH shapes** — the AES key never
  moves to the object store. Segments sitting on R2 are already AES-128-encrypted content, so a
  leaked or expired segment URL yields ciphertext, never playable content on its own; the key
  remains behind the same access check as everything else, served only by the API.
- Presigned segment URL expiry is pinned to the same 4-hour window as the video token
  (`expires_in=_VIDEO_TOKEN_MINUTES * 60`) — deliberately, so there's exactly one failure mode
  instead of two interleaved ones. The frontend's existing one-retry-on-network-error path
  (`VideoPlayer.tsx`, both the shared `frontend/src/components/video/VideoPlayer.tsx` and the
  LMS-specific `frontend/src/pages/learn/VideoPlayer.tsx`) already re-issues the token *and*
  refetches the playlist on a fatal hls.js error, which mints fresh presigned URLs — a student who
  pauses for hours and comes back gets one invisible retry, no special-casing needed.

---

## 8. Frontend

- **`frontend/src/components/video/VideoPlayer.tsx`** — the shared player for Library, checklist
  guideline, and Training video, plus the generic entry point for any `owner_type` played through
  `/videos/{id}/...`. Mirrors `get_playback_info()`'s response shape exactly
  (`VideoPlaybackInfo`); branches on `provider`/`mode` to render an iframe (youtube/vimeo), a
  plain `<video src=...>` (direct), or `HlsEncryptedVideo` (hls_encrypted — fetches its own token
  off `info.video_id`, attaches hls.js or falls back to Safari's native HLS support, one retry on
  a fatal hls.js error).
- **`frontend/src/pages/learn/VideoPlayer.tsx`** — LMS module video keeps its **own**, separate
  hls.js player rather than using the shared component above, specifically because it's coupled
  to `video_checkpoints` (`backend/app/models/lms/course.py::VideoCheckpoint` — timeline markers
  keyed on `module_items.id`, not on the `Video`/`video_id`: a `note` banner over a
  `[start_seconds, end_seconds]` window, or a `quiz` that pauses playback at a single
  `start_seconds` moment). Checkpoints are LMS-only state the shared component must never know
  about — that's the entire reason for the duplication, not an oversight; the attach/retry/native-
  HLS-fallback mechanics are otherwise mirrored between the two players.
- `getLmsProgramItemGuidelineVideoUrlApi` (`frontend/src/api/lms_admin.ts`) — the admin preview
  endpoint for a guideline video. Was previously always returning an empty `url` for
  `hls_encrypted` mode (bug #4 in the archived pre-deploy review — `get_playback_info()` has no
  bare `url` key for that mode) — confirmed fixed in the current backend
  (`get_program_item_guideline_video_url` now returns `video_info` matching
  `VideoPlaybackInfo`'s real shape, same pattern the student-facing twin already used).

---

## 9. What changed since the R2 migration runbooks — read this before trusting the archived docs

The three archived docs (`docs/archive/HANDOFF_VIDEO_R2_EXECUTION.md`,
`HANDOFF_VIDEO_R2_REVIEW_FIXES.md`, `HANDOFF_COMPETITION_DAY_DEPLOY.md`) are plans and go-live
runbooks for a specific event (the September 2026 SatKit competition), not living architecture —
some of what they describe is exactly what shipped, some evolved further. This doc is grounded in
the code as of 2026-09-17; where it disagrees with an archived doc, this doc is current:

- **The global `VIDEO_STORAGE_BACKEND` env-var switch the execution plan describes was
  superseded before it ever shipped as "the" mechanism.** It still exists in `core/config.py` as
  `default_video_backend()`, but `video_service.py` deliberately does not read it for new uploads
  — those are hardcoded to `"r2"` (`_NEW_UPLOAD_BACKEND`, §2). The per-video `storage_backend`
  column, not an env var, is what actually governs where any given row's bytes live — this was
  already the shipped design by the time of the competition-day runbook (which explicitly notes
  it supersedes the execution plan's §5.3 rollback section on exactly this point).
- **Playback moved out of the LMS router entirely.** The archived docs still describe
  `/lms/items/{item_id}/video/token` and `/lms/videos/{item_id}/...` — those paths are gone.
  Playback for every owner_type, including LMS module videos, is `/videos/{video_id}/...` (§7).
  Only the upload endpoint remains LMS-specific (`POST /lms/admin/items/{item_id}/video`).
- **The bucket name for pre-transcode sources is `video-sources`, not `lms-video-sources`** as
  the archived docs (and, until this pass, `HANDOFF_VPS_DEPLOYMENT.md`) said —
  `video_service.py::SOURCE_BUCKET` is the literal constant.
- **Every finding in `HANDOFF_VIDEO_R2_REVIEW_FIXES.md` has landed**, confirmed by reading the
  current code, not just trusting its own checklist: the video worker is genuinely split onto its
  own queue with `max_jobs=1` (§6); the deploy preflight checks the `transcoding:{id}` Redis lock
  (§4, `HANDOFF_VPS_DEPLOYMENT.md` §3); `migrate_course_videos_to_r2` excludes in-flight rows
  (§5); the guideline-video preview endpoint returns real `video_info` (§8). The two unrelated
  Roadmap/Design-mission findings in that doc (#5, #6) are out of scope for this doc.
- **The migration script grew well past what the execution plan specified** — `--link-legacy-library`
  and the `--convert`/`--reencode` split (§5) don't appear in the original plan at all; they were
  added to handle real bugs/gaps found during the actual rollout (the archived competition-day
  runbook's "Additional fixes that landed during the actual rollout" list covers some of this).

---

## Gotchas

- **`_NEW_UPLOAD_BACKEND` is hardcoded, not a setting.** If R2 credentials are ever missing from a
  deployment's env file, every fresh video upload fails loudly (a `RuntimeError` from
  `storage_r2.py::_client()`/`_endpoint()`) rather than silently falling back to local disk. This
  is intentional (§2) — don't "fix" it by making it configurable without re-reading why.
- **`HLS_BUCKET = "lms-hls"` must never be renamed.** Nothing persists this bucket name per row;
  every row's `playlist_path`/`key_path` is assumed to live under it. It was renamed once during
  development and broke playback of every pre-existing video; the fix was reverting the rename,
  not fixing up rows.
- **A video's storage prefix is `playlist_path`'s directory, not `video.id`.** Every row that
  predates PR #43's migration was backfilled with a freshly generated `id` while `playlist_path`
  was copied verbatim, so `str(video.id)` and the row's real storage prefix are different strings
  for those rows. `_storage_prefix()` (`routers/video.py`) and the corresponding logic in
  `video_service.py` always derive the prefix from `playlist_path`, never assume it equals
  `video.id` — any new code touching storage paths must do the same or it will fetch/write objects
  that don't exist.
- **A swap-in-place re-encode never changes `videos.status`.** A row mid "Migrate to R2" reads
  `status="ready"` the entire time, by design (§4) — the *only* signal that it's actually
  in-flight is the `transcoding:{video_id}` Redis key. Any tooling that gates on `status` alone
  (a future admin dashboard, a future deploy check) needs to check both, the way
  `ops/deploy-backend.sh --check` already does.
- **There's no way to explicitly re-encode a video back onto the VPS** — `target_backend=None`
  means "no override," not "the VPS" (§4). Rolling a video back to the VPS is always `--move --to
  vps`, a copy of the existing output, never a second transcode job.
- **Uploads are still fully buffered in memory** (`await file.read()`, §3) — a 4GB upload is a
  4GB `bytes` object handed straight to `attach_upload()`. Not fixed as of this pass; flagged as a
  real (not just theoretical) risk the moment concurrent large uploads happen.
- **The remux gate treats an unprobeable source as out-of-spec, not as "assume it's fine."**
  `_can_copy()` returns `False` whenever any probed field is `None` — deliberately the safe
  direction (a bad remux ships broken segments silently; a bad encode just fails and gets
  recorded), but it does mean a source ffprobe can't read at all always takes the slower re-encode
  path, never `-c copy`.
- **Segment filenames aren't fixed-width.** `%03d` is ffmpeg's *minimum* width — a lecture past
  ~4h10m at 10s segments produces `segment_1000.ts`, four digits. The route's regex
  (`_SEGMENT_NAME_RE = r"^segment_\d{3,}\.ts$"`) already accounts for this; don't tighten it back
  to a fixed `\d{3}`.
- **No ABR ladder exists.** Every `hls_encrypted` video is a single rendition at the encode
  settings in §4 — there is no lower-bitrate variant for hls.js to fall back to on a slow
  connection, which is also *why* segments are capped at 10s rather than 20s (§4). Building one
  (split filter + `-var_stream_map`, ~1.7× the CPU of a single rendition since the source is only
  decoded once) was explicitly scoped out of the original R2 rollout as post-event work
  (archived execution doc, Phase 6) — nothing in the current code suggests it has been picked up
  since.
