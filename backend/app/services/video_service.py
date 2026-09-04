"""The standardized video service — one shared path for every feature to
attach, transcode, and play back a video, regardless of who owns it.

Replaces four duplicated code paths: `services/lms/video.py`'s ffmpeg/HLS
pipeline (absorbed here verbatim — it was never actually LMS-specific, just
homed under `services/lms/` because LMS was the only caller), the checklist
guideline video's link-only iframe embed, the Instructor Library's raw
`storage.upload_to_path`/`get_signed_url` calls, and the facilitator training
video's hand-typed URL with no signing at all. See `app/models/videos.py`
for the schema this operates on.

Access-checking is deliberately NOT done here — each feature's own router
keeps its own enrollment/role check (exactly as `routers/lms/video.py`'s
`_video_from_token`/`_assert_enrolled` already does), since the four
features' rules are genuinely unrelated in shape. This module only owns:
persisting a `Video` row, moving bytes through `storage`, running the HLS
transcode, and shaping playback info. Token issuance
(`core.security.create_video_token`/`decode_video_token`) stays a router-
owned call for the same reason — it's the point where a feature's access
check and a video's identity meet, which this module must not conflate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Literal

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.videos import Video
from app.services import storage

logger = logging.getLogger("services.video_service")

SOURCE_BUCKET = "video-sources"
# Unlike source_bucket (a real per-row column, correctly preserved by the
# migration's backfill for every pre-existing row), the HLS bucket was
# never persisted anywhere — old and new code alike just hardcode one
# constant and assume every row's playlist_path/key_path lives under it.
# The old services/lms/video.py used "lms-hls"; renaming this to
# "video-hls" here broke every video migrated from before this service
# existed (their real files still physically sit under "lms-hls" on disk/
# in whatever bucket store is configured) — 404s/FileNotFoundErrors on
# playback the moment this shipped. Keep the original name; it costs
# nothing to keep calling it that even though the service is now generic.
HLS_BUCKET = "lms-hls"

# 10s, raised from 4s. Cost was never the driver — R2's Class B free tier
# swallows this library's read volume at any of these lengths. What 10s buys is
# 2.5x fewer segment requests per playback with a first-segment download small
# enough (~2-3MB at these bitrates) not to punish a slow connection at startup.
# 20s was considered and rejected: with a single rendition there is no lower
# variant for hls.js to fall back to, and a 20s segment that cannot be fetched
# in 20s is an unrecoverable stall rather than a hiccup. Apple's own authoring
# guidance recommends 6s; 10s is already a deliberate step past that.
_SEGMENT_SECONDS = 10

# Delivery targets for the re-encode path. Measured against the real library
# (2026-09-04): every sampled source is 4K HEVC ~16 Mbps straight off an
# iPhone, and _probe_is_h264_aac rejected all of them, so 119 of 127 videos
# were being served at the old 720p/800k — visibly soft for slide and
# screen-recorded content. 1080p at capped CRF is a large quality upgrade for
# those, and a ~7x size reduction for the 8 H.264 sources that were sailing
# through the remux gate untouched at full source bitrate.
_MAX_HEIGHT = 1080
_MAX_FPS = 30
# The cap a source must already be under to be worth remuxing instead of
# re-encoding, and the ceiling the encoder is allowed to spend.
_MAX_SOURCE_KBPS = 3000
_TARGET_MAX_KBPS = 2500

# Same host-matching regex as frontend/src/lib/embed.ts::isKnownEmbedHost —
# keep the two in sync manually (no cross-language shared source; this
# codebase already duplicates the analogous _VIDEO_FORMATS/isVideoFormat
# extension set the same way, for the same reason).
_EMBED_HOST_RE = re.compile(r"youtu\.be|youtube\.com|vimeo\.com", re.IGNORECASE)

# Every new upload — any owner_type, any mode — lands here, never on local
# disk. VPS upload was a bootstrapping default from before R2 existed; it is
# no longer offered anywhere in the product, and this is the one place that
# rule is actually enforced, so a frontend that forgot to remove a VPS option
# still can't silently write one. Deliberately NOT `storage.default_video_
# backend()` — that setting can be blank (R2 creds not deployed yet) without
# silently reviving VPS uploads; if R2 isn't configured, a new upload fails
# loudly instead of landing somewhere nobody intended.
_NEW_UPLOAD_BACKEND = "r2"


def _hls_backend(video: Video) -> str | None:
    """Where this video's HLS output (playlist, segments, key) lives.

    Read from the row, never from settings — see the comment on
    Video.storage_backend for why that distinction is the whole design."""
    return video.storage_backend or None


def _source_backend(video: Video) -> str | None:
    """Where this video's `source_bucket`/`source_path` bytes live.

    The rule is about who reads the bytes, not what they are:

    - `hls_encrypted`: the source is a pre-transcode INPUT that only the ARQ
      worker ever opens. It stays on the default backend (local disk) — no
      student request touches it, and keeping it there means a transcode does
      not have to pull hundreds of megabytes back over the network first.
    - `direct`: the source IS the asset the browser fetches, so it follows the
      row's storage_backend like any other student-facing bytes.

    That distinction matters more than it looks. Served from local storage, a
    `direct` video goes through GET /files, which Fernet-decrypts the WHOLE
    blob into memory and returns one non-range response — Fernet is
    all-or-nothing, so byte ranges are not merely unimplemented there, they
    are unimplementable. A <video> element depends on ranges: it range-fetches
    the moov atom (at the END of any MP4 not written with +faststart) before
    it can play, and range-fetches again on every seek. Against a
    non-range-serving origin each of those restarts the entire download, which
    presents as a video that flashes one frame and drops back to buffering
    forever. An object store answers ranges natively, which is the actual fix.
    """
    return _hls_backend(video) if video.upload_mode == "direct" else None


def _content_type_for(name: str) -> str:
    """Content type to store alongside an object. Matters on an object store
    in a way it never did locally: R2 hands this header straight to the
    browser, with no app in between to re-infer it from the extension, and
    hls.js/<video> reject some of what they are handed without it."""
    if name.endswith(".ts"):
        return "video/mp2t"
    if name.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl"
    if name.endswith(".bin"):
        return "application/octet-stream"
    return {
        ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
        ".webm": "video/webm", ".mkv": "video/x-matroska", ".ogv": "video/ogg",
        ".ogg": "video/ogg", ".avi": "video/x-msvideo",
    }.get("." + name.rsplit(".", 1)[-1].lower() if "." in name else "", "video/mp4")


def _detect_provider(url: str) -> Literal["youtube", "vimeo"] | None:
    if not url or not _EMBED_HOST_RE.search(url):
        return None
    return "vimeo" if "vimeo.com" in url.lower() else "youtube"


# ── The HLS/AES pipeline — ported from services/lms/video.py unchanged ─────

@dataclass
class EncodeResult:
    playlist: bytes             # raw .m3u8 text, relative segment/key filenames
    segments: dict[str, bytes]  # filename -> .ts bytes
    key: bytes                  # 16-byte AES-128 key
    duration_seconds: int | None


Encoder = Callable[[Path], Awaitable[EncodeResult]]


def _run(cmd: list[str], *, low_priority: bool = False) -> str:
    """`low_priority` runs the command under `nice -n 19` — the API and the
    ARQ worker share one 4-vCPU box, so an unniced ffmpeg encode pins every
    core. POSIX-only (ffmpeg itself only ships in the Linux image)."""
    if low_priority and os.name == "posix":
        cmd = ["nice", "-n", "19", *cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


@dataclass
class SourceInfo:
    """What the remux-vs-re-encode decision needs to know about a source."""
    vcodec: str | None = None
    acodec: str | None = None
    height: int | None = None
    fps: float | None = None
    bitrate_kbps: int | None = None
    duration_seconds: int | None = None


def _parse_fps(rate: str | None) -> float | None:
    """ffprobe reports r_frame_rate as a rational string ("30/1", "60000/1001")."""
    if not rate or "/" not in rate:
        return None
    num, _, den = rate.partition("/")
    try:
        return float(num) / float(den) if float(den) else None
    except (ValueError, ZeroDivisionError):
        return None


def _probe_source(source: Path) -> SourceInfo:
    """One ffprobe call for everything, replacing the three separate ones this
    used to make (two codec probes plus a duration probe). Each probe re-opens
    and re-parses the container; on the 200-800MB 4K sources this library
    actually holds that was pure waste on the critical path."""
    try:
        raw = _run([
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_streams", "-show_format", str(source),
        ])
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Unreadable/probe-less source: report nothing known. _can_copy then
        # refuses to remux, so we re-encode — the safe direction, since a
        # bad remux ships broken segments while a bad encode fails loudly.
        return SourceInfo()

    try:
        probed = json.loads(raw)
    except json.JSONDecodeError:
        return SourceInfo()

    streams = probed.get("streams") or []
    video = next((st for st in streams if st.get("codec_type") == "video"), {})
    audio = next((st for st in streams if st.get("codec_type") == "audio"), {})
    fmt = probed.get("format") or {}

    try:
        duration = int(float(fmt["duration"]))
    except (KeyError, TypeError, ValueError):
        duration = None
    try:
        bitrate = int(fmt["bit_rate"]) // 1000
    except (KeyError, TypeError, ValueError):
        bitrate = None

    return SourceInfo(
        vcodec=video.get("codec_name"),
        acodec=audio.get("codec_name"),
        height=video.get("height"),
        fps=_parse_fps(video.get("r_frame_rate")),
        bitrate_kbps=bitrate,
        duration_seconds=duration,
    )


def _can_copy(info: SourceInfo) -> bool:
    """True when the source is ALREADY what we would have encoded anyway, so
    remuxing it is free rather than lossy.

    This used to gate on codec alone (`h264 and aac`), which meant any source
    that happened to be H.264 was copied through at its *original* resolution
    and bitrate. Confirmed live on 2026-09-04: 8 of 127 videos had HLS output
    the same size as a 250-750MB source, i.e. multi-megabit streams being
    served to students verbatim. Copying is still the right call when it
    applies — it is seconds of CPU instead of minutes on a box shared with the
    live API — but "is H.264" was never the question. `None` on any field means
    the probe could not tell us, and an unknown is treated as out-of-spec."""
    return (
        info.vcodec == "h264"
        and info.acodec == "aac"
        and info.height is not None and info.height <= _MAX_HEIGHT
        # 30fps sources probe as 30000/1001 = 29.97; allow a little headroom
        # rather than tripping on NTSC rounding.
        and info.fps is not None and info.fps <= _MAX_FPS + 1
        and info.bitrate_kbps is not None and info.bitrate_kbps <= _MAX_SOURCE_KBPS
    )


def _ffmpeg_encode_hls_sync(source: Path) -> EncodeResult:
    key = os.urandom(16)
    iv = os.urandom(16).hex()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        key_file = tmp_path / "key.bin"
        key_file.write_bytes(key)
        keyinfo_file = tmp_path / "keyinfo"
        # Line 1 is embedded literally as the playlist's key URI by ffmpeg —
        # a placeholder; the serving route rewrites it per-request to a
        # token-gated URL, never a static one.
        keyinfo_file.write_text(f"key\n{key_file}\n{iv}\n")

        playlist_path = tmp_path / "playlist.m3u8"
        segment_pattern = str(tmp_path / "segment_%03d.ts")

        info = _probe_source(source)
        codec_args = (
            ["-c", "copy"] if _can_copy(info)
            else [
                # Explicit stream selection. iPhone recordings — which is what
                # this library is — carry several `mebx` timed-metadata streams
                # alongside video and audio; none of them belong in an mpegts
                # segment. `0:a:0?` keeps a silent source from failing outright.
                "-map", "0:v:0", "-map", "0:a:0?",
                # min() clamps rather than forcing: `scale=-2:1080` would
                # UPSCALE anything already smaller, producing a bigger, softer
                # file than the source. force_divisible_by=2 keeps both
                # dimensions even, which H.264 4:2:0 requires.
                "-vf",
                f"scale='min(1920,iw)':'min({_MAX_HEIGHT},ih)'"
                f":force_original_aspect_ratio=decrease:force_divisible_by=2,fps={_MAX_FPS}",
                # veryfast, not fast/medium: the API and this worker share one
                # 4-vCPU box, and the sources are 4K HEVC whose decode alone
                # costs more than the encode. The -maxrate cap absorbs the
                # slight bitrate cost of the faster preset.
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-maxrate", f"{_TARGET_MAX_KBPS}k", "-bufsize", f"{_TARGET_MAX_KBPS * 2}k",
                # Guarantees decode on older Android/Safari, for an audience
                # whose devices we do not control.
                "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
                # Forced keyframes at exactly the segment boundary so -hls_time
                # cuts land precisely instead of drifting to wherever the
                # encoder's own GOP structure put the nearest keyframe. Only
                # meaningful here — the -c copy path above cannot move existing
                # keyframes without re-encoding, so its segments land on the
                # first source keyframe at or after the target.
                "-force_key_frames", f"expr:gte(t,n_forced*{_SEGMENT_SECONDS})",
                # Speech at 96k stereo AAC is transparent; the sources carry
                # 128-192k of mostly-silence room tone.
                "-c:a", "aac", "-b:a", "96k", "-ac", "2",
            ]
        )
        _run([
            "ffmpeg", "-y", "-i", str(source), *codec_args,
            "-f", "hls", "-hls_time", str(_SEGMENT_SECONDS), "-hls_playlist_type", "vod",
            "-hls_key_info_file", str(keyinfo_file),
            "-hls_segment_filename", segment_pattern,
            str(playlist_path),
        ], low_priority=True)

        segments = {p.name: p.read_bytes() for p in sorted(tmp_path.glob("segment_*.ts"))}
        return EncodeResult(
            playlist=playlist_path.read_bytes(),
            segments=segments,
            key=key,
            duration_seconds=info.duration_seconds,
        )


async def _ffmpeg_encode_hls(source: Path) -> EncodeResult:
    return await anyio.to_thread.run_sync(_ffmpeg_encode_hls_sync, source)


# ── Attach / detach ─────────────────────────────────────────────────────

async def _delete_storage(video: Video) -> None:
    """Best-effort cleanup of whatever storage objects this video owns —
    called before replacing an owner's existing video and before a real
    delete(). Never raises: a storage 404 on an already-gone object (or a
    row that never finished uploading) shouldn't block the DB write."""
    try:
        if video.upload_mode == "hls_encrypted":
            # Derived from playlist_path's own directory, not video.id — a
            # row backfilled from the old ModuleVideo table keeps its
            # original item_id-prefixed storage layout (playlist_path
            # copied verbatim by the migration), which doesn't equal this
            # row's new, freshly-generated id. Falls back to video.id only
            # when there's no playlist yet (still "pending" — nothing to
            # list/delete either way).
            prefix = (video.playlist_path.rsplit("/", 1)[0] if video.playlist_path else str(video.id)) + "/"
            hls_backend = _hls_backend(video)
            for entry in await storage.list_files(HLS_BUCKET, prefix, backend=hls_backend):
                if entry.get("metadata") is not None:  # a file, not a folder
                    await storage.delete_file(HLS_BUCKET, f"{prefix}{entry['name']}", backend=hls_backend)
        if video.source_bucket and video.source_path:
            await storage.delete_file(
                video.source_bucket, video.source_path,
                backend=_source_backend(video),
            )
    except Exception:  # noqa: BLE001 — cleanup is best-effort
        logger.exception("Failed to clean up storage for video %s", video.id)


