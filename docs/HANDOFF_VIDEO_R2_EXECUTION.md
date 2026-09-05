# Execution plan: video delivery for the 400-student competition (R2 + re-encode)

**Status:** plan, not yet executed. Written 2026-09-04.
**Supersedes the sequencing in** `HANDOFF_VIDEO_R2_MIGRATION.md` §2–3 (that doc's *analysis* still
holds; this one is the ordered, decision-closed version, sized for a hard deadline).

**Baseline:** PR #43 (`f7b2f01`, "Standardize video handling") is **merged to `main`**. Everything
below is written against that code, verified by reading it — not against the pre-#43 shape. Names
that changed, and that every script and snippet here already uses:

| Pre-#43 | Now |
|---|---|
| `ModuleVideo` (table `module_videos`) | `Video` (`app/models/videos.py`, table `videos`), filtered `where(Video.owner_type == "module_item")` |
| `.item_id` | `.owner_id` |
| `.transcode_status` / `.transcode_error` | `.status` / `.status_error` |
| `services/lms/video.py` (deleted) | `services/video_service.py` |
| ARQ job `transcode_lms_video` | ARQ job `transcode_video` (`app/workers/tasks/video.py`) |
| video JWT claim `item_id` | claim `video_id` |

### Two constants that must NOT be "cleaned up"

1. **`HLS_BUCKET = "lms-hls"`** in `video_service.py`. It is not a per-row DB column — both old and
   new code hardcode it and assume every row's `playlist_path`/`key_path` lives under it. Renaming
   it to something more generic-sounding (`video-hls`) already broke playback of every pre-existing
   video once during #43's development; it was caught and reverted. The comment above it in the
   merged code explains this. Leave it.
2. **A row's storage prefix is `playlist_path`'s directory, NOT `video.id`.** The migration
   backfilled each pre-existing video with a *freshly generated* `uuid4()` id while copying
   `playlist_path` verbatim — so for all ~110 existing videos, `playlist_path` is
   `{item_id}/playlist.m3u8` and `str(video.id)` is something else entirely. The merged read path
   already does this correctly (`routers/lms/video.py:193`,
   `video_service.py::_delete_storage`); anything new must match it. §2.4 covers the one place the
   merged code does *not*, which matters specifically for this migration.

**Decisions taken by the operator (2026-09-04), not open for re-litigation here:**
- Students are **remote, on their own connections** — no shared venue uplink ceiling.
- **No Cloudflare custom domain.** Bytes are served with **presigned S3 URLs** against
  `<account>.r2.cloudflarestorage.com`. No DNS change to `spacepoint.ae`.
- **The VPS is the only encoding machine** (4 vCPU, shared with the live platform).
- Scope is the existing library: ~110 videos / ~20.7 GB of sources, already on the VPS.

---

## 0. What problem this actually solves (read this before cutting anything)

The framing in the original handoff was "R2 bills per operation, so make segments longer to cut
Class B ops." **At this scale that is not the problem.** Run the numbers:

| | 4s segments | 10s segments | 20s segments |
|---|---|---|---|
| Segments per student-hour | 900 | 360 | 180 |
| 400 students × 9h of content | 3.24M | 1.30M | 0.65M |
| R2 Class B free tier | 10M/month | 10M/month | 10M/month |
| **Cost** | **$0** | **$0** | **$0** |

Storage: ~110 re-encoded lessons at ~1080p/2.5 Mbps ≈ 10–15 GB → $0.00–0.08/month
(10 GB-month free, then $0.015/GB). Class A writes for the whole upload ≈ 4k operations against a
1M/month free tier. Egress is $0 on R2 at any volume. **The whole delivery bill is effectively
zero regardless of segment length.**

The real problem is the VPS:

- Today every HLS segment is a request to a **single uvicorn process** that reads the whole
  segment off disk, **Fernet-decrypts it in a thread**, and buffers it in memory before
  responding (`storage_local.download_file` → `routers/lms/video.py:get_segment`).
- 400 concurrent students at ~2.5 Mbps is **~1 Gbps sustained** out of one 4-vCPU box, plus
  ~30,000 decrypt operations per five minutes of wall clock.
- Over the event that is roughly **4 TB of egress** from a VPS that very likely has a monthly
  traffic quota well under that.

Moving segments to R2 takes the API's per-playback work from `3 + N` requests (N = 75 for a
5-minute lesson at 4s) to exactly **3 small requests: token, playlist, key** — and takes its
video byte throughput to approximately zero. That is the win. Segment length is a *playback
quality* decision, not a cost one (see §2).

**Second problem, equally important and currently invisible:** the transcode step only remuxes vs.
re-encodes based on **codec**, never resolution or bitrate:

```python
# video_service.py — as merged in #43 (ported verbatim from the deleted services/lms/video.py)
codec_args = ["-c", "copy"] if _probe_is_h264_aac(source) else [720p @ 800k transcode]
```

