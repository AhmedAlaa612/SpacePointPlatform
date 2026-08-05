"""LMS video pipeline (LM1-6) — ffprobe/ffmpeg → AES-128 HLS.

`run_transcode` is the ARQ job body (called from workers/tasks/lms.py). The
actual subprocess-calling step is `_ffmpeg_encode_hls`, reached only through
the injectable `encoder` param — tests pass a fake encoder so the DB/storage/
status-transition plumbing is covered **without** shelling out to real ffmpeg
(LM1-6 spec: "not running real ffmpeg in tests"; ffmpeg itself only exists in
the Docker image, not this dev machine).

D2: ffprobe first — `-c copy` remux when the source is already H.264/AAC
(seconds, not minutes), 720p transcode as the fallback. Single rendition, no
quality ladder (§8 Q1, closed).
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms import ModuleVideo
from app.services import storage

logger = logging.getLogger("services.lms.video")

HLS_BUCKET = "lms-hls"
_SEGMENT_SECONDS = 6


@dataclass
class EncodeResult:
    playlist: bytes             # raw .m3u8 text, relative segment/key filenames
    segments: dict[str, bytes]  # filename -> .ts bytes
    key: bytes                  # 16-byte AES-128 key
    duration_seconds: int | None


Encoder = Callable[[Path], Awaitable[EncodeResult]]


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


def _probe_is_h264_aac(source: Path) -> bool:
    try:
        video_codec = _run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(source),
        ]).strip()
        audio_codec = _run([
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(source),
        ]).strip()
        return video_codec == "h264" and audio_codec == "aac"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _probe_duration(source: Path) -> int | None:
    try:
        out = _run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(source),
        ]).strip()
        return int(float(out))
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None


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
        # token-gated URL (routers/lms/video.py), never a static one (D2).
        keyinfo_file.write_text(f"key\n{key_file}\n{iv}\n")

        playlist_path = tmp_path / "playlist.m3u8"
        segment_pattern = str(tmp_path / "segment_%03d.ts")

        codec_args = (
            ["-c", "copy"] if _probe_is_h264_aac(source)
            else ["-c:v", "libx264", "-vf", "scale=-2:720", "-c:a", "aac"]
        )
        _run([
            "ffmpeg", "-y", "-i", str(source), *codec_args,
            "-f", "hls", "-hls_time", str(_SEGMENT_SECONDS), "-hls_playlist_type", "vod",
            "-hls_key_info_file", str(keyinfo_file),
            "-hls_segment_filename", segment_pattern,
            str(playlist_path),
        ])

        segments = {p.name: p.read_bytes() for p in sorted(tmp_path.glob("segment_*.ts"))}
        return EncodeResult(
            playlist=playlist_path.read_bytes(),
            segments=segments,
            key=key,
            duration_seconds=_probe_duration(source),
        )


async def _ffmpeg_encode_hls(source: Path) -> EncodeResult:
    return await anyio.to_thread.run_sync(_ffmpeg_encode_hls_sync, source)


async def run_transcode(db: AsyncSession, item_id: uuid.UUID, *, encoder: Encoder | None = None) -> None:
    """Downloads the source, encodes (real ffmpeg by default), uploads the
    HLS output, and flips `transcode_status`. Never raises — a failure is
    recorded on the row (`failed` + `transcode_error`), not thrown at the
    worker, since nothing awaits this job synchronously."""
    encode = encoder or _ffmpeg_encode_hls

    video = (await db.execute(
        select(ModuleVideo).where(ModuleVideo.item_id == item_id)
    )).scalars().first()
    if video is None:
        logger.warning("run_transcode: no ModuleVideo row for item %s", item_id)
        return

    video.transcode_status = "processing"
    video.transcode_error = None
    await db.commit()

    try:
        source_bytes = await storage.download_file(video.source_bucket, video.source_path)
        with tempfile.TemporaryDirectory() as tmp:
            source_file = Path(tmp) / "source"
            source_file.write_bytes(source_bytes)
            result = await encode(source_file)

        prefix = str(item_id)
        for name, data in result.segments.items():
            await storage.upload_to_path(HLS_BUCKET, f"{prefix}/{name}", data, "video/mp2t")
        await storage.upload_to_path(
            HLS_BUCKET, f"{prefix}/playlist.m3u8", result.playlist, "application/vnd.apple.mpegurl"
        )
        await storage.upload_to_path(HLS_BUCKET, f"{prefix}/key.bin", result.key, "application/octet-stream")

        video.playlist_path = f"{prefix}/playlist.m3u8"
        video.key_path = f"{prefix}/key.bin"
        video.duration_seconds = result.duration_seconds
        video.transcode_status = "ready"
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — record on the row, never crash the worker
        logger.exception("Transcode failed for item %s", item_id)
        video.transcode_status = "failed"
        video.transcode_error = str(exc)[:2000]
        await db.commit()