async def get_video_for_owner(db: AsyncSession, *, owner_type: str, owner_id: uuid.UUID) -> Video | None:
    return (await db.execute(
        select(Video).where(Video.owner_type == owner_type, Video.owner_id == owner_id)
    )).scalars().first()


async def attach_embed_link(
    db: AsyncSession, *, owner_type: str, owner_id: uuid.UUID, url: str,
    created_by: uuid.UUID | None = None,
) -> Video:
    """Upserts the one Video row for this owner as an embed link. Raises
    ValueError for a host toEmbedUrl()/isKnownEmbedHost() wouldn't recognize
    either, rather than storing an unplayable provider."""
    provider = _detect_provider(url)
    if provider is None:
        raise ValueError(f"Unrecognized video host: {url!r}")

    video = await get_video_for_owner(db, owner_type=owner_type, owner_id=owner_id)
    if video is not None:
        await _delete_storage(video)
    else:
        video = Video(owner_type=owner_type, owner_id=owner_id)
        db.add(video)

    video.provider = provider
    video.upload_mode = None
    video.status = "ready"
    video.status_error = None
    video.embed_url = url
    video.source_bucket = None
    video.source_path = None
    video.playlist_path = None
    video.key_path = None
    video.duration_seconds = None
    video.created_by = created_by
    await db.commit()
    await db.refresh(video)
    return video