Any source that is already H.264/AAC is **copied through at its original resolution and bitrate**.
A 4K 50 Mbps H.264 lecture becomes 4K 50 Mbps HLS segments served to students. Given the library
was bulk-imported from a Drive dump of unknown provenance, an unknown fraction of the 110 videos
are almost certainly in exactly this state. §0.1 measures it; §2 fixes it. **This single gate is
likely doing more damage to playback than storage backend and segment length combined.**

---

## Phase 0 — Pre-flight (do first; none of it depends on the code work)

### 0.1 Audit the library — measure before you encode

Run on the VPS. This is the input to every capacity estimate below and it confirms or kills the
`-c copy` suspicion above.

```bash
# inside the api container, or on the host with the storage volume mounted
# NOTE: sources are Fernet-encrypted at rest — ffprobe cannot read them off disk directly.
# Decrypt to a temp file first (script sketch, run in the container so STORAGE_ENCRYPTION_KEY is set):
python - <<'PY'
import csv, json, subprocess, tempfile, asyncio, pathlib
from app.services import storage
from app.db.session import AsyncSessionLocal
from sqlalchemy import select
from app.models.videos import Video

async def main():
    rows = []
    async with AsyncSessionLocal() as db:
        vids = (await db.execute(
            select(Video).where(Video.owner_type == "module_item",
                                Video.upload_mode == "hls_encrypted")
        )).scalars().all()
        for v in vids:
            if not v.source_path:
                continue
            data = await storage.download_file(v.source_bucket, v.source_path)
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(data); src = f.name
            out = subprocess.run([
                "ffprobe","-v","error","-print_format","json",
                "-show_streams","-show_format", src], capture_output=True, text=True).stdout
            j = json.loads(out)
            vs = next((s for s in j["streams"] if s["codec_type"]=="video"), {})
            aud = next((s for s in j["streams"] if s["codec_type"]=="audio"), {})
            rows.append({
                "video_id": str(v.id), "owner_id": str(v.owner_id),
                "prefix": (v.playlist_path or "").rsplit("/", 1)[0],
                "size_mb": round(len(data)/1e6,1),
                "duration_s": round(float(j["format"].get("duration",0))),
                "vcodec": vs.get("codec_name"), "acodec": aud.get("codec_name"),
                "width": vs.get("width"), "height": vs.get("height"),
                "fps": vs.get("r_frame_rate"),
                "bitrate_kbps": round(int(j["format"].get("bit_rate",0))/1000),
                "status": v.status,
            })
            pathlib.Path(src).unlink(missing_ok=True)
    with open("/tmp/video_audit.csv","w",newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} videos, total {sum(r['duration_s'] for r in rows)/3600:.1f}h")
asyncio.run(main())
PY
```

**What you are looking for, and what each answer means:**

| Finding | Meaning |
|---|---|
| Total duration (hours) | The single number that sets the encode window in §4. |
| Rows with `height > 1080` **and** `vcodec == h264` | Were copied through at full resolution. These are the worst offenders and *must* be re-encoded. |
| Rows with `bitrate_kbps > 3000` | Same — students are downloading far more than they need. |
| Rows already ≤1080p, h264/aac, ≤3000 kbps, ≤30 fps | **Can be `-c copy`'d — near-zero CPU.** Every row in this bucket is encode time you don't spend. |
| `prefix` ≠ `video_id` on a row | Normal and expected — that row was backfilled by #43's migration. It is why §2.4 exists. Keep this column; §4.2 and §5.3 both use it. |
| `fps` near 60 | Halving to 30 cuts required bitrate ~35% for identical perceived quality on lecture content. |

Do not skip this. The difference between "20 rows need a real encode" and "110 rows need a real
encode" is the difference between a 90-minute job and an overnight one on a 4-vCPU box.

### 0.2 R2 setup

1. **Check the existing bucket's location** in the R2 dashboard. R2 location hints are
   `wnam / enam / weur / eeur / apac / oc` — there is no Middle East region, and **a bucket's
   location cannot be changed after creation**. Without a custom domain there is no CDN edge
   cache in front of it, so this latency is paid on every segment fetch. For a UAE-centred
   audience **`eeur` (Vienna)** is normally the best of the available hints, with `weur` (Dublin)
   close behind. Measure before deciding — https://r2-ping.fernandodilland.com/ pings every region
   from the browser; run it from a connection representative of your students.
   **If the existing bucket is in `wnam`/`enam`, create a new one with `eeur` now** — you are
   uploading fresh content anyway, so it costs nothing but the bucket name.
2. **One R2 bucket, app buckets become key prefixes.** Do not create one R2 bucket per app
   bucket. `storage_r2.py` maps `(bucket, path)` → key `f"{bucket}/{path}"` inside a single R2
   bucket (e.g. `spacepoint-media`). This keeps the six-function storage interface unchanged.
