"""One-time fix: a video was uploaded to the Instructor Library but actually
belongs in facilitator Training. Repoints it in place — the video's bytes
never move (R2 or VPS, HLS output or source), only the ownership metadata
does, so this is instant and does not touch storage or re-encode anything.

What it does, for one `--library-resource-id`:
  1. Create a new TrainingVideo row in `--training-module-id` (title/
     description carried over, no video_path — it becomes an upload, not an
     embed link).
  2. Repoint the existing `videos` row's (owner_type, owner_id) from
     ("library_resource", <library_resource.id>) to
     ("training_video", <new TrainingVideo.id>). Same row, same
     playlist_path/source_path/storage_backend — nothing about the actual
     video changes, only who owns it.
  3. Delete the LibraryResource row (it only ever existed to point at that
     video; nothing else references it).

Requires the library resource to be video-service-backed already (file_url
startswith "video-service:") — a legacy, never-linked row has no Video row
to repoint. Run --link-legacy-library first (video_migrate_to_r2.py) if
`--status` below reports "not video-service-backed".

Usage (inside the api or worker container):

    python -m scripts.move_library_video_to_training --status --library-resource-id <id>

    python -m scripts.move_library_video_to_training \\
        --library-resource-id <id> --training-module-id <id> --dry-run

    python -m scripts.move_library_video_to_training \\
        --library-resource-id <id> --training-module-id <id>
"""
from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.instructors.library import LibraryResource
from app.models.instructors.training import TrainingModule, TrainingVideo
from app.services.video_service import get_video_for_owner

_VIDEO_SENTINEL_PREFIX = "video-service:"  # mirrors routers/instructors/facilitator.py


async def status(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        resource = await db.get(LibraryResource, uuid.UUID(args.library_resource_id))
        if resource is None:
            print(f"No library resource with id {args.library_resource_id}")
            return 1
        print(f"title={resource.title!r} format={resource.format} resource_type={resource.resource_type}")
        if not resource.file_url.startswith(_VIDEO_SENTINEL_PREFIX):
            print("NOT video-service-backed — file_url is a raw storage path, not a video-service pointer.")
            print("Run --link-legacy-library (video_migrate_to_r2.py) first.")
            return 1
        video = await get_video_for_owner(db, owner_type="library_resource", owner_id=resource.id)
        if video is None:
            print("file_url points at a video-service row that doesn't exist. Nothing to move.")
            return 1
        print(f"video_id={video.id} upload_mode={video.upload_mode} status={video.status} "
              f"storage_backend={video.storage_backend or 'vps'}")
        print("Ready to move.")
        return 0


async def move(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        resource = await db.get(LibraryResource, uuid.UUID(args.library_resource_id))
        if resource is None:
            print(f"FAIL  no library resource with id {args.library_resource_id}")
            return 1
        if not resource.file_url.startswith(_VIDEO_SENTINEL_PREFIX):
            print(f"FAIL  {resource.title!r} is not video-service-backed — run --link-legacy-library first")
            return 1
        video = await get_video_for_owner(db, owner_type="library_resource", owner_id=resource.id)
        if video is None:
            print(f"FAIL  {resource.title!r} has no matching videos row — nothing to move")
            return 1

        module = await db.get(TrainingModule, uuid.UUID(args.training_module_id))
        if module is None:
            print(f"FAIL  no training module with id {args.training_module_id}")
            return 1

        next_sort_order = (await db.scalar(
            select(func.coalesce(func.max(TrainingVideo.sort_order), 0)).where(TrainingVideo.module_id == module.id)
        )) + 1

        print(f"Move {resource.title!r} (video_id={video.id}) -> training module {module.title!r}")
        if args.dry_run:
            print("DRY RUN — nothing written.")
            return 0

        training_video = TrainingVideo(
            module_id=module.id, title=resource.title, description=resource.description,
            video_path=None, sort_order=next_sort_order,
        )
        db.add(training_video)
        await db.flush()  # need training_video.id before repointing the videos row

        video.owner_type = "training_video"
        video.owner_id = training_video.id

        await db.delete(resource)
        await db.commit()
        print(f"OK  training_video={training_video.id}  video row repointed, bytes untouched, library entry removed.")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="report whether this resource is ready to move, change nothing")
    ap.add_argument("--library-resource-id", required=True, help="the Library resource's id (uuid)")
    ap.add_argument("--training-module-id", help="destination training module's id (uuid) — required unless --status")
    ap.add_argument("--dry-run", action="store_true", help="report what would happen, change nothing")
    args = ap.parse_args()

    if args.status:
        return asyncio.run(status(args))
    if not args.training_module_id:
        ap.error("--training-module-id is required unless --status")
    return asyncio.run(move(args))


if __name__ == "__main__":
    raise SystemExit(main())