async def attach_upload(
    db: AsyncSession, *, owner_type: str, owner_id: uuid.UUID, file_bytes: bytes, filename: str,
    content_type: str | None, mode: Literal["hls_encrypted", "direct"],
    created_by: uuid.UUID | None = None,
) -> Video:
    """Upserts the one Video row for this owner and uploads the source bytes.
    Every call — any owner_type, any mode — lands on `_NEW_UPLOAD_BACKEND`
    ("r2"), never local disk; VPS is no longer a destination this function
    will ever write a fresh upload to (see that constant's own note). This is
    a genuinely new upload (a replace discards whatever the owner had before
    via `_delete_storage`), not a re-encode of existing content, so there is
    no live traffic on this exact row/content to protect — unlike
    `run_encrypted_transcode`'s zero-downtime path, flipping `storage_backend`
    immediately here is safe.

    `mode="direct"` flips straight to `status="ready"` — the uploaded file IS
    the served asset, nothing async happens. `mode="hls_encrypted"` sets
    `status="pending"` and returns; the caller is responsible for calling
    `enqueue_transcode` separately, so this stays a pure DB+storage
    primitive, testable without a Redis dependency."""
    existing = await get_video_for_owner(db, owner_type=owner_type, owner_id=owner_id)
    if existing is not None:
        await _delete_storage(existing)
        video = existing
    else:
        # id is assigned client-side (not server-generated) specifically so
        # it's already known here for the storage path below, without an
        # early flush — flushing now would insert a row with `provider`
        # still unset, violating its NOT NULL constraint.
        video = Video(id=uuid.uuid4(), owner_type=owner_type, owner_id=owner_id)
        db.add(video)

    # Set before the upload, not after: _source_backend() reads upload_mode and
    # storage_backend off the row to decide where the bytes go, so assigning
    # them afterwards would upload to the wrong place.
    video.upload_mode = mode
    video.storage_backend = _NEW_UPLOAD_BACKEND

    suffix = Path(filename or "video.mp4").suffix or ".mp4"
    source_path = f"{video.id}/source{suffix}"
    await storage.upload_to_path(
        SOURCE_BUCKET, source_path, file_bytes, _content_type_for(source_path),
        backend=_source_backend(video),
    )

    video.provider = "upload"
    video.status = "ready" if mode == "direct" else "pending"
    video.status_error = None
    video.embed_url = None
    video.source_bucket = SOURCE_BUCKET
    video.source_path = source_path
    video.playlist_path = None
    video.key_path = None
    video.duration_seconds = None
    video.created_by = created_by
    await db.commit()
    await db.refresh(video)
    return video


