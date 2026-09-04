"""Standardize video handling into one shared `videos` table (2026-09).

Video handling was duplicated four ways before this: `module_videos` (LMS
course modules, the only feature with a working ffmpeg->AES-HLS pipeline),
`lms_program_items.guideline_kind='video'`/`guideline_url` (checklist
guideline videos, link-only), `library_resources` (instructor library,
video-ness sniffed by file extension, plain upload, no transcode), and
`training_videos.video_path` (facilitator training, link-only despite a
stale doc-comment claiming otherwise). None of the four were usable by any
other feature. `videos` (see `app/models/videos.py`) replaces all four with
one polymorphic table (`owner_type`/`owner_id`, the same service-layer-
enforced discriminator idiom `lms_program_items.owner_type` already uses)
supporting three playback shapes: `provider="youtube"|"vimeo"` (embed link),
`provider="upload", upload_mode="direct"` (plain progressive stream, no
transcode), and `provider="upload", upload_mode="hls_encrypted"` (the
existing AES-HLS pipeline, generalized in `services/video_service.py`).

This revision creates the table and backfills one `videos` row per existing
video-bearing row in all four source tables, then drops `module_videos`
outright (video-only, no other consumer — `video_checkpoints.item_id` points
at `module_items.id` directly, confirmed unaffected). The other three
source tables are NOT altered here: `lms_program_items.guideline_kind`/
`guideline_url` stay in place (still load-bearing for `pdf`/`link` kinds);
`library_resources.format`/`file_url` and `training_videos.video_path` stay
in place for their video rows too (both tables still exist for non-video
reasons — title/description/grouping) but become dead weight for those rows
going forward, superseded by their new `videos` counterpart. Application
code stops writing to them for video rows as of this same change (see the
video-service migration commits for each of the four features).

**This backfill must be dry-run against a real copy of the data before
being applied to any environment with real rows** — it cannot be exercised
in a sandbox with no reachable Postgres, and reads real content (video
paths/URLs) whose exact shape (e.g. `library_resources.file_url` sometimes
holding a bare path and sometimes a legacy full signed URL, per
`_lib_storage_path()` in `routers/instructors/facilitator.py`) is inferred
from code reading, not from having queried the actual production data.

Revision ID: f2c8a916e731
Revises: d4a72fe19b03
Create Date: 2026-09-04 00:00:00.000000

"""
import re
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2c8a916e731'
down_revision: Union[str, None] = 'd4a72fe19b03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same extension set routers/instructors/library.py::_VIDEO_FORMATS and
# frontend/src/lib/utils.ts::isVideoFormat already check — kept as a local,
# frozen copy here rather than importing app code into a migration (a
# migration must keep working even after the app code it once mirrored
# changes or is deleted).
_VIDEO_FORMATS = {"MP4", "MOV", "WEBM", "M4V", "AVI", "MKV", "OGG", "OGV"}

# Same host-matching regex as frontend/src/lib/embed.ts::isKnownEmbedHost.
_EMBED_HOST_RE = re.compile(r"youtu\.be|youtube\.com|vimeo\.com", re.IGNORECASE)


def _detect_provider(url: str) -> str | None:
    if not url or not _EMBED_HOST_RE.search(url):
        return None
    return "vimeo" if "vimeo.com" in url.lower() else "youtube"


