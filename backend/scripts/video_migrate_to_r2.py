"""Move videos between storage backends, and re-encode them to current targets.

Two jobs, deliberately in one script because they are the two halves of the
same cutover and share every filter and safety check.

  --move    Copy a video's student-facing bytes to another backend and repoint
            its row's `storage_backend`, without re-encoding.

            NOT the path for the existing LMS library — see --reencode. Copying
            the current HLS output to R2 would just relocate output that is
            about to be thrown away. Use --move when the bytes are worth keeping
            as they are:

            · `direct` videos (Instructor Library, facilitator training). There
              is no transcode in that mode, so the file IS the asset and there
              is nothing to regenerate.
            · Rolling a single video back: `--to vps --video-id <id>`.

            Copies, never moves — the origin bytes stay put, so flipping a row
            back is instant and complete.

            For `direct` the source is what moves, because there the source IS
            what the browser fetches. That is also the fix for a Library video that
            "opens for a second then goes back to loading": served from local
            storage it goes through GET /files, which Fernet-decrypts the whole
            blob into memory and answers with one non-range response. A <video>
            element needs byte ranges — for the moov atom at the end of any
            non-faststart MP4, and for every seek — and against a non-range
            origin each of those restarts the entire download. Fernet is
            all-or-nothing, so ranges are not merely unimplemented there, they
            are unimplementable. An object store answers them natively.

  --reencode  Re-run the HLS transcode at the CURRENT encode targets (1080p30,
            capped CRF, 10s segments), writing the output to `--to`. THIS is
            how the existing library gets onto R2 — not --move.

            Copying the current HLS output to R2 would be copying junk: the old
            remux gate checked codec only, so sources that were already H.264
            got copied through at full 4K and full bitrate, and everything else
            was crushed to 720p/800k. That output is being replaced. Re-encode
            from the source (already on the VPS) and write the result straight
            to R2 — one pass, no pointless copy of bytes nobody wants.

            Each video keeps serving its existing output for the whole encode
            and swaps atomically when the new one is verified. If an encode
            fails, that row never swaps and students never notice.

USAGE (inside the api or worker container, where the env is loaded)

    python -m scripts.video_migrate_to_r2 --move --to r2 --dry-run
    python -m scripts.video_migrate_to_r2 --move --to r2 --limit 1     # one first
    python -m scripts.video_migrate_to_r2 --move --to r2
    python -m scripts.video_migrate_to_r2 --move --to vps --video-id <id>   # roll one back

    python -m scripts.video_migrate_to_r2 --reencode --to r2 --dry-run
    python -m scripts.video_migrate_to_r2 --reencode --to r2 --limit 1   # one first
    python -m scripts.video_migrate_to_r2 --reencode --to r2

BEFORE --reencode, non-negotiable:

  1. `max_jobs = 1` must be deployed (app/workers/main.py). arq defaults to 10,
     and ten concurrent ffmpeg encodes on a 4-vCPU box take the live platform
     down with them.
  2. Dump the columns this touches, so you can restore statuses if a batch goes
     wrong mid-run:

     psql -d spacepoint_unified -c "\\copy (SELECT id, owner_id, playlist_path, \\
       key_path, duration_seconds, status, storage_backend FROM videos \\
       WHERE owner_type='module_item') TO '/root/videos_pre_reencode.csv' CSV HEADER"

  3. Do NOT run deploy-backend.sh while this is draining. `docker rm -f` is
     SIGKILL; it bypasses run_encrypted_transcode's CancelledError handler and
     leaves rows stuck at "processing" with nothing to retry them.

  4. A video that is already "ready" and is being re-encoded ONTO A DIFFERENT
     backend keeps its "ready" status throughout and never becomes unplayable,
     whether the encode succeeds or fails. Re-encoding onto the SAME backend
     has no such protection — the new output overwrites the old in place, so
     the row does go "processing" and, on failure, "failed". Prefer
     `--to r2` from a VPS-hosted video for exactly this reason.

WHAT --reencode DELIBERATELY DOES NOT DO

  It does not clear `playlist_path`/`key_path`. run_encrypted_transcode reuses
  the row's existing prefix, so a re-encode overwrites in place rather than
  relocating to a `video.id`-shaped path. Rows backfilled by the
  unify_video_service migration carry an owner_id-shaped prefix, and moving
  them would strand the VPS copy at a path no row points at — which is exactly
  what the per-video rollback depends on still being there.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from arq import create_pool
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.videos import Video
from app.services.video_service import move_to_backend
from app.workers.settings import redis_settings


def _label(video: Video) -> str:
    return (f"{str(video.id)[:8]} {video.owner_type:<24} "
            f"{(video.upload_mode or '-'):<14} on={video.storage_backend or 'vps'}")


async def move(args: argparse.Namespace) -> int:
    target = None if args.to == "vps" else args.to
    failures = skipped = moved = 0

    async with AsyncSessionLocal() as db:
        stmt = select(Video).where(Video.provider == "upload").order_by(Video.created_at)
        if args.mode:
            stmt = stmt.where(Video.upload_mode == args.mode)
        if args.owner_type:
            stmt = stmt.where(Video.owner_type == args.owner_type)
        if args.video_id:
            stmt = stmt.where(Video.id == uuid.UUID(args.video_id))
        rows = (await db.execute(stmt)).scalars().all()
        # Skip anything already there, so re-running after a partial failure
        # retries only what actually needs retrying.
        rows = [v for v in rows if (v.storage_backend or None) != target]
        if args.limit:
            rows = rows[: args.limit]

        print(f"{len(rows)} video(s) to move -> {args.to}\n")
        for video in rows:
            result = await move_to_backend(db, video, target, dry_run=args.dry_run)
            if "error" in result:
                print(f"  FAIL  {_label(video)}  {result['error']}")
                failures += 1
            elif args.dry_run:
                print(f"  DRY   {_label(video)}  would copy "
                      f"{result.get('would_move', 0)} object(s) -> {result.get('to')}")
            elif result.get("skipped"):
                print(f"  SKIP  {_label(video)}  {result['skipped']}")
                skipped += 1
            else:
                print(f"  OK    {_label(video)}  {result['moved']} object(s) "
                      f"{result['from']} -> {result['to']}")
                moved += 1

    tail = "DRY RUN — nothing written" if args.dry_run else f"{moved} moved"
    print(f"\n{tail}, {skipped} skipped, {failures} failed.")
    if moved:
        print("Origin bytes were NOT deleted. To roll one video back:")
        print("  python -m scripts.video_migrate_to_r2 --move --to vps --video-id <id>")
    return 1 if failures else 0


async def reencode(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(Video).where(
            Video.provider == "upload", Video.upload_mode == "hls_encrypted"
        ).order_by(Video.created_at)
        if args.owner_type:
            stmt = stmt.where(Video.owner_type == args.owner_type)
        if args.video_id:
            stmt = stmt.where(Video.id == uuid.UUID(args.video_id))
        rows = (await db.execute(stmt)).scalars().all()
        if args.limit:
            rows = rows[: args.limit]

        target = None if args.to == "vps" else args.to
        print(f"{len(rows)} video(s) to re-encode -> output on {args.to}\n")
        if not rows:
            return 0

        if args.dry_run:
            for video in rows:
                prefix = (video.playlist_path or "").rsplit("/", 1)[0] or f"{video.id} (new)"
                print(f"  DRY   {_label(video)}  status={video.status:<10} "
                      f"dur={video.duration_seconds or '?':>5}s  prefix={prefix}")
            print("\nDRY RUN — nothing enqueued, no row modified.")
            return 0

        redis = await create_pool(redis_settings())
        try:
            for video in rows:
                # playlist_path/key_path deliberately left set — see the module
                # docstring.
                #
                # Status is only reset for a video that is NOT currently
                # servable, or that is being re-encoded onto the backend it
                # already sits on. A ready video moving to a different backend
                # must stay "ready": the token endpoint 409s on anything else,
                # so setting "pending" here would take it away from students
                # for the whole encode — the exact thing run_encrypted_transcode
                # goes out of its way to avoid.
                keeps_serving = (
                    bool(video.playlist_path)
                    and video.status == "ready"
                    and target != (video.storage_backend or None)
                )
                if not keeps_serving:
                    video.status = "pending"
                    video.status_error = None
                    await db.commit()
                await redis.enqueue_job("transcode_video", str(video.id), target)
                print(f"  QUEUED {_label(video)}"
                      f"{'  (keeps serving during encode)' if keeps_serving else ''}")
        finally:
            await redis.close()

    print(f"\n{len(rows)} job(s) queued. With max_jobs=1 they drain one at a time.")
    print("Watch:  docker logs -f spacepoint-worker")
    print("Poll:   psql -d spacepoint_unified -c \"SELECT status, count(*) FROM videos "
          "WHERE owner_type='module_item' GROUP BY 1;\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--move", action="store_true",
                    help="copy videos' bytes to --to and repoint their rows")
    ap.add_argument("--to", choices=["r2", "vps"], default="r2",
                    help="target backend: where --move copies to, or where "
                         "--reencode writes its output (default: r2)")
    ap.add_argument("--reencode", action="store_true",
                    help="re-enqueue the HLS transcode for hls_encrypted videos")
    ap.add_argument("--mode", choices=["hls_encrypted", "direct"],
                    help="restrict to one upload mode")
    ap.add_argument("--owner-type", help="restrict to one owner type, e.g. module_item")
    ap.add_argument("--video-id", help="restrict to a single video id")
    ap.add_argument("--limit", type=int,
                    help="process at most N videos — always test with a small N first")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen, change nothing")
    args = ap.parse_args()

    if args.move == args.reencode:
        ap.error("pass exactly one of --move or --reencode")

    return asyncio.run(move(args) if args.move else reencode(args))


if __name__ == "__main__":
    raise SystemExit(main())