async def enqueue_transcode(
    arq_redis, video_id: uuid.UUID, *, target_backend: str | None = None,
) -> str:
    """Thin wrapper so callers don't need to know the ARQ job name — one
    shared job ("transcode_video") replaces the LMS-only "transcode_lms_video".

    `target_backend` is where the OUTPUT should land; the row is repointed
    there only once the encode succeeds."""
    from app.workers.settings import safe_enqueue
    return await safe_enqueue(arq_redis, "transcode_video", str(video_id), target_backend)


async def run_encrypted_transcode(
    db: AsyncSession, video_id: uuid.UUID, *,
    encoder: Encoder | None = None, target_backend: str | None = None,
) -> None:
    """The ARQ job body for `upload_mode="hls_encrypted"` videos — same
    download/ffprobe/ffmpeg/upload/status-transition shape
    `services/lms/video.py::run_transcode` used, generalized to work off
    `video_id` instead of `item_id`. Never raises — a failure is recorded on
    the row (`failed` + `status_error`), not thrown at the worker, since
    nothing awaits this job synchronously.

    `target_backend=None` means "no override — write to wherever this row's
    storage_backend already says", not "target the VPS explicitly". That is
    deliberate, not just the simplest reading: this value crosses an ARQ job
    boundary (Redis-serialized, then re-passed by transcode_video's own
    `target_backend: str | None = None` parameter), so a sentinel object
    identity would not survive the round trip — a fresh upload's ordinary
    post-attach transcode (no override given) and an explicit "re-encode onto
    the VPS" request would collapse into the same `None` on the other side,
    silently writing a "r2"-stamped row's output to the wrong place. Rolling
    a single video back to the VPS is `move_to_backend`'s job (a copy, not a
    re-encode) for exactly this reason — see the migration script."""
    encode = encoder or _ffmpeg_encode_hls

    video = await db.get(Video, video_id)
    if video is None:
        logger.warning("run_encrypted_transcode: no Video row %s", video_id)
        return

    target = target_backend if target_backend is not None else video.storage_backend

    # A video that is currently servable keeps serving while it re-encodes.
    #
    # `status` is what gates playback (the token endpoint 409s on anything but
    # "ready"), so downgrading it to "processing" would take a working video
    # away from students for the length of an encode — and, if the encode
    # failed, leave it "failed" and unplayable even though its existing output
    # is still sitting there intact. That is unacceptable for a re-encode of
    # 127 already-working videos.
    #
    # Writing to a DIFFERENT backend is what makes this safe: the new output
    # lands beside the old rather than over it, so until the swap at the end
    # the row still points at bytes that are complete and correct. A first-time
    # transcode has nothing to serve, so it takes the normal path.
    swap_in_place = bool(video.playlist_path) and video.status == "ready" and target != video.storage_backend
    if not swap_in_place:
        video.status = "processing"
        video.status_error = None
        await db.commit()

    try:
        source_bytes = await storage.download_file(video.source_bucket, video.source_path)
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "source"
            source_file.write_bytes(source_bytes)
            result = await encode(source_file)

        # Reuse the row's established prefix rather than always writing to
        # str(video_id), so a RE-encode overwrites in place instead of
        # relocating. Rows backfilled by the unify_video_service migration
        # carry an owner_id-shaped prefix (playlist_path was copied verbatim
        # onto a freshly-generated id, so prefix != video.id for every video
        # that predates that migration); a fresh upload has no playlist_path
        # yet and gets video.id, exactly as before.
        #
        # Keeping the prefix stable is what makes a hot re-encode's old copy a
        # true rollback: the pre-existing tree on the OLD backend and the
        # newly written tree on `target` occupy the SAME key, untouched by
        # each other (different physical stores), so setting this row's
        # storage_backend back to the old value re-serves the old output
        # as-is. Writing to a new prefix would strand that old copy at a path
        # nothing points at.
        prefix = video.playlist_path.rsplit("/", 1)[0] if video.playlist_path else str(video_id)
        hls_backend = target
        for name, data in result.segments.items():
            await storage.upload_to_path(
                HLS_BUCKET, f"{prefix}/{name}", data, "video/mp2t", backend=hls_backend
            )
        await storage.upload_to_path(
            HLS_BUCKET, f"{prefix}/playlist.m3u8", result.playlist,
            "application/vnd.apple.mpegurl", backend=hls_backend,
        )
        await storage.upload_to_path(
            HLS_BUCKET, f"{prefix}/key.bin", result.key,
            "application/octet-stream", backend=hls_backend,
        )

        # The atomic swap. Everything above wrote to `target`; only now does
        # the row start pointing there, in the same commit that marks it ready.
        # Before this line the video served from its old backend; after it, the
        # new one. There is no in-between a request can observe.
        video.playlist_path = f"{prefix}/playlist.m3u8"
        video.key_path = f"{prefix}/key.bin"
        video.duration_seconds = result.duration_seconds
        video.storage_backend = target
        video.status = "ready"
        await db.commit()
    except asyncio.CancelledError:
        # arq's job_timeout cancels the task from outside — CancelledError is
        # a BaseException (not Exception, since Python 3.8), so it would
        # otherwise skip the handler below entirely and leave the row stuck
        # at "processing" forever with no automatic retry. Record failure,
        # then re-raise so arq's own cancellation/retry bookkeeping still
        # sees it.
        logger.exception("Transcode cancelled (job timeout?) for video %s", video_id)
        # Only mark it failed if it was not already serving something. A
        # re-encode that dies must leave the working video exactly as it was.
        if not swap_in_place:
            video.status = "failed"
        video.status_error = "Transcode timed out or was cancelled"
        await db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 — record on the row, never crash the worker
        logger.exception("Transcode failed for video %s", video_id)
        if not swap_in_place:
            video.status = "failed"
        video.status_error = str(exc)[:2000]
        await db.commit()