def _lib_storage_path(file_url: str) -> str:
    """Mirrors routers/instructors/facilitator.py::_lib_storage_path —
    file_url holds either a bare storage path or a legacy full signed URL."""
    if file_url.startswith("http"):
        return file_url.split("library-resources/")[-1].split("?")[0]
    return file_url


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(32), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("upload_mode", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ready"),
        sa.Column("status_error", sa.Text(), nullable=True),
        sa.Column("embed_url", sa.String(512), nullable=True),
        sa.Column("source_bucket", sa.String(64), nullable=True),
        sa.Column("source_path", sa.String(512), nullable=True),
        sa.Column("playlist_path", sa.String(512), nullable=True),
        sa.Column("key_path", sa.String(512), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("owner_type", "owner_id", name="uq_videos_owner"),
    )
    op.create_index("ix_videos_created_by", "videos", ["created_by"])

    bind = op.get_bind()
    now = sa.func.now()

    # ── module_videos -> videos (owner_type='module_item') ──────────────
    for row in bind.execute(sa.text(
        "SELECT id, item_id, source_bucket, source_path, playlist_path, key_path, "
        "duration_seconds, transcode_status, transcode_error FROM module_videos"
    )).mappings():
        bind.execute(sa.text(
            "INSERT INTO videos (id, owner_type, owner_id, provider, upload_mode, status, "
            "status_error, source_bucket, source_path, playlist_path, key_path, "
            "duration_seconds, created_at, updated_at) "
            "VALUES (:id, 'module_item', :owner_id, 'upload', 'hls_encrypted', :status, "
            ":status_error, :source_bucket, :source_path, :playlist_path, :key_path, "
            ":duration_seconds, :now, :now)"
        ), {
            "id": uuid.uuid4(), "owner_id": row["item_id"], "status": row["transcode_status"],
            "status_error": row["transcode_error"], "source_bucket": row["source_bucket"],
            "source_path": row["source_path"], "playlist_path": row["playlist_path"],
            "key_path": row["key_path"], "duration_seconds": row["duration_seconds"], "now": now,
        })

    # ── lms_program_items (guideline_kind='video') -> videos ────────────
    # (owner_type='program_item_guideline') — only for a recognized
    # YouTube/Vimeo host; these have only ever been pasted links (no upload
    # path existed), and toEmbedUrl() itself falls back to a plain outbound
    # link for anything else, so an unrecognized host here is expected to be
    # rare-to-nonexistent. Left un-migrated (guideline_url stays authoritative
    # via the router's fallback) rather than guessing a provider.
    for row in bind.execute(sa.text(
        "SELECT id, guideline_url FROM lms_program_items "
        "WHERE guideline_kind = 'video' AND guideline_url IS NOT NULL"
    )).mappings():
        provider = _detect_provider(row["guideline_url"])
        if provider is None:
            continue
        bind.execute(sa.text(
            "INSERT INTO videos (id, owner_type, owner_id, provider, status, embed_url, "
            "created_at, updated_at) "
            "VALUES (:id, 'program_item_guideline', :owner_id, :provider, 'ready', :embed_url, :now, :now)"
        ), {"id": uuid.uuid4(), "owner_id": row["id"], "provider": provider,
            "embed_url": row["guideline_url"], "now": now})

    # ── library_resources (video-format files) -> videos ────────────────
    # (owner_type='library_resource', upload_mode='direct' — no transcode
    # today, matches the feature's existing plain-signed-URL playback).
    fmt_list = ", ".join(f"'{f}'" for f in sorted(_VIDEO_FORMATS))
    for row in bind.execute(sa.text(
        f"SELECT id, file_url, uploader_id FROM library_resources "
        f"WHERE resource_type = 'file' AND format IN ({fmt_list})"
    )).mappings():
        bind.execute(sa.text(
            "INSERT INTO videos (id, owner_type, owner_id, provider, upload_mode, status, "
            "source_bucket, source_path, created_by, created_at, updated_at) "
            "VALUES (:id, 'library_resource', :owner_id, 'upload', 'direct', 'ready', "
            "'library-resources', :source_path, :created_by, :now, :now)"
        ), {"id": uuid.uuid4(), "owner_id": row["id"],
            "source_path": _lib_storage_path(row["file_url"]),
            "created_by": row["uploader_id"], "now": now})

    # ── training_videos -> videos (owner_type='training_video') ─────────
    # Always a pasted YouTube/Vimeo link in practice today (no upload path
    # ever existed for this feature) — same un-migrate-if-unrecognized
    # posture as the guideline-video backfill above.
    for row in bind.execute(sa.text("SELECT id, video_path FROM training_videos")).mappings():
        provider = _detect_provider(row["video_path"])
        if provider is None:
            continue
        bind.execute(sa.text(
            "INSERT INTO videos (id, owner_type, owner_id, provider, status, embed_url, "
            "created_at, updated_at) "
            "VALUES (:id, 'training_video', :owner_id, :provider, 'ready', :embed_url, :now, :now)"
        ), {"id": uuid.uuid4(), "owner_id": row["id"], "provider": provider,
            "embed_url": row["video_path"], "now": now})

    op.drop_table("module_videos")


def downgrade() -> None:
    # module_videos is not recreated with its backfilled data — this
    # migration is not meant to be rolled back once real uploads have
    # happened through the new videos table; recreate the empty shape only
    # so a downgrade doesn't leave the DB in an inconsistent state.
    op.create_table(
        "module_videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("source_bucket", sa.String(64), nullable=False),
        sa.Column("source_path", sa.String(512), nullable=False),
        sa.Column("playlist_path", sa.String(512), nullable=True),
        sa.Column("key_path", sa.String(512), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("transcode_status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("transcode_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["module_items.id"], ondelete="CASCADE"),
    )
    op.drop_index("ix_videos_created_by", table_name="videos")
    op.drop_table("videos")
