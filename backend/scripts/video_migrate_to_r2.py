"""Move videos between storage backends, and re-encode them to current
targets — incrementally, one video (or one course) at a time, with zero
downtime.

Three jobs, deliberately in one script because they share every filter and
safety check.

  --status  Report where every video's bytes currently live (r2/vps), grouped
            by owner_type and — for module_item videos — by course.
            Read-only, changes nothing. Run this first and after every batch:
            it is the "can I migrate only 3 courses today" visibility this
            script exists for.

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

  --convert   One-time mode change for an EXISTING `direct`-mode video (a raw
            file served as-is — Instructor Library, facilitator training,
            checklist guidelines) into `hls_encrypted`: compressed and
            streamed through the same pipeline every LMS course module video
            already uses, then enqueued for transcode same as --reencode.

            Every upload endpoint for these features now requests
            hls_encrypted directly — this is the catch-up pass for whatever
            was uploaded before that switch, back when "direct" was the only
            option. `--move --to r2 --mode direct` made those files
            seekable; it never made them smaller, and Library files run 4K
            routinely. This is the actual compression step.

            Safe to run repeatedly: it filters to upload_mode="direct" and
            each row flips out of that mode the moment it converts, so a
            re-run only ever touches what --convert has not already reached
            (including anything --status still shows on "vps").

  --reencode  Re-run the HLS transcode at the CURRENT encode targets (1080p30,
            capped CRF, 10s segments), writing the output to R2. THIS is how
            the existing library gets onto R2 — not --move.

            Copying the current HLS output to R2 would be copying junk: the old
            remux gate checked codec only, so sources that were already H.264
            got copied through at full 4K and full bitrate, and everything else
            was crushed to 720p/800k. That output is being replaced. Re-encode
            from the source (already on the VPS) and write the result straight
            to R2 — one pass, no pointless copy of bytes nobody wants.

            Each video keeps serving its existing output for the whole encode
            and swaps atomically when the new one is verified. If an encode
            fails, that row never swaps and students never notice. Only "r2"
            is a valid --reencode target — see NO "--reencode --to vps" below.

`--move` and `--reencode` both accept `--course <course_id>` to scope to one
course's module_item videos — migrate 3 courses today, the rest next week,
with every other video (and every video mid-migration) continuing to serve
from wherever it already is. `--owner-type`/`--mode`/`--video-id` narrow
further; every mutating command also skips rows already on the target
backend, so a re-run after a partial batch only touches what is left.

USAGE (inside the api or worker container, where the env is loaded)

    python -m scripts.video_migrate_to_r2 --status
    python -m scripts.video_migrate_to_r2 --status --course <course_id>

    python -m scripts.video_migrate_to_r2 --move --to r2 --dry-run
    python -m scripts.video_migrate_to_r2 --move --to r2 --limit 1     # one first
    python -m scripts.video_migrate_to_r2 --move --to r2
    python -m scripts.video_migrate_to_r2 --move --to vps --video-id <id>   # roll one back

    python -m scripts.video_migrate_to_r2 --convert --dry-run
    python -m scripts.video_migrate_to_r2 --convert --limit 1
    python -m scripts.video_migrate_to_r2 --convert --owner-type library_resource

    python -m scripts.video_migrate_to_r2 --reencode --course <course_id> --dry-run
    python -m scripts.video_migrate_to_r2 --reencode --course <course_id> --limit 1
    python -m scripts.video_migrate_to_r2 --reencode --course <course_id>

BEFORE --reencode, non-negotiable:

  1. `max_jobs = 1` must be deployed (app/workers/main.py). arq defaults to 10,
     and ten concurrent ffmpeg encodes on a 4-vCPU box take the live platform
     down with them.
  2. Dump the columns this touches, so you can restore statuses if a batch goes
     wrong mid-run:

     psql -d spacepoint_unified -c "\\copy (SELECT id, owner_type, owner_id, \\
       playlist_path, key_path, duration_seconds, status, storage_backend \\
       FROM videos) TO '/root/videos_pre_reencode.csv' CSV HEADER"

  3. Do NOT run deploy-backend.sh while this is draining. `docker rm -f` is
     SIGKILL; it bypasses run_encrypted_transcode's CancelledError handler and
     leaves rows stuck at "processing" with nothing to retry them.

  4. A video that is already "ready" and is being re-encoded ONTO A DIFFERENT
     backend keeps its "ready" status throughout and never becomes unplayable,
     whether the encode succeeds or fails. Re-encoding onto the SAME backend
     has no such protection — the new output overwrites the old in place, so
     the row does go "processing" and, on failure, "failed". This is why
     --reencode only ever targets r2 from a VPS-hosted video.

NO "--reencode --to vps"

  `run_encrypted_transcode`'s `target_backend=None` means "no override — write
  to wherever this row's storage_backend already says", not "target the VPS
  explicitly" (see that function's own note on why: the value crosses an ARQ
  job boundary, so a value meaning "explicit vps" would be indistinguishable
  from "no override" on the other side once serialized). So there is no way to
  ask this script to re-encode a video explicitly back onto the VPS, and no
  need to: rolling a video back is `--move --to vps` — free, immediate, no
  re-encode, no ffmpeg — not a second transcode.

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
from collections import Counter

from arq import create_pool
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.videos import Video
from app.services.video_service import convert_to_hls_encrypted, move_to_backend
from app.workers.settings import redis_settings


def _label(video: Video) -> str:
    return (f"{str(video.id)[:8]} {video.owner_type:<24} "
            f"{(video.upload_mode or '-'):<14} on={video.storage_backend or 'vps'}")


def _scope_to_course(stmt, course_id: str):
    """module_item videos only — Video.owner_id -> ModuleItem.id ->
    CourseModule.id -> Course.id. Any other owner_type has no course concept,
    so a --course filter combined with e.g. --owner-type library_resource
    would just return nothing, which is the correct (if unhelpful) answer."""
    return (
        stmt.join(ModuleItem, ModuleItem.id == Video.owner_id)
        .join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .where(Video.owner_type == "module_item", CourseModule.course_id == uuid.UUID(course_id))
    )


async def status(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(Video)
        if args.video_id:
            stmt = stmt.where(Video.id == uuid.UUID(args.video_id))
        if args.owner_type:
            stmt = stmt.where(Video.owner_type == args.owner_type)
        if args.course:
            stmt = _scope_to_course(stmt, args.course)
        rows = (await db.execute(stmt)).scalars().all()

        by_owner_type: dict[str, Counter] = {}
        by_course: dict[uuid.UUID, Counter] = {}
        course_titles: dict[uuid.UUID, str] = {}

        if any(v.owner_type == "module_item" for v in rows):
            item_ids = [v.owner_id for v in rows if v.owner_type == "module_item"]
            course_rows = (await db.execute(
                select(ModuleItem.id, Course.id, Course.title)
                .join(CourseModule, CourseModule.id == ModuleItem.module_id)
                .join(Course, Course.id == CourseModule.course_id)
                .where(ModuleItem.id.in_(item_ids))
            )).all()
            item_to_course = {item_id: course_id for item_id, course_id, _ in course_rows}
            course_titles = {course_id: title for _, course_id, title in course_rows}
        else:
            item_to_course = {}

        for video in rows:
            by_owner_type.setdefault(video.owner_type, Counter())[video.storage_backend or "vps"] += 1
            if video.owner_type == "module_item":
                course_id = item_to_course.get(video.owner_id)
                if course_id is not None:
                    by_course.setdefault(course_id, Counter())[video.storage_backend or "vps"] += 1

        print(f"{len(rows)} video(s) total\n")
        print("By owner_type:")
        for ot, counts in by_owner_type.items():
            print(f"  {ot:<24} r2={counts['r2']:<4} vps={counts['vps']:<4}")

        if by_course:
            print("\nBy course (module_item only):")
            for course_id, counts in by_course.items():
                title = course_titles.get(course_id, "")
                print(f"  {str(course_id)[:8]}  r2={counts['r2']:<4} vps={counts['vps']:<4}  {title}")

        return 0


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
        if args.course:
            stmt = _scope_to_course(stmt, args.course)
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


async def convert(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(Video).where(
            Video.provider == "upload", Video.upload_mode == "direct"
        ).order_by(Video.created_at)
        if args.owner_type:
            stmt = stmt.where(Video.owner_type == args.owner_type)
        if args.video_id:
            stmt = stmt.where(Video.id == uuid.UUID(args.video_id))
        if args.course:
            stmt = _scope_to_course(stmt, args.course)
        rows = (await db.execute(stmt)).scalars().all()
        if args.limit:
            rows = rows[: args.limit]

        print(f"{len(rows)} direct-mode video(s) to convert -> hls_encrypted, output on r2\n")
        if not rows:
            return 0

        if args.dry_run:
            for video in rows:
                print(f"  DRY   {_label(video)}  source={video.source_bucket}/{video.source_path}")
            print("\nDRY RUN — nothing converted, no row modified.")
            return 0

        failures = 0
        redis = await create_pool(redis_settings())
        try:
            for video in rows:
                result = await convert_to_hls_encrypted(db, video)
                if "error" in result:
                    print(f"  FAIL  {_label(video)}  {result['error']}")
                    failures += 1
                    continue
                await redis.enqueue_job("transcode_video", str(video.id), "r2")
                print(f"  QUEUED {_label(video)}  (was direct, now transcoding to hls_encrypted)")
        finally:
            await redis.close()

    print(f"\n{len(rows) - failures} job(s) queued, {failures} failed.")
    print("A converted video was NOT servable as direct before this queued — it stays")
    print("unplayable until its own encode finishes (there is no prior HLS output to")
    print("keep serving, unlike --reencode). Watch:  docker logs -f spacepoint-worker")
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
        if args.course:
            stmt = _scope_to_course(stmt, args.course)
        rows = (await db.execute(stmt)).scalars().all()
        if args.limit:
            rows = rows[: args.limit]

        target = "r2"  # the only valid --reencode target — see the module docstring
        print(f"{len(rows)} video(s) to re-encode -> output on {target}\n")
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
    print("Poll:   psql -d spacepoint_unified -c \"SELECT storage_backend, count(*) FROM videos GROUP BY 1;\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="report each video's current backend, change nothing")
    ap.add_argument("--move", action="store_true",
                    help="copy videos' bytes to --to and repoint their rows")
    ap.add_argument("--to", choices=["r2", "vps"], default="r2",
                    help="--move's target backend (default: r2) — --reencode always targets r2, see NO "
                         "\"--reencode --to vps\" in the module docstring")
    ap.add_argument("--convert", action="store_true",
                    help="convert existing direct-mode videos to hls_encrypted and enqueue transcode")
    ap.add_argument("--reencode", action="store_true",
                    help="re-enqueue the HLS transcode for hls_encrypted videos, targeting r2")
    ap.add_argument("--course", help="restrict to one course's module_item videos (uuid)")
    ap.add_argument("--mode", choices=["hls_encrypted", "direct"],
                    help="restrict --move to one upload mode")
    ap.add_argument("--owner-type", help="restrict to one owner type, e.g. module_item")
    ap.add_argument("--video-id", help="restrict to a single video id")
    ap.add_argument("--limit", type=int,
                    help="process at most N videos — always test with a small N first")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen, change nothing")
    args = ap.parse_args()

    modes = [args.status, args.move, args.convert, args.reencode]
    if sum(bool(m) for m in modes) != 1:
        ap.error("pass exactly one of --status, --move, --convert, or --reencode")

    if args.status:
        return asyncio.run(status(args))
    if args.move:
        return asyncio.run(move(args))
    if args.convert:
        return asyncio.run(convert(args))
    return asyncio.run(reencode(args))


if __name__ == "__main__":
    raise SystemExit(main())
