"""Move the video library onto R2, and re-encode it to the current targets —
incrementally, one video (or one course) at a time, with zero downtime.

Three independent jobs, deliberately in one script because they share every
filter and safety check:

  --status        Report where every video's bytes currently live (vps/r2),
                   grouped by owner_type and — for module_item videos — by
                   course. Read-only, changes nothing. Run this first and
                   after every batch: it is the "can I migrate only 3
                   courses today" visibility this script exists for.

  --copy-direct   Copy `direct`-mode videos' source bytes to R2, verify the
                  copy, then flip that row's `storage_backend` to "r2" in
                  one commit. These are the files a browser fetches straight
                  from `<video src>` (Instructor Library, facilitator
                  training). Served from local storage they go through
                  GET /files, which Fernet-decrypts the whole blob into
                  memory and answers with a single non-range response — and
                  a <video> element NEEDS byte ranges, both for the moov
                  atom at the end of a non-faststart MP4 and for every seek.
                  Against a non-range origin each of those restarts the
                  whole download, which is why a Library video "opens for a
                  second then goes back to loading". The local original is
                  left in place after a successful copy (only the row's
                  storage_backend pointer moves) — nothing to roll back to
                  by hand if a later step goes wrong.

  --reencode      Re-run the HLS transcode for `hls_encrypted` videos,
                  writing output to R2 at the CURRENT encode targets (1080p30,
                  capped CRF, 10s segments) — necessary because the old remux
                  gate checked codec only: sources that were already H.264
                  were copied through at full resolution and bitrate, and
                  everything else was crushed to 720p/800k. This job never
                  touches `video.status` or `video.storage_backend` itself —
                  see WHAT --reencode DELIBERATELY DOES NOT DO below.

Both mutating jobs accept `--course <course_id>` to scope to one course's
module_item videos — migrate 3 courses today, the rest next week, with
every other video (and every video mid-migration) continuing to serve from
wherever it already is. `--owner-type` scopes to one owner_type instead
(library_resource/training_video/program_item_guideline/module_item).
`--video-id` scopes to exactly one video. `--only-vps` (default on for the
mutating jobs) skips rows already on r2, so a re-run after a partial batch
only touches what's left.

USAGE (inside the api or worker container, where the env is loaded)

    python -m scripts.video_migrate_to_r2 --status
    python -m scripts.video_migrate_to_r2 --status --course <course_id>

    python -m scripts.video_migrate_to_r2 --copy-direct --dry-run
    python -m scripts.video_migrate_to_r2 --copy-direct

    python -m scripts.video_migrate_to_r2 --reencode --course <course_id> --dry-run
    python -m scripts.video_migrate_to_r2 --reencode --course <course_id> --limit 2  # test two first
    python -m scripts.video_migrate_to_r2 --reencode --course <course_id>

BEFORE --reencode, non-negotiable:

  1. `max_jobs = 1` must be deployed (app/workers/main.py). arq defaults to 10,
     and ten concurrent ffmpeg encodes on a 4-vCPU box takes the live platform
     down with it.
  2. Dump the columns this touches, so a bad batch stays a real rollback even
     if something goes wrong:

     psql -d spacepoint_unified -c "\\copy (SELECT id, owner_type, owner_id, \\
       playlist_path, key_path, duration_seconds, status, storage_backend \\
       FROM videos) TO '/root/videos_pre_reencode.csv' CSV HEADER"

  3. Do NOT run deploy-backend.sh while this is draining. `docker rm -f` is
     SIGKILL; it bypasses run_encrypted_transcode's CancelledError handler and
     leaves rows stuck at "processing" with nothing to retry them. (This only
     applies to a COLD row, `status != "ready"` at the time the job started —
     a HOT re-encode's failure or kill leaves the row completely untouched,
     see below.)

WHAT --reencode DELIBERATELY DOES NOT DO

  It does not set `video.status = "pending"` before enqueueing, and it does
  not clear `playlist_path`/`key_path`. Both are load-bearing:

  - Not touching `status` is what makes this zero-downtime for an
    already-`ready` video: `run_encrypted_transcode` (video_service.py) reads
    `hot = video.status == "ready"` and, when hot, leaves status/
    storage_backend completely alone for the whole encode — the OLD HLS
    output keeps serving every request, including new ones, for the entire
    duration of the re-encode. Only once the NEW output is verified fully
    written does one commit flip `playlist_path`/`key_path`/
    `duration_seconds`/`status`/`storage_backend` together, so no request can
    ever observe a half-migrated row. Setting `status = "pending"` here first
    — the old, broken shape of this script — would take the video offline
    for the entire re-encode instead, which is exactly the downtime this
    script now exists to avoid.
  - Not clearing `playlist_path`/`key_path` means `run_encrypted_transcode`
    reuses the row's existing prefix, so the re-encode overwrites in place
    on the NEW backend instead of relocating to a fresh `video.id`-shaped
    path — different backends are different physical stores, so writing the
    new output to the old prefix on R2 never collides with the still-live
    local tree at that same prefix.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections import Counter

from arq import create_pool
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.videos import Video
from app.services import storage
from app.services.video_service import enqueue_transcode
from app.workers.settings import redis_settings

_OWNER_TYPES = ("module_item", "library_resource", "program_item_guideline", "training_video")


def _label(video: Video) -> str:
    return f"{str(video.id)[:8]} {video.owner_type}/{str(video.owner_id)[:8]}"


def _backend_label(video: Video) -> str:
    return video.storage_backend or "vps"


def _fmt_mb(n: int) -> str:
    return f"{n / 1_000_000:.1f}MB"


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


def _apply_common_filters(stmt, args: argparse.Namespace):
    if args.video_id:
        stmt = stmt.where(Video.id == uuid.UUID(args.video_id))
    if args.owner_type:
        stmt = stmt.where(Video.owner_type == args.owner_type)
    if args.course:
        stmt = _scope_to_course(stmt, args.course)
    if not args.include_migrated:
        stmt = stmt.where(Video.storage_backend.is_(None))
    return stmt


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

        by_owner_type: dict[str, Counter] = {ot: Counter() for ot in _OWNER_TYPES}
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
            by_owner_type.setdefault(video.owner_type, Counter())[_backend_label(video)] += 1
            if video.owner_type == "module_item":
                course_id = item_to_course.get(video.owner_id)
                if course_id is not None:
                    by_course.setdefault(course_id, Counter())[_backend_label(video)] += 1

        print(f"{len(rows)} video(s) total\n")
        print("By owner_type:")
        for ot, counts in by_owner_type.items():
            if not counts:
                continue
            print(f"  {ot:<24} r2={counts['r2']:<4} vps={counts['vps']:<4}")

        if by_course:
            print("\nBy course (module_item only):")
            for course_id, counts in by_course.items():
                title = course_titles.get(course_id, "")
                print(f"  {str(course_id)[:8]}  r2={counts['r2']:<4} vps={counts['vps']:<4}  {title}")

        return 0


async def copy_direct(args: argparse.Namespace) -> int:
    if storage.video_backend() is None and not args.target:
        print("VIDEO_STORAGE_BACKEND is unset and --target was not given — nowhere to copy to.", file=sys.stderr)
        print("Set VIDEO_STORAGE_BACKEND=r2 in the container env, or pass --target r2.", file=sys.stderr)
        return 2
    target = args.target or storage.video_backend()

    failures = 0
    async with AsyncSessionLocal() as db:
        stmt = _apply_common_filters(
            select(Video).where(Video.provider == "upload", Video.upload_mode == "direct"), args,
        )
        rows = (await db.execute(stmt)).scalars().all()
        if args.limit:
            rows = rows[: args.limit]
        print(f"{len(rows)} direct-mode video(s) to copy -> backend={target}\n")

        for video in rows:
            label = _label(video)
            if not (video.source_bucket and video.source_path):
                print(f"  SKIP  {label}  (no source on file)")
                continue
            try:
                # Read from wherever this row's bytes currently live (local
                # disk for an unmigrated row), never from `target` — that is
                # where we are copying TO, not reading an already-written copy.
                data = await storage.download_file(video.source_bucket, video.source_path, backend=None)
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
            # truncated upload, or — worse — flipping storage_backend onto
            # a copy that never actually landed.
            check = await storage.download_file(video.source_bucket, video.source_path, backend=target)
            if len(check) != len(data):
                print(f"  FAIL  {label}  size mismatch: wrote {len(data)}, read back {len(check)} — NOT flipped")
                failures += 1
                continue

            # Only NOW, with the copy verified in place, does this row start
            # resolving to R2 — the local original is left untouched, so a
            # verification failure above leaves playback exactly as it was.
            video.storage_backend = target
            await db.commit()
            print(f"  OK    {label}  {_fmt_mb(len(data))} copied, verified, and switched to {target}")

    print(f"\n{'DRY RUN — nothing written' if args.dry_run else 'Done'}. {failures} failure(s).")
    print("Local originals were NOT deleted — a row can be pointed back at vps by hand if needed.")
    return 1 if failures else 0


def _guess_video_type(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "mp4": "video/mp4", "m4v": "video/mp4", "mov": "video/quicktime",
        "webm": "video/webm", "mkv": "video/x-matroska", "ogv": "video/ogg",
        "ogg": "video/ogg", "avi": "video/x-msvideo",
    }.get(ext, "video/mp4")


async def reencode(args: argparse.Namespace) -> int:
    target = args.target or storage.video_backend() or "r2"

    async with AsyncSessionLocal() as db:
        stmt = _apply_common_filters(
            select(Video).where(Video.provider == "upload", Video.upload_mode == "hls_encrypted")
            .order_by(Video.created_at),
            args,
        )
        rows = (await db.execute(stmt)).scalars().all()
        if args.limit:
            rows = rows[: args.limit]

        print(f"{len(rows)} video(s) to re-encode -> HLS output on {target}\n")
        if not rows:
            return 0

        if args.dry_run:
            for video in rows:
                prefix = (video.playlist_path or "").rsplit("/", 1)[0] or f"{video.id} (new)"
                hot = "hot (zero-downtime swap)" if video.status == "ready" else "cold"
                print(f"  DRY   {_label(video)}  current={_backend_label(video):<4} {hot:<26} "
                      f"dur={video.duration_seconds or '?':>5}s  prefix={prefix}")
            print("\nDRY RUN — nothing enqueued, no row modified.")
            return 0

        redis = await create_pool(redis_settings())
        try:
            for video in rows:
                prefix = (video.playlist_path or "").rsplit("/", 1)[0] or str(video.id)
                # Deliberately does NOT touch video.status or
                # video.storage_backend here — see the module docstring's
                # "WHAT --reencode DELIBERATELY DOES NOT DO". The swap is
                # entirely run_encrypted_transcode's job, driven by the
                # target_backend passed through enqueue_transcode below.
                dispatch = await enqueue_transcode(redis, video.id, target_backend=target)
                print(f"  QUEUED {_label(video)}  prefix={prefix}  dispatch={dispatch}")
        finally:
            await redis.close()

    print(f"\n{len(rows)} job(s) queued. With max_jobs=1 they drain one at a time.")
    print("Watch:  docker logs -f spacepoint-worker")
    print("Poll:   psql -d spacepoint_unified -c \"SELECT storage_backend, count(*) FROM videos GROUP BY 1;\"")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="report each video's current backend, change nothing")
    ap.add_argument("--copy-direct", action="store_true",
                    help="copy direct-mode source bytes to R2, then flip storage_backend once verified")
    ap.add_argument("--reencode", action="store_true",
                    help="re-enqueue the HLS transcode for hls_encrypted videos, targeting R2")
    ap.add_argument("--course", help="restrict to one course's module_item videos (uuid)")
    ap.add_argument("--owner-type", choices=_OWNER_TYPES, help="restrict to one owner_type")
    ap.add_argument("--video-id", help="restrict to one video id")
    ap.add_argument("--target", default=None, help="backend to migrate onto (default: r2)")
    ap.add_argument("--include-migrated", action="store_true",
                    help="also touch rows already on the target backend (default: only vps rows)")
    ap.add_argument("--limit", type=int, help="process at most N videos (test with a small N first)")
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, change nothing")
    args = ap.parse_args()

    modes = [args.status, args.copy_direct, args.reencode]
    if sum(bool(m) for m in modes) != 1:
        ap.error("pass exactly one of --status, --copy-direct, or --reencode")

    if args.status:
        return asyncio.run(status(args))
    return asyncio.run(copy_direct(args) if args.copy_direct else reencode(args))


if __name__ == "__main__":
    raise SystemExit(main())
