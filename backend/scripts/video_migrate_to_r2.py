"""Move the video library onto R2, and re-encode it to the current targets.

Two independent jobs, deliberately in one script because they are the two
halves of the same cutover and share every filter and safety check:

  --copy-direct   Copy `direct`-mode videos' source bytes to the video backend.
                  These are the files a browser fetches straight from
                  `<video src>` (Instructor Library, facilitator training).
                  Served from local storage they go through GET /files, which
                  Fernet-decrypts the whole blob into memory and answers with a
                  single non-range response — and a <video> element NEEDS byte
                  ranges, both for the moov atom at the end of a non-faststart
                  MP4 and for every seek. Against a non-range origin each of
                  those restarts the whole download, which is why a Library
                  video "opens for a second then goes back to loading".
                  Copy only — the local original is left in place, so
                  unsetting VIDEO_STORAGE_BACKEND puts you back exactly.

  --reencode      Re-run the HLS transcode for `hls_encrypted` videos, writing
                  output to the video backend at the CURRENT encode targets
                  (1080p30, capped CRF, 10s segments). Necessary because the
                  old remux gate checked codec only: sources that were already
                  H.264 were copied through at full resolution and bitrate,
                  and everything else was crushed to 720p/800k.

USAGE (inside the api or worker container, where the env is loaded)

    python -m scripts.video_migrate_to_r2 --copy-direct --dry-run
    python -m scripts.video_migrate_to_r2 --copy-direct

    python -m scripts.video_migrate_to_r2 --reencode --dry-run
    python -m scripts.video_migrate_to_r2 --reencode --limit 2      # test two first
    python -m scripts.video_migrate_to_r2 --reencode

BEFORE --reencode, non-negotiable:

  1. `max_jobs = 1` must be deployed (app/workers/main.py). arq defaults to 10,
     and ten concurrent ffmpeg encodes on a 4-vCPU box takes the live platform
     down with it.
  2. Dump the columns this touches, so the storage-backend flip stays a real
     rollback even if something goes wrong:

     psql -d spacepoint_unified -c "\\copy (SELECT id, owner_id, playlist_path, \\
       key_path, duration_seconds, status FROM videos WHERE owner_type='module_item') \\
       TO '/root/videos_pre_reencode.csv' CSV HEADER"

  3. Do NOT run deploy-backend.sh while this is draining. `docker rm -f` is
     SIGKILL; it bypasses run_encrypted_transcode's CancelledError handler and
     leaves rows stuck at "processing" with nothing to retry them.

WHAT --reencode DELIBERATELY DOES NOT DO

  It does not clear `playlist_path`/`key_path`. run_encrypted_transcode reuses
  the row's existing prefix, so the re-encode overwrites in place instead of
  relocating to a `video.id`-shaped path. That is what keeps the newly written
  R2 tree at the SAME key as the pre-existing local one — which is the entire
  rollback story: flip VIDEO_STORAGE_BACKEND back and the same unmodified rows
  resolve to the old local output. Clearing those columns would strand every
  local tree at a path no row points at.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from arq import create_pool
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.videos import Video
from app.services import storage
from app.services.video_service import _source_backend
from app.workers.settings import redis_settings


def _fmt_mb(n: int) -> str:
    return f"{n / 1_000_000:.1f}MB"


async def copy_direct(args: argparse.Namespace) -> int:
    target = storage.video_backend()
    if target is None:
        print("VIDEO_STORAGE_BACKEND is unset — there is nowhere to copy to.", file=sys.stderr)
        print("Set it (e.g. r2) in the container env before running this.", file=sys.stderr)
        return 2

    failures = 0
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Video).where(Video.provider == "upload", Video.upload_mode == "direct")
        )).scalars().all()
        if args.limit:
            rows = rows[: args.limit]
        print(f"{len(rows)} direct-mode video(s) to copy -> backend={target}\n")

        for video in rows:
            label = f"{str(video.id)[:8]} {video.owner_type}/{str(video.owner_id)[:8]}"
            if not (video.source_bucket and video.source_path):
                print(f"  SKIP  {label}  (no source on file)")
                continue
            try:
                # Read from the DEFAULT backend explicitly. _source_backend now
                # reports the video backend for direct rows, which is where we
                # are copying TO — reading through it would just re-read the
                # object we have not written yet.
                data = await storage.download_file(
                    video.source_bucket, video.source_path, backend=None,
                )
            except FileNotFoundError:
                print(f"  MISS  {label}  {video.source_bucket}/{video.source_path} not on local disk")
                failures += 1
                continue

            if args.dry_run:
                print(f"  DRY   {label}  would copy {_fmt_mb(len(data))} -> {target}")
                continue

            await storage.upload_to_path(
                video.source_bucket, video.source_path, data,
                # Content type matters here in a way it never did locally: R2
                # serves this header straight to the browser, and a <video>
                # given application/octet-stream may refuse to play it.
                _guess_video_type(video.source_path),
                backend=target,
            )
            # Verify by reading it back rather than trusting the write. One
            # extra GET per video is nothing against silently shipping a
            # truncated upload.
            check = await storage.download_file(
                video.source_bucket, video.source_path, backend=target,
            )
            if len(check) != len(data):
                print(f"  FAIL  {label}  size mismatch: wrote {len(data)}, read back {len(check)}")
                failures += 1
                continue
            print(f"  OK    {label}  {_fmt_mb(len(data))} copied and verified")

    print(f"\n{'DRY RUN — nothing written' if args.dry_run else 'Done'}. {failures} failure(s).")
    print("Local originals were NOT deleted — unsetting VIDEO_STORAGE_BACKEND restores them.")
    return 1 if failures else 0


def _guess_video_type(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "mp4": "video/mp4", "m4v": "video/mp4", "mov": "video/quicktime",
        "webm": "video/webm", "mkv": "video/x-matroska", "ogv": "video/ogg",
        "ogg": "video/ogg", "avi": "video/x-msvideo",
    }.get(ext, "video/mp4")


async def reencode(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(Video).where(
            Video.provider == "upload", Video.upload_mode == "hls_encrypted"
        ).order_by(Video.created_at)
        if args.video_id:
            stmt = stmt.where(Video.id == uuid.UUID(args.video_id))
        rows = (await db.execute(stmt)).scalars().all()
        if args.limit:
            rows = rows[: args.limit]

        target = storage.video_backend() or "(default backend)"
        print(f"{len(rows)} video(s) to re-encode -> HLS output on {target}\n")
        if not rows:
            return 0

        if args.dry_run:
            for video in rows:
                prefix = (video.playlist_path or "").rsplit("/", 1)[0] or f"{video.id} (new)"
                print(f"  DRY   {str(video.id)[:8]}  status={video.status:<10} "
                      f"dur={video.duration_seconds or '?':>5}s  prefix={prefix}")
            print("\nDRY RUN — nothing enqueued, no row modified.")
            return 0

        redis = await create_pool(redis_settings())
        try:
            for video in rows:
                prefix = (video.playlist_path or "").rsplit("/", 1)[0] or str(video.id)
                # playlist_path/key_path are deliberately left set — see the
                # module docstring. Only the status is reset.
                video.status = "pending"
                video.status_error = None
                await db.commit()
                await redis.enqueue_job("transcode_video", str(video.id))
                print(f"  QUEUED {str(video.id)[:8]}  prefix={prefix}")
        finally:
            await redis.close()

    print(f"\n{len(rows)} job(s) queued. With max_jobs=1 they drain one at a time.")
    print("Watch:  docker logs -f spacepoint-worker")
    print("Poll:   psql -d spacepoint_unified -c \"SELECT status, count(*) FROM videos "
          "WHERE owner_type='module_item' GROUP BY 1;\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--copy-direct", action="store_true",
                    help="copy direct-mode source bytes to the video backend")
    ap.add_argument("--reencode", action="store_true",
                    help="re-enqueue the HLS transcode for hls_encrypted videos")
    ap.add_argument("--video-id", help="restrict --reencode to one video id")
    ap.add_argument("--limit", type=int, help="process at most N videos (test with a small N first)")
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, change nothing")
    args = ap.parse_args()

    if args.copy_direct == args.reencode:
        ap.error("pass exactly one of --copy-direct or --reencode")

    return asyncio.run(copy_direct(args) if args.copy_direct else reencode(args))


if __name__ == "__main__":
    raise SystemExit(main())