3. **API token**: R2 → Manage API Tokens → *Object Read & Write*, scoped to that one bucket.
   Record account id, access key id, secret, and the endpoint
   `https://<account-id>.r2.cloudflarestorage.com`. These go in `/etc/spacepoint/env`, never in
   git (per `HANDOFF_VPS_DEPLOYMENT.md` §0).
4. **CORS — this one silently breaks playback if you forget it.** hls.js fetches segments
   cross-origin from the R2 endpoint; without an `Access-Control-Allow-Origin` header the browser
   drops every segment and you get a generic "playback failed" that looks exactly like a
   transcode bug. Set on the bucket:
   ```json
   [{
     "AllowedOrigins": ["https://portal.spacepoint.ae", "https://lms.spacepoint.ae"],
     "AllowedMethods": ["GET", "HEAD"],
     "AllowedHeaders": ["range", "content-type"],
     "ExposeHeaders": ["content-length", "content-range", "etag"],
     "MaxAgeSeconds": 3600
   }]
   ```
   Add every origin that serves the SPA bundle. Same list as the backend's `CORS_ORIGINS`.

### 0.3 VPS hardening — cheap, unrelated to R2, all of it matters at 400 concurrent

These are the items the original handoff deprioritized. At 400 concurrent they stop being
optional. Do them in this order; each is independently deployable.

1. **`arq` concurrency — do this BEFORE §4 or you will melt the box.** ~~`WorkerSettings` sets
   `max_jobs = 1` globally~~ — superseded (pre-deploy code review, 2026-09-04): a single worker
   process with `max_jobs = 1` caps the *whole worker's* concurrency, so IO-bound jobs
   (`send_ticket_email`, `sync_registration_lms_job`, etc.) queue up behind whatever transcode is
   running, for up to its 3600s timeout. `backend/app/workers/main.py` now runs **two** worker
   processes/containers instead of tuning one:
   ```python
   class WorkerSettings:       # IO-bound jobs — arq's default concurrency (10)
       functions = [send_ticket_email, sync_registration_lms_job, ...]  # transcode_video NOT here

   class VideoWorkerSettings:  # transcode_video only, its own queue
       queue_name = "arq:queue:video"
       functions = [func(transcode_video, timeout=3600)]
       max_jobs = 1             # ffmpeg is the only CPU-bound job here; serial is correct
   ```
   `enqueue_transcode` routes jobs to `arq:queue:video` via `safe_enqueue`'s `_queue_name` kwarg.
   Both containers must run in production — see `ops/deploy-backend.sh` (`spacepoint-worker` +
   `spacepoint-worker-video`) and `docs/HANDOFF_VPS_DEPLOYMENT.md` §2/§3.
2. **uvicorn workers.** `backend/Dockerfile` runs one process. On a 4-vCPU box:
   ```dockerfile
   CMD ["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 3"]
   ```
   Three, not four — leave a core for Postgres and the worker.
3. **DB pool.** `backend/app/db/session.py` sets no `pool_size`/`max_overflow`, so SQLAlchemy
   defaults to 5 + 10 = 15 per process. With 3 workers that is 45 connections; check
   `SHOW max_connections;` on the VPS Postgres (default 100) covers `workers × (pool + overflow)`
   plus the worker container plus your own psql sessions.
   ```python
   engine = create_async_engine(settings.DATABASE_URL, pool_size=10, max_overflow=5, pool_pre_ping=True, ...)
   ```
4. **nginx `client_max_body_size 4g;`** — the outstanding action item from
   `HANDOFF_VPS_DEPLOYMENT.md` §7. Uploads still 413 at 50m regardless of the app's 4GB caps.
5. **Confirm BBR is still on**: `sysctl net.ipv4.tcp_congestion_control`. Per
   `HANDOFF_LMS.md` §2 this took first-segment load from 11.2s to 1.7s; a kernel update can
   revert it. Less critical once segments come from R2, but the API still serves the SPA bundle,
   PDFs and every JSON call through the same stack.
6. **Disk headroom**: `df -h /var/lib/spacepoint`. §4 keeps the old local HLS in place as the
   rollback lever (§5.3), so nothing gets freed until after the event.

---

## Phase 1 — `storage_r2.py`

New file `backend/app/services/storage_r2.py`, same six-function interface as
`storage_local.py`/`storage_supabase.py`. Add `boto3` to `backend/requirements.txt` (not currently
a dependency).

