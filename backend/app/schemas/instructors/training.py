from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TrainingVideoOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    notes: Optional[str] = None
    video_url: str = ""
    # True once a real file has been uploaded through the standardized video
    # service (owner_type="training_video") — video_url stays whatever
    # embed link was set at creation (unused going forward once an upload
    # supersedes it), same no-baked-in-signed-url posture has_pdf/
    # guideline_video_uploaded follow. The player calls the separate
    # resolve-url endpoint (GET .../stream) to actually view it.
    video_uploaded: bool = False
    sort_order: int
    is_completed: bool = False

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm_video(cls, v: object, is_completed: bool = False, video_uploaded: bool = False) -> "TrainingVideoOut":
        return cls(
            id=getattr(v, "id"),
            title=getattr(v, "title"),
            description=getattr(v, "description"),
            notes=getattr(v, "notes"),
            video_url=getattr(v, "video_path", "") or "",
            video_uploaded=video_uploaded,
            sort_order=getattr(v, "sort_order"),
            is_completed=is_completed,
        )


class TrainingModuleOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    sort_order: int
    videos: list[TrainingVideoOut] = []

    class Config:
        from_attributes = True


class TrainingModuleCreate(BaseModel):
    title: str
    description: Optional[str] = None
    sort_order: int = 1


class TrainingVideoCreate(BaseModel):
    module_id: UUID
    title: str
    description: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int = 1


class LibraryVideoPlaybackInfo(BaseModel):
    """Mirrors video_service.get_playback_info()'s response shape exactly,
    and frontend/src/components/video/VideoPlayer.tsx's VideoPlaybackInfo
    interface field for field — passed straight through as that component's
    `info` prop, no reshaping on either side."""
    provider: str  # "youtube" | "vimeo" | "upload"
    status: str | None = None
    embed_url: str | None = None
    mode: str | None = None  # "direct" | "hls_encrypted"
    url: str | None = None
    duration_seconds: int | None = None
    status_error: str | None = None
    # Required for hls_encrypted playback — the shared <VideoPlayer> fetches
    # its own token off this id (GET /videos/{video_id}/token) rather than
    # taking a separate prop that could drift out of sync with this info.
    video_id: str | None = None


class LibraryResourceOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    format: str
    file_url: str          # signed URL at response time (not stored value)
    resource_type: str = "file"
    # Set only for a video-service-backed resource (uploaded or embedded
    # video) — None for a PDF/other file or a plain external link. The
    # facilitator Library UI uses this, not file_url, to decide whether/how
    # to render a <VideoPlayer>.
    video_info: LibraryVideoPlaybackInfo | None = None

    class Config:
        from_attributes = True


class LibraryModuleOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    resources: list[LibraryResourceOut] = []

    class Config:
        from_attributes = True


class LibraryModuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