async def move_to_backend(
    db: AsyncSession, video: Video, target: str | None, *, dry_run: bool = False,
) -> dict:
    """Copy this video's student-facing bytes to `target` and repoint the row.

    COPY, never move. The bytes are left on the origin backend untouched, so
    setting `storage_backend` back is a complete, instant rollback for this one
    video — no re-upload, no re-encode, nothing to restore. Reclaiming the old
    copies is a separate, deliberate cleanup once a video has been watched in
    anger from its new home.

    Every object is verified by reading it back and comparing sizes before the
    row is repointed. A half-copied video that the row already claims is on R2
    is worse than one that was never moved: it fails at playback, for students,
    rather than here, for us.

    `target=None` means the deployment default (the VPS). Returns a summary
    dict rather than raising on a per-object problem, so a caller moving 127
    videos can report which ones need attention and keep going.
    """
    origin = video.storage_backend or None
    if origin == (target or None):
        return {"video_id": str(video.id), "moved": 0, "skipped": "already there"}

    # (bucket, path) pairs to copy — exactly the objects a student fetches.
    objects: list[tuple[str, str]] = []
    if video.upload_mode == "hls_encrypted":
        if not video.playlist_path:
            return {"video_id": str(video.id), "error": "no playlist yet (never transcoded)"}
        prefix = video.playlist_path.rsplit("/", 1)[0] + "/"
        for entry in await storage.list_files(HLS_BUCKET, prefix, backend=origin):
            if entry.get("metadata") is not None:  # a file, not a folder
                objects.append((HLS_BUCKET, f"{prefix}{entry['name']}"))
        if not objects:
            return {"video_id": str(video.id), "error": f"no HLS objects under {prefix}"}
    elif video.upload_mode == "direct":
        if not (video.source_bucket and video.source_path):
            return {"video_id": str(video.id), "error": "no source on file"}
        objects.append((video.source_bucket, video.source_path))
    else:
        # An embed link hosts no bytes of ours; there is nothing to move.
        return {"video_id": str(video.id), "moved": 0, "skipped": "embed link"}

    if dry_run:
        return {"video_id": str(video.id), "would_move": len(objects),
                "from": origin or "default", "to": target or "default"}

    copied = 0
    for bucket, path in objects:
        data = await storage.download_file(bucket, path, backend=origin)
        await storage.upload_to_path(
            bucket, path, data, _content_type_for(path), backend=target,
        )
        check = await storage.download_file(bucket, path, backend=target)
        if len(check) != len(data):
            return {"video_id": str(video.id), "error":
                    f"verify failed on {path}: wrote {len(data)}, read back {len(check)}",
                    "copied_before_failure": copied}
        copied += 1

    video.storage_backend = target or None
    await db.commit()
    await db.refresh(video)
    return {"video_id": str(video.id), "moved": copied,
            "from": origin or "default", "to": target or "default"}


