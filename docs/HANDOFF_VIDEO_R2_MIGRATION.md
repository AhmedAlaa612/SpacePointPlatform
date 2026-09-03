# Video service standardization + Cloudflare R2 migration (handoff)

Video handling today is duplicated across four features (course modules, checklist guideline video,
instructor library, facilitator training video), each with its own schema and code path, and video
files live Fernet-encrypted on the VPS's local disk, proxied through the API on every HLS segment
request. Decided approach, in this order:

1. **Standardize** into one shared video service first, on the current storage backend — no R2 yet.
2. **Test** that end-to-end before touching storage.
3. **Migrate storage to Cloudflare R2** (an R2 account/bucket already exists) — new backend module,
   one-time upload script for existing files, switch playback to presigned R2 URLs.
4. **Cut R2 operations cost**: longer HLS segments (4s → 20s), consider a compression pass.
5. Deprioritized for later: uvicorn/DB-pool tuning, live-games Redis pattern (expected under 100
   concurrent per game — not a current concern).

This doc is grounded in the actual code (file:line refs) so whoever picks it up doesn't need to
re-discover the current state.

---

## Step 1 — Standardize the video service

**Current duplication** (four different shapes, confirmed by code read):

| Feature | Table | Upload? | Transcode? | Serving |
|---|---|---|---|---|
| Course module video | `ModuleVideo` (`backend/app/models/lms/course.py:136-151`) | Yes, real upload, 2GB cap | Full ffmpeg→HLS+AES pipeline (`backend/app/services/lms/video.py`) | JWT-token-gated playlist/segment routes (`backend/app/routers/lms/video.py`) |
| Checklist guideline video | `LmsProgramItem.guideline_url` (`backend/app/models/lms/program.py:180-187`) | No — link only | none | client iframe embed |
| Instructor Library | `LibraryResource.file_url` (shared row with PDFs) | Yes, 500MB cap, video sniffed by extension | none | generic signed URL, no seek support |
| Facilitator training video | `TrainingVideo.video_path` | **No upload endpoint** — URL set by hand | none | signed URL elsewhere |

**Build**: one shared `videos` table + one `video_service.py`:
- `videos`: `id`, `owner_type`/`owner_id` (same polymorphic-owner pattern `LmsProgramItem` already
  uses), `provider`, `provider_object_key` (bucket/path or provider id), `status`
  (`uploading`/`processing`/`ready`/`failed`), `duration_seconds`, `created_at`.