```python
"""Cloudflare R2 storage backend (STORAGE_BACKEND / VIDEO_STORAGE_BACKEND = "r2").

R2 is S3-compatible. Two things differ from a real S3 and both matter:
- region is always the literal string "auto"
- signature_version must be pinned to "s3v4" and addressing_style to "path"

Unlike storage_local.py this backend does NOT Fernet-encrypt: R2 encrypts at rest, and the
presigned URL *is* the access control. The bytes it holds are HLS segments that are themselves
AES-128 encrypted by the transcode step, with the key served from the API — see routers/lms/video.py.
"""
import boto3, anyio
from botocore.config import Config
from functools import lru_cache
from app.core.config import settings

@lru_cache
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

def _key(bucket: str, path: str) -> str:
    return f"{bucket}/{path}"        # app "bucket" is a key prefix in one real R2 bucket

async def upload_to_path(bucket, path, data, content_type) -> str:
    def _do():
        _client().put_object(Bucket=settings.R2_BUCKET, Key=_key(bucket, path),
                             Body=bytes(data), ContentType=content_type)
    await anyio.to_thread.run_sync(_do)
    return path

async def get_signed_url(bucket, path, expires_in: int = 3600) -> str:
    # Pure local HMAC — no network call, no R2 operation billed. Safe to call
    # once per segment line when rewriting a playlist.
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET, "Key": _key(bucket, path)},
        ExpiresIn=expires_in,
    )
# download_file / delete_file / list_files / upload_file: same shapes, wrap the
# corresponding boto3 call in anyio.to_thread.run_sync. list_files must return the
# supabase-py dict shape (see storage.py's docstring) — the admin Storage Browser depends on it.
```

**Config** (`backend/app/core/config.py`): `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT_URL`, plus:

```python
# Video-only storage override. "" = follow STORAGE_BACKEND (no behaviour change).
# This is the extension point the standardization pass reserved: PDFs, letters and
# certificates stay exactly where they are; only video bytes move.
VIDEO_STORAGE_BACKEND: str = ""
```

**Facade** (`backend/app/services/storage.py`): add an optional `backend: str | None = None`
kwarg to all six functions, defaulting to `settings.STORAGE_BACKEND`, and teach `_impl()` about
`"r2"`. Every existing caller is untouched. `video_service.py` (and the video router) pass
`backend=settings.VIDEO_STORAGE_BACKEND or None` explicitly.

> **Why a separate switch and not just `STORAGE_BACKEND=r2`:** flipping the global one moves
> payment letters, ID cards, signed contracts and every document bucket at the same time,
> days before a competition, for no benefit. Video is the only thing under load.

**Deliberately NOT migrating:** `lms-video-sources` stays on the local VPS disk, Fernet-encrypted.
Only the ARQ worker ever reads it, it never touches a student request path, and moving 20 GB of
source files buys nothing this month.

---

## Phase 2 — Encoder changes

`backend/app/services/video_service.py`.

### 2.1 Segment length — 10 seconds, not 20

Your instinct to lengthen from 4s was right; **20s over-corrects.** §0 shows cost is $0 at any of
these lengths, so the only things left to trade are startup time and stall risk — and your
students are remote on connections you cannot see or control.

| | 4s (today) | **10s (recommended)** | 20s (proposed) |
|---|---|---|---|
| Bytes before first frame @2.5 Mbps | ~1.3 MB | ~3.1 MB | ~6.3 MB |
| Requests per student-hour | 900 | 360 | 180 |
| Seek granularity | fine | fine | coarse, noticeable |
| Stalls on a 2 Mbps connection | recoverable | recoverable | **a 20s segment takes 25s to fetch → permanent stall** |

That last row is the one that matters. With a **single rendition** there is no lower-bitrate
variant for hls.js to drop to, so any student whose real throughput sits below the encode bitrate
stalls — and the longer the segment, the harder that failure is (it cannot buffer ahead out of the
hole). Apple's own HLS authoring guidance recommends 6-second segments; 10s is already a
deliberate step past that in your favour. 20s only becomes safe once the ABR ladder in §6.1
exists.

```python
_SEGMENT_SECONDS = 10
```

If you want 20s anyway, ship §6.1 (the 480p variant) in the same change — do not ship 20s
single-rendition to 400 remote students.

### 2.2 Fix the remux gate — the highest-value change in this document

Replace `_probe_is_h264_aac` with a real probe and gate on **resolution, bitrate and frame rate**,
not just codec:

```python
@dataclass
class SourceInfo:
    vcodec: str | None; acodec: str | None
    height: int | None; fps: float | None
    bitrate_kbps: int | None; duration_seconds: int | None

_MAX_HEIGHT   = 1080
_MAX_FPS      = 31        # 30fps sources probe as 30000/1001 = 29.97
_MAX_KBPS     = 3000

def _can_copy(info: SourceInfo) -> bool:
    """Remux only when the source is ALREADY what we would have encoded anyway.

    The old version checked codec only, so a 4K 50Mbps H.264 lecture was copied
    through untouched and served to students at 4K. Copying is still the right
    call — it is seconds instead of minutes of CPU on a 4-vCPU box shared with
    the live API — but only for sources that are genuinely already in spec.
    """
    return (
        info.vcodec == "h264" and info.acodec == "aac"
        and (info.height or 99999) <= _MAX_HEIGHT
        and (info.fps or 999) <= _MAX_FPS
        and (info.bitrate_kbps or 99999) <= _MAX_KBPS
    )
```

### 2.3 The transcode arguments