async def convert_to_hls_encrypted(db: AsyncSession, video: Video) -> dict:
    """One-time mode change: a `direct`-mode video (a raw file served
    as-is, byte-range playback only) becomes `hls_encrypted` — compressed
    and streamed through the same pipeline every LMS course module video
    already uses. For an existing direct upload sitting at 4K, this is the
    actual compression step; `--move` only ever made such a file seekable,
    never smaller.

    Does not itself run ffmpeg — it repoints the row and leaves the actual
    encode to run_encrypted_transcode, exactly like a fresh hls_encrypted
    upload does. Caller enqueues the transcode job separately (same
    attach_upload/enqueue_transcode split, same reason: keep this a pure
    DB+storage primitive, testable without Redis).

    The one thing this must get right that a fresh upload never has to
    worry about: run_encrypted_transcode's source download
    (storage.download_file(video.source_bucket, video.source_path), no
    backend= override — see that function's body) always reads from the
    DEPLOYMENT DEFAULT backend, because a genuine hls_encrypted upload's
    source only ever lands there (_source_backend returns None for that
    mode, by design — the source is a worker-only input, never worth
    shipping to an object store). A `direct` video's source, by contrast,
    follows ITS OWN storage_backend — which may already be "r2" if this
    video went through `--move --to r2 --mode direct` before this
    conversion existed. So before flipping the mode, this copies the source
    back to the default backend under the SAME (bucket, path) key, so the
    transcode job finds it exactly where it always expects to look. The
    old copy on whatever backend it came from is left in place — cheap,
    and exactly this module's usual "copy, never delete the origin until
    something has been proven to work from the new location" posture.
    """
    if video.upload_mode != "direct":
        return {"video_id": str(video.id), "error": f"not direct mode (currently {video.upload_mode})"}
    if not (video.source_bucket and video.source_path):
        return {"video_id": str(video.id), "error": "no source on file"}

    current_backend = _source_backend(video)  # still "direct" here -> video.storage_backend
    if current_backend is not None:
        data = await storage.download_file(video.source_bucket, video.source_path, backend=current_backend)
        await storage.upload_to_path(
            video.source_bucket, video.source_path, data, _content_type_for(video.source_path),
            backend=None,  # the default backend — where run_encrypted_transcode will look
        )

    video.upload_mode = "hls_encrypted"
    video.status = "pending"
    video.status_error = None
    # storage_backend is left as-is on purpose: the moment upload_mode flips,
    # _hls_backend reinterprets that same column as "where the HLS OUTPUT
    # should land" rather than "where the source is" — for anything uploaded
    # since the R2 switch it is already "r2", which is exactly right.
    await db.commit()
    await db.refresh(video)
    return {"video_id": str(video.id), "converted": True}


