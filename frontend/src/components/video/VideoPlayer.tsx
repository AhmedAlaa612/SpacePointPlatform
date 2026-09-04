import { toEmbedUrl } from "@/lib/embed"

/** Mirrors `video_service.get_playback_info()`'s response shape exactly —
 * see backend/app/services/video_service.py. `hls_encrypted` is
 * deliberately not rendered here: every feature this shared component
 * serves (Curriculum Library, checklist guideline video, facilitator
 * training video) only ever produces `embed`/`direct` videos. The one
 * `hls_encrypted` consumer (LMS course module video) keeps its mature,
 * checkpoint-coupled hls.js player in pages/learn/VideoPlayer.tsx rather
 * than being folded in here — see that file's own note. */
export interface VideoPlaybackInfo {
  provider: "youtube" | "vimeo" | "upload"
  status?: string
  embed_url?: string | null
  mode?: "direct" | "hls_encrypted"
  url?: string | null
  duration_seconds?: number | null
  status_error?: string | null
}

function VideoPlaceholder({ text, className }: { text: string; className?: string }) {
  return (
    <div
      className={
        className ??
        "aspect-video rounded-lg border border-dashed border-border flex items-center justify-center text-sm text-muted-foreground bg-muted/20"
      }
    >
      {text}
    </div>
  )
}

export function VideoPlayer({
  info, title, className, placeholderClassName, autoPlay,
}: {
  info: VideoPlaybackInfo
  title?: string
  className?: string
  placeholderClassName?: string
  autoPlay?: boolean
}) {
  if (info.provider === "youtube" || info.provider === "vimeo") {
    if (!info.embed_url) return <VideoPlaceholder text="Video not configured yet." className={placeholderClassName} />
    return (
      <div className={className ?? "aspect-video rounded-lg overflow-hidden"}>
        <iframe
          src={toEmbedUrl(info.embed_url)}
          title={title ?? "Video"}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          className="w-full h-full"
        />
      </div>
    )
  }

  if (info.mode === "direct") {
    if (info.status === "failed") {
      return <VideoPlaceholder text="This video failed to process." className={placeholderClassName} />
    }
    if (!info.url) {
      return <VideoPlaceholder text="Video is processing…" className={placeholderClassName} />
    }
    return (
      <video
        src={info.url}
        controls
        autoPlay={autoPlay}
        controlsList="nodownload noremoteplayback"
        disablePictureInPicture
        onContextMenu={(e) => e.preventDefault()}
        className={className ?? "w-full rounded-lg bg-black"}
      />
    )
  }

  return <VideoPlaceholder text="This video can't be played here." className={placeholderClassName} />
}