```python
codec_args = ["-c", "copy"] if _can_copy(info) else [
    "-map", "0:v:0", "-map", "0:a:0?",     # iPhone sources carry 4 `mebx` data streams; drop them
    "-vf", "scale='min(1920,iw)':'min(1080,ih)'"
           ":force_original_aspect_ratio=decrease:force_divisible_by=2,fps=30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
    "-maxrate", "2500k", "-bufsize", "5000k",
    "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
    "-force_key_frames", f"expr:gte(t,n_forced*{_SEGMENT_SECONDS})",
    "-c:a", "aac", "-b:a", "96k", "-ac", "2",
]
```

Every difference from your `compresstest` command, and why:

| Your test | Here | Why |
|---|---|---|
| `-preset fast` | `-preset veryfast` | Your run managed **0.362× realtime**. On a 4-vCPU VPS shared with the live API that is unusable for 110 videos (§4 does the arithmetic). `veryfast` is roughly 3–4× quicker for ~10% more bitrate at the same CRF — and the `-maxrate` cap absorbs that. |
| kept 59.94 fps | `fps=30` | Your 2-minute test came out at **2988 kbps at 60fps**. The same content at 30fps lands near 1800 kbps with no perceptible loss on lecture/slide material. This is the single biggest file-size lever you have and it also halves encode time. |
| `scale=-2:1080` | `scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease` | `-2:1080` **upscales** anything already smaller than 1080p — a 720p source becomes a bigger, blurrier 1080p file. `min()` clamps instead of forcing. |
| CRF only | CRF + `-maxrate/-bufsize` | Capped CRF. Without a cap, one high-motion lesson can spike to 8 Mbps and stall students on modest connections. |
| `-b:a 128k` | `-b:a 96k` | Speech at 96k stereo AAC is transparent. Small, free. |
| (implicit stream selection) | explicit `-map` | Your `input.mov` had **four `mebx` data streams**. Explicit mapping stops ffmpeg ever trying to mux those into mpegts. |
| — | `-profile:v high -level 4.1 -pix_fmt yuv420p` | Guarantees playback on older Android/Safari. Cheap insurance for an audience you don't control. |

`-force_key_frames` is only meaningful on the encode path — the `-c copy` path cannot move
existing keyframes, so its segments land on the nearest source keyframe at or after 10s. That is
fine and expected.

### 2.4 Make the transcode's output prefix stable — required for §5.3's rollback

The merged `run_encrypted_transcode` writes its output to `prefix = str(video_id)` and then sets
`playlist_path = f"{prefix}/playlist.m3u8"` (`video_service.py:309`). That is self-consistent for a
*fresh* upload, and the read path derives the prefix back out of `playlist_path`, so nothing is
broken today.

But it is wrong for this migration specifically. Re-encoding a **backfilled** video (all ~110 of
them) would *move* it from `{owner_id}/…` to `{video.id}/…`. Consequences:

- The old 4-second local HLS tree is orphaned at a path no DB row points at any more.
- **§5.3's one-env-var rollback stops working** — flipping `VIDEO_STORAGE_BACKEND` back to local
  would look for `{video.id}/playlist.m3u8` on local disk, which was never written there. 404 on
  every video, during the event, with no quick way back.

Fix it by reusing the existing prefix when there is one:

```python
# video_service.py::run_encrypted_transcode
# Reuse the row's established prefix so a re-encode overwrites in place rather
# than relocating. Backfilled rows carry an owner_id-shaped prefix (#43's
# migration copied playlist_path verbatim onto a freshly-generated id); a
# fresh upload has no playlist_path yet and gets video.id, as before. Keeping
# the prefix stable is what lets the old local tree and the new R2 tree sit at
# the same key, which is the whole rollback story (§5.3).
prefix = video.playlist_path.rsplit("/", 1)[0] if video.playlist_path else str(video_id)
```

This is the **only** change this plan makes to code that shipped in #43. It is safe on its own
(fresh uploads behave identically) and should land in the same branch as the rest, not separately.

Paired constraint on §4.2: **the re-encode driver must not null `playlist_path` before enqueuing**,
or this fix has nothing to read.

---

## Phase 3 — Serve segments from R2

The security model is deliberately asymmetric, and it is what makes a public-ish object store safe
here:

| Asset | Where it is served from | Protection |
|---|---|---|
| Playlist (`.m3u8`) | **API**, unchanged | video JWT + enrollment check, re-validated per request |
| **Segments (`.ts`)** | **R2, presigned, direct to browser** | AES-128 encrypted content + a time-limited signature |
| **Key (`key.bin`)** | **API**, unchanged | video JWT + enrollment check, re-validated per request |

A leaked or expired-but-cached segment URL yields **ciphertext**. The decryption key never leaves
the API and is still gated on the enrollment check that exists today. This is the same protection
level as the current setup, at ~1/25th the API requests and ~0% of the API bandwidth.

### 3.1 Playlist rewriting