- `video_service.py`: `upload(owner_type, owner_id, file) -> Video`, `get_playback_url(video_id) ->
  str`, `delete(video_id)`. Internally still calls the existing ffmpeg/HLS pipeline
  (`services/lms/video.py`) and existing `app.services.storage` — this step is about the schema/API
  surface, not the storage backend (that's Step 2).

**Migration order** (least risk first):
1. Point `ModuleVideo` at the new table/service — it's the only feature with a working pipeline
   today, so this proves the new path without also building upload/transcode from scratch.
2. Wire instructor library video uploads through it (currently raw upload with no transcode/seek
   support — this is a real upgrade for that feature too).
3. Add checklist guideline video upload through it (currently link-only — this is the actual "attach
   video anywhere" gap closing).
4. Add training video upload through it (currently has no upload endpoint at all).

**Gate before Step 2**: all four call sites working end-to-end on the *current* storage backend
(local/Fernet, unchanged) — confirms the schema/service consolidation is correct in isolation, before
also changing where bytes live.

---

## Step 2 — Migrate storage to Cloudflare R2

R2 account/bucket already created.

1. **New `storage_r2.py`** alongside the existing `storage_local.py`/`storage_supabase.py`
   (`backend/app/services/storage.py` dispatches on `settings.STORAGE_BACKEND`) — same interface
   (`upload_file`, `upload_to_path`, `delete_file`, `get_signed_url`, `download_file`, `list_files`).
   R2 is S3-compatible (`boto3` or any S3 SDK works against R2's endpoint) — `get_signed_url` becomes
   a real presigned URL, not the app's self-issued HMAC scheme `storage_local.py` uses today.
2. **Config**: R2 account id, access key, secret, bucket name, endpoint URL — add to
   `backend/app/core/config.py` alongside the existing `STORAGE_BACKEND`/`STORAGE_ENCRYPTION_KEY`
   settings.
3. **One-time upload script** (VPS → R2): iterate existing video files under `STORAGE_ROOT` (per
   `storage_local.py`'s bucket/path layout), decrypt with the existing Fernet key, upload plaintext
   to R2 under the same bucket/path scheme, verify the upload (re-download + checksum, or at least
   confirm object exists + size matches), **only then** delete the local copy. Do this per-file, not
   as one big batch commit, so a failure partway through doesn't lose track of what's migrated.
4. **Playback URLs**: replace the JWT-gated segment-proxy routes
   (`backend/app/routers/lms/video.py`'s playlist/segment/key endpoints) with issuing a presigned R2
   URL after the same enrollment/access check that exists today — one URL per playback session
   instead of decrypting every ~4s segment in-process. This is also what removes Fernet from the
   video path entirely (R2 has its own encryption at rest; the presigned URL *is* the access
   control now) — Fernet stays unchanged for everything else (PDFs, documents) on local storage.
5. Switch `STORAGE_BACKEND` for video specifically once the above is verified (the shared
   `video_service.py` from Step 1 is exactly what makes this a one-place change instead of four).

---

## Step 3 — Cut R2 operations cost

The concern: R2 bills per read/write operation (Class A = writes, Class B = reads) beyond its free
tier (10M Class B ops/month free) — HLS's many small segment files multiply reads per view.

1. **Segment duration 4s → 20s**: in the ffmpeg HLS encode step (`services/lms/video.py`), raise the
   target segment duration. Fewer, larger files per video = proportionally fewer GET requests per
   view. Trade-off: coarser seek granularity and a slightly larger first-segment download before
   playback starts — likely fine for ~5-minute lessons, worth a quick check on perceived start-up
   latency once changed.
2. **Worth evaluating before committing to (1)**: since these are short (~5 min) VOD lessons, not
   live/adaptive-bitrate content, serving a single plain MP4 per lesson with HTTP Range support
   (native to R2 and to `<video>` tags — no manual playlist/segment files at all) would cut reads to
   roughly one object per lesson instead of N segments, a bigger reduction in operations than
   lengthening HLS segments. This drops adaptive bitrate switching (probably not needed at this
   content length/type) — flagging as an alternative worth a decision, not prescribing over the
   4s→20s plan already decided.
3. **Compression**: the existing ffmpeg transcode step is already the point that sets the delivered
   bitrate/resolution — the direct lever for smaller delivered files is lowering the target
   bitrate/resolution there (e.g. cap at 720p or lower for talking-head/screen-recorded lessons),
   rather than necessarily adding a separate pre-compression pass. A separate pre-pass only earns its
   keep if the goal is shrinking the raw instructor-uploaded source *before* it hits the transcode
   worker (saves upload time and worker CPU on large source files) — worth clarifying which problem
   is being solved before building it as its own pipeline stage.

---

## Deprioritized — come back to later

- **uvicorn workers + DB pool sizing**: `backend/Dockerfile:39` runs a single uvicorn process with no
  `--workers` flag; `backend/app/db/session.py:27-34` sets no `pool_size`/`max_overflow` (SQLAlchemy
  defaults to 15 total connections for the whole app). Free, low-risk fix (`--workers 3` + explicit
  `pool_size=10, max_overflow=10`, checking Postgres's `max_connections` covers `workers × pool`) —
  real, but sequenced after the video work.
- **Live games realtime**: `backend/app/services/games/realtime.py` opens one dedicated Redis
  subscriber connection per connected student in a live game (by design, documented in its own
  docstring). Fine at the expected scale (well under 100 concurrent per game session) — revisit only
  if that assumption changes materially.
