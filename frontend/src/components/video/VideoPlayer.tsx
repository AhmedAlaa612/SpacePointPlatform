import { useEffect, useRef, useState } from "react"
import Hls from "hls.js"
import { toEmbedUrl } from "@/lib/embed"
import { fetchVideoToken, videoPlaylistUrl } from "@/api/lms"

/** Mirrors `video_service.get_playback_info()`'s response shape exactly —
 * see backend/app/services/video_service.py. Every feature this serves
 * (Curriculum Library, checklist guideline video, facilitator training
 * video, LMS module video via the token-gated generic /videos/{id}/...
 * surface) can produce any of embed/direct/hls_encrypted — every upload
 * path now requests hls_encrypted, "direct" only survives on whatever was
 * uploaded before that switch. `video_id` is required for hls_encrypted:
 * this component fetches its own token off it, rather than a caller doing
 * so and passing a URL down, so the token-refresh-on-error retry (below)
 * has everything it needs locally.
 *
 * LMS module video keeps its own separate, checkpoint-coupled hls.js player
 * in pages/learn/VideoPlayer.tsx rather than using this one — checkpoints
 * are LMS-only state this shared component must never know about. That
 * player's hls_encrypted mechanics (attach/retry/native-HLS fallback) are
 * mirrored here, minus checkpoints and the custom control bar — native
 * `<video controls>` throughout, matching this component's direct-mode
 * branch. */
export interface VideoPlaybackInfo {
  provider: "youtube" | "vimeo" | "upload"
  status?: string
  embed_url?: string | null
  mode?: "direct" | "hls_encrypted"
  url?: string | null
  duration_seconds?: number | null
  status_error?: string | null
  video_id?: string | null
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

function HlsEncryptedVideo({
  videoId, title, className, placeholderClassName, autoPlay,
}: {
  videoId: string
  title?: string
  className?: string
  placeholderClassName?: string
  autoPlay?: boolean
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const hlsRef = useRef<Hls | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    let retried = false
    setError("")

    async function attach() {
      const { token } = await fetchVideoToken(videoId)
      if (cancelled) return
      const src = videoPlaylistUrl(videoId, token)
      const video = videoRef.current
      if (!video) return

      if (Hls.isSupported()) {
        hlsRef.current?.destroy()
        const hls = new Hls()
        hlsRef.current = hls
        hls.loadSource(src)
        hls.attachMedia(video)
        // A fatal error here is usually an expired token (segments start
        // 403-ing) or a dropped connection — both recover by re-issuing the
        // token and rebuilding the source, same one-retry-then-give-up
        // shape pages/learn/VideoPlayer.tsx already uses.
        hls.on(Hls.Events.ERROR, (_evt, data) => {
          if (!data.fatal || cancelled) return
          if (!retried) {
            retried = true
            if (data.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError()
            else void attach().catch(() => setError("Video playback failed. Please try again."))
            return
          }
          setError("Video playback failed. Please try again.")
        })
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = src // Safari/iOS native HLS support, no hls.js needed
      } else {
        setError("Your browser can't play this video.")
      }
    }

    void attach().catch(() => {
      if (!cancelled) setError("Couldn't load this video. Please try again.")
    })

    return () => {
      cancelled = true
      hlsRef.current?.destroy()
      hlsRef.current = null
    }
  }, [videoId])

  if (error) return <VideoPlaceholder text={error} className={placeholderClassName} />

  return (
    <video
      ref={videoRef}
      controls
      autoPlay={autoPlay}
      controlsList="nodownload noremoteplayback"
      disablePictureInPicture
      onContextMenu={(e) => e.preventDefault()}
      title={title}
      className={className ?? "w-full rounded-lg bg-black"}
    />
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

  if (info.mode === "hls_encrypted") {
    if (info.status === "failed") {
      return <VideoPlaceholder text="This video failed to process." className={placeholderClassName} />
    }
    if (info.status !== "ready" || !info.video_id) {
      return (
        <VideoPlaceholder
          text="Video is still processing — this can take a minute. It'll appear here automatically once ready."
          className={placeholderClassName}
        />
      )
    }
    return (
      <HlsEncryptedVideo
        videoId={info.video_id}
        title={title}
        className={className}
        placeholderClassName={placeholderClassName}
        autoPlay={autoPlay}
      />
    )
  }

  return <VideoPlaceholder text="This video can't be played here." className={placeholderClassName} />
}