`routers/lms/video.py::_rewrite_playlist` gains an R2 branch. Today it rewrites each segment line
to a relative `segment/{name}?token=…`; it now emits an absolute presigned R2 URL instead. The
`#EXT-X-KEY` line is **unchanged** — it stays the relative `key?token=…`, which resolves against
the playlist's own URL and therefore keeps working behind nginx's `/api/` prefix exactly as the
existing comment in that function explains.

```python
async def _rewrite_playlist(raw: bytes, video: Video, token: str, *, expires_in: int) -> bytes:
    key_line = re.compile(r'URI="[^"]*"')
    # Same derivation as get_segment (routers/lms/video.py:193) and
    # video_service._delete_storage — NEVER f"{video.id}/…". A row backfilled
    # by #43's migration has a freshly-generated id that does not match its
    # storage prefix, and assuming otherwise is exactly the bug class #43
    # already had to fix once.
    prefix = video.playlist_path.rsplit("/", 1)[0]
    out = []
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("#EXT-X-KEY"):
            out.append(key_line.sub(f'URI="key?token={token}"', line))   # stays on the API
        elif line and not line.startswith("#"):
            out.append(await storage.get_signed_url(
                HLS_BUCKET, f"{prefix}/{line}",
                expires_in=expires_in, backend=_video_backend()))
        else:
            out.append(line)
    return ("\n".join(out) + "\n").encode("utf-8")
```

Note this makes `_rewrite_playlist` **async** and gives it the `Video` row instead of the
`item_id`; update `get_playlist`'s call site accordingly. `item_id` was only ever used to build a
relative URL that no longer appears in the R2 branch.

Presigning is a local HMAC — no network call, nothing billed. ~30 signatures for a 5-minute lesson
at 10s segments is microseconds.

### 3.2 Expiry must match the video token

Pass `expires_in = _VIDEO_TOKEN_MINUTES * 60` (4 hours). The segment URLs and the video JWT then
age out together, so there is exactly one failure mode instead of two interleaved ones. **The
recovery path already exists and needs no change**: `pages/learn/VideoPlayer.tsx` catches an hls.js
network error, re-fetches the token and rebuilds the source — which re-fetches the playlist and
therefore mints fresh presigned URLs. A student who pauses for four hours and comes back gets one
invisible retry, same as today.

### 3.3 Keep the old segment route

Leave `GET /lms/videos/{item_id}/segment/{name}` in place and working against local storage. It
costs nothing, and it is half of the rollback lever in §5.3 — with `VIDEO_STORAGE_BACKEND=""` the
playlist rewrites to relative segment paths and the whole system is byte-for-byte what ships
today.

### 3.4 Frontend

**No changes required.** hls.js follows whatever URLs the playlist contains, cross-origin or not,
provided §0.2's CORS block is in place. This is worth stating explicitly because it means Phase 3
can ship and be tested without waiting on the shared-`VideoPlayer` component work.

---

## Phase 4 — Bulk re-encode and upload

### 4.1 Budget the encode window from §0.1's numbers

On 4 shared vCPU with `nice -n 19` already applied by `_run(low_priority=True)`:

| Path | Throughput | 9h of content |
|---|---|---|
| `-c copy` (in spec after §2.2) | ~50–100× realtime | minutes |
| `libx264 -preset veryfast`, 1080p30 | ~1.5–2.5× realtime | **4–6 hours** |
| `libx264 -preset fast`, 1080p30 | ~0.7–1× realtime | 9–13 hours |
| `libx264 -preset fast`, 1080p60 (your test) | 0.36× realtime | **25 hours — do not** |

So: **`veryfast` + `fps=30`, run overnight, serially.** Scale that table by your real total
duration from §0.1, and subtract everything the fixed `_can_copy` gate lets through untouched.

If the number still doesn't fit the calendar, in order of preference:
1. Re-encode **only the courses the 400 students will actually open** first; let the rest run after
   the event. The audit CSV plus the course listing tells you which item_ids those are.
2. Drop to `scale=…:min(720,ih)` for talking-head courses (keep 1080p for anything slide- or
   screen-recorded, where text legibility is the whole point).
3. Accept `-preset superfast` — noticeably worse compression, still fine at a 2500k cap.

### 4.2 The re-encode driver

New `backend/scripts/lms_reencode_all.py`, modelled on the existing
`scripts/lms_retry_failed_transcodes.py`. It does **not** re-upload sources (they are already on
the VPS) — it just resets status and enqueues:

```python
# select(Video).where(Video.owner_type == "module_item",
#                     Video.upload_mode == "hls_encrypted")
# optional filters: --course "name" / --only-above-1080 (join the audit CSV) / --dry-run
for video in rows:
    # Deliberately NOT nulling playlist_path/key_path: §2.4's stable-prefix fix
    # reads playlist_path to decide where to write, and §5.3's rollback depends
    # on the prefix not moving. Both paths are overwritten in place by the job.
    video.status = "pending"
    video.status_error = None
    await db.commit()
    await enqueue_transcode(arq_redis, video.id)      # -> ARQ job "transcode_video"
    log(video.id, video.owner_id, prefix, source res/bitrate from the audit CSV, copy-vs-encode)
```

