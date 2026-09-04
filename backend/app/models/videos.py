"""The standardized video service — one table for every video the platform
hosts or links to, regardless of which feature owns it.

Before this, video handling was duplicated four ways: `ModuleVideo` (LMS
course modules, full ffmpeg->AES-HLS pipeline), `LmsProgramItem.guideline_url`
(checklist guideline videos, link-only), `LibraryResource` (instructor
library, plain upload sniffed by file extension, no transcode), and
`TrainingVideo.video_path` (facilitator training, link-only despite a stale
doc-comment claiming otherwise). Each had its own schema and its own bespoke
frontend player. This table and `services/video_service.py` are the single
shared path going forward — any feature can attach a video to any owning row
by writing one `Video` here, in one of three shapes:

- `provider="youtube"|"vimeo"`: `embed_url` holds the pasted link, played as
  an iframe. Nothing async — `status` is `"ready"` immediately.
- `provider="upload", upload_mode="direct"`: `source_bucket`/`source_path`
  point at the uploaded file itself, served as a plain signed URL — no
  transcode, no per-chunk access re-validation (same posture the Instructor
  Library's plain `<video>` playback already had, generalized). `status`
  flips to `"ready"` the moment the upload lands.
- `provider="upload", upload_mode="hls_encrypted"`: `source_bucket`/
  `source_path` are the pre-transcode source; `playlist_path`/`key_path` are
  the AES-128 HLS output an ARQ worker produces (see `services/video_service.py`,
  the generalized form of the LMS-only pipeline this replaces). `status`
  spends real time in `"processing"` here, unlike the other two modes.

`owner_type`/`owner_id` is a polymorphic pointer, enforced at the service
layer rather than the DB — the same discriminator idiom `LmsProgramItem.
owner_type`/`owner_id` already uses in this codebase (no single FK column can
point at four different tables). Initial values: `module_item`,
`library_resource`, `program_item_guideline`, `training_video` — new owner
types (e.g. a future standalone Guides feature) need no schema change, just a
new string.

One video per owner today (`UniqueConstraint`) — nothing currently needs an
owner to hold more than one. If that changes, this becomes a plain index
instead; additive, not a rewrite.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", name="uq_videos_owner"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # module_item|library_resource|program_item_guideline|training_video
    owner_type = Column(String(32), nullable=False)
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # youtube|vimeo|upload
    provider = Column(String(16), nullable=False)
    # hls_encrypted|direct — only set when provider="upload"
    upload_mode = Column(String(16), nullable=True)
    # pending|processing|ready|failed
    status = Column(String(16), nullable=False, default="ready")
    status_error = Column(Text, nullable=True)

    # provider=youtube|vimeo — the pasted URL, verbatim (embed-URL shape is
    # derived at render time, same as lib/embed.ts already does; no reason
    # to store a derived form of something this cheap to recompute).
    embed_url = Column(String(512), nullable=True)

    # provider=upload: the pre-transcode source (hls_encrypted) or the
    # served file itself (direct).
    source_bucket = Column(String(64), nullable=True)
    source_path = Column(String(512), nullable=True)
    # provider=upload, upload_mode=hls_encrypted only.
    playlist_path = Column(String(512), nullable=True)
    key_path = Column(String(512), nullable=True)

    duration_seconds = Column(Integer, nullable=True)

    # Where THIS video's student-facing bytes actually live right now — the
    # HLS output for hls_encrypted, the source file itself for direct. NULL
    # (every pre-existing row) means local/VPS; "r2" means Cloudflare R2.
    # Deliberately per-row, not a global setting: it is what makes migrating
    # one video (or one course) to R2 at a time possible while everything
    # else keeps serving from wherever it already was — no flag day, no
    # window where every video moves at once. See video_service.py's
    # _hls_backend/_source_backend, which read this instead of a global
    # switch, and run_encrypted_transcode's zero-downtime re-encode path,
    # which only writes this once the new output is verified in place.
    storage_backend = Column(String(16), nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
