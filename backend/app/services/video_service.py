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


def _hls_backend() -> str | None:
    """The storage backend the HLS output (playlist/segments/key) lives on.

    Only the HLS output moves. `source_bucket`/`source_path` stay on the
    default backend deliberately: the sources are ~33GB that only the worker
    ever reads, never a student request, and keeping them local means a
    transcode does not have to pull hundreds of megabytes back over the network
    before it can start."""
    return storage.video_backend()


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
            hls_backend = _hls_backend()
            for entry in await storage.list_files(HLS_BUCKET, prefix, backend=hls_backend):
                if entry.get("metadata") is not None:  # a file, not a folder
                    await storage.delete_file(HLS_BUCKET, f"{prefix}{entry['name']}", backend=hls_backend)
        if video.source_bucket and video.source_path:
            await storage.delete_file(video.source_bucket, video.source_path)
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
    `mode="direct"` flips straight to `status="ready"` — the uploaded file
    IS the served asset, nothing async happens. `mode="hls_encrypted"` sets
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

    suffix = Path(filename or "video.mp4").suffix or ".mp4"
    source_path = f"{video.id}/source{suffix}"
    await storage.upload_to_path(SOURCE_BUCKET, source_path, file_bytes, content_type or "video/mp4")

    video.provider = "upload"
    video.upload_mode = mode
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


async def enqueue_transcode(arq_redis, video_id: uuid.UUID) -> str:
    """Thin wrapper so callers don't need to know the ARQ job name — one
    shared job ("transcode_video") replaces the LMS-only "transcode_lms_video"."""
    from app.workers.settings import safe_enqueue
    return await safe_enqueue(arq_redis, "transcode_video", str(video_id))


async def run_encrypted_transcode(db: AsyncSession, video_id: uuid.UUID, *, encoder: Encoder | None = None) -> None:
    """The ARQ job body for `upload_mode="hls_encrypted"` videos — same
    download/ffprobe/ffmpeg/upload/status-transition shape
    `services/lms/video.py::run_transcode` used, generalized to work off
    `video_id` instead of `item_id`. Never raises — a failure is recorded on
    the row (`failed` + `status_error`), not thrown at the worker, since
    nothing awaits this job synchronously."""
    encode = encoder or _ffmpeg_encode_hls

    video = await db.get(Video, video_id)
    if video is None:
        logger.warning("run_encrypted_transcode: no Video row %s", video_id)
        return

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
        # Keeping the prefix stable is what makes the storage-backend switch a
        # true rollback: the pre-existing local HLS tree and the newly written
        # R2 tree occupy the SAME key, so flipping VIDEO_STORAGE_BACKEND back
        # re-serves the old output from the same unmodified DB row. Writing to
        # a new prefix would strand the local copy at a path nothing points at.
        prefix = video.playlist_path.rsplit("/", 1)[0] if video.playlist_path else str(video_id)
        hls_backend = _hls_backend()
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

        video.playlist_path = f"{prefix}/playlist.m3u8"
        video.key_path = f"{prefix}/key.bin"
        video.duration_seconds = result.duration_seconds
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
        video.status = "failed"
        video.status_error = "Transcode timed out or was cancelled"
        await db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 — record on the row, never crash the worker
        logger.exception("Transcode failed for video %s", video_id)
        video.status = "failed"
        video.status_error = str(exc)[:2000]
        await db.commit()


async def get_playback_info(db: AsyncSession, video: Video, *, signed_url_expires_in: int = 3600) -> dict:
    """Shape depends on provider/mode — deliberately never includes a token
    or a segment/key URL for hls_encrypted: token issuance stays a
    router-owned call coupled to that feature's own access check."""
    if video.provider != "upload":
        return {"provider": video.provider, "embed_url": video.embed_url, "status": video.status}
    if video.upload_mode == "direct":
        url = await storage.resolve_url(video.source_bucket, video.source_path, expires_in=signed_url_expires_in)
        return {
            "provider": "upload", "mode": "direct", "status": video.status,
            "url": url, "duration_seconds": video.duration_seconds,
        }
    return {
        "provider": "upload", "mode": "hls_encrypted", "status": video.status,
        "status_error": video.status_error, "duration_seconds": video.duration_seconds,
    }


async def delete(db: AsyncSession, video: Video) -> None:
    await _delete_storage(video)
    await db.delete(video)
    await db.commit()