Before the run, **dump the columns you are about to change** — this is §5.3's other half and takes
one command:

```bash
psql -d spacepoint_unified -c "\copy (SELECT id, owner_id, playlist_path, key_path, \
  duration_seconds, status FROM videos WHERE owner_type='module_item') \
  TO '/root/videos_pre_reencode.csv' CSV HEADER"
```

Run it with `VIDEO_STORAGE_BACKEND=r2` already set on the worker container, so output lands
directly in R2 and no second upload/migration step exists at all.

**The `VideoWorkerSettings`/`max_jobs = 1` split from §0.3 must already be deployed** (both
`spacepoint-worker` and `spacepoint-worker-video` containers running). With it, the 110 jobs drain
serially on the video queue without blocking email/LMS sync, and you can watch progress with
`docker logs -f spacepoint-worker-video` and the transcode status column in `/lms-authoring`.

### 4.3 Do NOT migrate the old `lms-hls` files

The original handoff proposed a decrypt-and-upload script for existing HLS output. **Skip it.**
You are re-encoding everything anyway (§2.2 forces it, §2.1 changes segment boundaries), so the
old 4-second segments have no value — and the "verify then delete local" dance that script
required is exactly what you don't want to be debugging this week. Regenerating from the sources
you already have is strictly simpler and fixes the resolution problem in the same pass.

Keep the old local `lms-hls` tree on disk until after the competition — see §5.3.

---

## Phase 5 — Verify, load test, go/no-go

### 5.1 Functional, one video, before touching the other 109

1. Re-encode a single video with `VIDEO_STORAGE_BACKEND=r2`.
2. `GET /lms/items/{id}/video/token` → 200.
3. Pick a **backfilled** video for this test (one whose `prefix` ≠ `video_id` in the §0.1 CSV) —
   that is the case §2.4 exists for, and the case a fresh-upload smoke test would not exercise.
4. `GET /lms/videos/{id}/playlist?token=…` → segment lines are absolute
   `https://<account>.r2.cloudflarestorage.com/...X-Amz-Signature=...` URLs; the `#EXT-X-KEY`
   line is still relative `key?token=…`.
5. `curl -o /dev/null -w '%{http_code} %{size_download} %{time_total}\n' '<one presigned URL>'` →
   200, plausible size, and note the time: **that is your students' per-segment latency with no
   CDN in front.** If it is above ~400ms consistently, revisit the bucket region (§0.2).
6. Play it in a real browser, in an incognito window, as a real enrolled student account. Watch
   the network tab: exactly 3 requests to `portal.spacepoint.ae`, everything else to R2.
7. **Seek to the middle, and seek backwards.** This is where a wrong segment length or a broken
   keyframe interval shows up.