async def get_playback_info(db: AsyncSession, video: Video, *, signed_url_expires_in: int = 3600) -> dict:
    """Shape depends on provider/mode — deliberately never includes a token
    or a segment/key URL for hls_encrypted: token issuance stays a
    router-owned call coupled to that feature's own access check.

    `video_id` is included in every shape (even embed, where it is not
    strictly needed) so a caller never has to thread the id through
    separately from this dict — the shared frontend <VideoPlayer> fetches its
    own hls_encrypted token off `info.video_id` rather than taking a second
    prop that could drift out of sync with which video `info` actually
    describes."""
    if video.provider != "upload":
        return {
            "provider": video.provider, "embed_url": video.embed_url, "status": video.status,
            "video_id": str(video.id),
        }
    # storage_backend is surfaced so authoring UIs can show where a video
    # actually lives ("VPS" / "R2") and offer to move it.
    if video.upload_mode == "direct":
        url = await storage.resolve_url(
            video.source_bucket, video.source_path,
            expires_in=signed_url_expires_in, backend=_source_backend(video),
        )
        return {
            "provider": "upload", "mode": "direct", "status": video.status,
            "url": url, "duration_seconds": video.duration_seconds,
            "storage_backend": video.storage_backend, "video_id": str(video.id),
        }
    return {
        "provider": "upload", "mode": "hls_encrypted", "status": video.status,
        "status_error": video.status_error, "duration_seconds": video.duration_seconds,
        "storage_backend": video.storage_backend, "video_id": str(video.id),
    }


async def delete(db: AsyncSession, video: Video) -> None:
    await _delete_storage(video)
    await db.delete(video)
    await db.commit()