8. Confirm the LMS checkpoint overlay still pauses and resumes (unchanged code path, but it is
   the thing most likely to have been disturbed by #43).
9. Confirm the other three owner types still work — #43 wired `library_resource`,
   `program_item_guideline` and `training_video` onto the same table. They use `direct`/embed
   modes, so R2 does not touch them, but `VIDEO_STORAGE_BACKEND` does route their signed URLs if
   their bytes ever move. Load one of each page and confirm nothing regressed.

### 5.2 Load

The API's video surface is now three small JSON/text endpoints, so this is a much easier test than
it would have been:

```bash
# 400 concurrent token issuances — the heaviest of the three (enrollment check + JWT sign)
hey -n 4000 -c 400 -H "Authorization: Bearer <student-jwt>" \
    https://portal.spacepoint.ae/api/lms/items/<id>/video/token
```
Watch `docker stats spacepoint-api` and Postgres `pg_stat_activity` count during it. p99 should
stay well under a second; connection count must stay under `max_connections`. If it doesn't, the
§0.3 pool sizing is wrong, not the video work.

Separately, have 5–10 real people on real connections play different videos simultaneously. A
synthetic test will not catch a CORS misconfiguration or a codec-profile problem; a browser will.

### 5.3 Rollback

This is the payoff for keeping the old segment route (§3.3), the old local files (§4.3), and
above all §2.4's stable prefix:

> **`VIDEO_STORAGE_BACKEND=""` in `/etc/spacepoint/env`, then recreate the containers.**

**Why this works — and the one thing that would break it.** With §2.4 in place, a re-encode writes
the new 10-second HLS tree to R2 under the *same* key prefix the old 4-second tree occupies on
local disk, and `playlist_path` never changes. So the identical DB row resolves to the old local
tree or the new R2 tree purely by which backend the facade dispatches to. One env var, nothing to
unwind, no data to restore.

**Without §2.4 this rollback silently does not exist** — the re-encode would have relocated every
backfilled row to a `{video.id}`-shaped prefix that was never written to local disk, and flipping
the env var would 404 all ~110 videos. If for any reason §2.4 does not land, the fallback is the
CSV from §4.2: restore `playlist_path`/`key_path`/`duration_seconds` for the affected rows first,
*then* flip the env var. Slower, needs psql under pressure, and is exactly the thing you do not
want to be doing during the event — land §2.4.

Rollback does not restore `duration_seconds` differences or re-mark statuses; take the §4.2 CSV
regardless, as belt and braces.

**Remember `/etc/spacepoint/env` is only read at container *creation*** (`HANDOFF_VPS_DEPLOYMENT.md`
§2) — editing it is not enough, the containers must be recreated. Rehearse this rollback once,
before the event, so nobody is reading a handoff doc at 2am.

### 5.4 Go/no-go checklist

- [ ] §0.1 audit run; total duration and the over-1080p count are known numbers, not guesses
- [ ] §2.4 stable-prefix fix landed **before** any bulk re-encode (rollback depends on it)
- [ ] §4.2 pre-re-encode CSV of `videos` taken and stored off the container
- [ ] R2 bucket region measured from a representative connection
- [ ] R2 CORS set and verified with a real browser (not curl — curl ignores CORS)
- [ ] `spacepoint-worker-video` (`VideoWorkerSettings`, `max_jobs = 1`) deployed and healthy **before** any bulk enqueue
- [ ] uvicorn `--workers 3`, DB pool sized, `max_connections` checked
- [ ] nginx `client_max_body_size 4g`
- [ ] BBR confirmed on
- [ ] All videos `status = ready`, spot-checked in a browser across ≥3 different courses
- [ ] Rollback rehearsed end-to-end at least once
- [ ] Old local `lms-hls` tree still on disk and disk has headroom

---

## Phase 6 — After the competition (explicitly out of scope for this week)

1. **ABR ladder.** The one real quality gap left. One ffmpeg pass, `split` filter +
   `-var_stream_map`, produces 1080p/720p/480p variants and a master playlist sharing a single AES
   key — roughly 1.7× the CPU of a single rendition, not 3×, because the source is decoded once.
   This is what makes 20-second segments safe, and what stops a student on a weak connection from
   stalling instead of degrading. **Prerequisite for §2.1's 20s option.**
2. **Cloudflare custom domain + Cache Rule.** Puts the CDN in front of R2: edge cache hits are not
   billed as Class B operations and cut segment latency to single-digit milliseconds. Requires the
   domain to be a Cloudflare zone in the same account — either move `spacepoint.ae`'s nameservers
   off Hostinger, or (lower risk) add a separate cheap domain as a Cloudflare zone purely for
   `cdn.…`. Note that **`.ts` and `.m3u8` are not cached by Cloudflare's default rules** — a Cache
   Rule with an explicit Edge TTL is required, and its absence is the usual reason people report
   "R2 custom domain isn't caching". Serving video this way is explicitly permitted under
   Cloudflare's terms as long as the content is hosted in R2. The `r2.dev` managed subdomain is
   **not** an alternative — it is rate-limited to hundreds of requests/second and Cloudflare
   documents it as not for production.
3. **Streaming uploads.** `routers/lms/video.py` does `data = await file.read()` against a **4 GB**
   cap, then hands the whole `bytes` object to `video_service.attach_upload` — two full copies in
   RAM on a VPS that does not have that. Stream to a temp file instead. Not a competition
   risk if nobody uploads during the event; a real risk the moment someone does.
4. **Move `lms-video-sources` to R2** and reclaim ~20 GB of VPS disk.
5. Revisit `services/games/realtime.py`'s one-Redis-connection-per-student pattern only if live
   games are expected past ~100 concurrent per session.

---

## Sources

- Cloudflare R2 pricing (storage $0.015/GB-mo, Class A $4.50/M after 1M free, Class B $0.36/M
  after 10M free, $0 egress): https://egresscost.com/cloudflare/ ,
  https://www.bucketmate.app/blogs/cloudflare-r2-pricing-2026
- R2 presigned URLs point at the S3 endpoint, not a custom domain:
  https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- R2 public buckets / `r2.dev` rate limits and the custom-domain zone requirement:
  https://developers.cloudflare.com/r2/buckets/public-buckets/
- R2 location hints (`wnam/enam/weur/eeur/apac/oc`, set at creation only):
  https://developers.cloudflare.com/r2/reference/data-location/ ; region ping tool:
  https://r2-ping.fernandodilland.com/
- `.ts`/`.m3u8` are not cached by Cloudflare's default rules; a Cache Rule with an explicit Edge
  TTL is required: https://developers.cloudflare.com/cache/about/default-cache-behavior ,
  https://developers.cloudflare.com/cache/how-to/cache-rules/settings/
- Serving video through the CDN is permitted when hosted by R2 (2023 ToS change):
  https://blog.cloudflare.com/updated-tos
- Apple's 6-second HLS segment recommendation and the startup-latency mechanics:
  https://developer.apple.com/videos/play/wwdc2019/502/ ,
  https://aws.amazon.com/blogs/media/alhls-apple-low-latency-http-live-streaming-explained/
