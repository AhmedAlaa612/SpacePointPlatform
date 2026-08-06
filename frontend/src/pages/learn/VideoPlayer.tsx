import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { fetchVideoToken, videoPlaylistUrl } from "@/api/lms";

interface VideoPlayerProps {
  itemId: string;
  transcodeStatus: string | null;
  /** Called once, when playback reaches the end. */
  onEnded: () => void;
  /** Optional mid-video checkpoint (LMS D7) — called once when playback
   * crosses this timestamp; the caller pauses the video itself via the
   * returned ref control so the checkpoint quiz can render on top. */
  checkpointSeconds?: number | null;
  onCheckpoint?: () => void;
  /** Imperative resume, called by the parent once the checkpoint quiz passes. */
  resumeSignal: number;
}

/**
 * Thin hls.js wrapper for the token-gated AES-128 stream (LM1-6, D2). Fetches
 * a short-lived token, loads the (per-request, token-rewritten) playlist, and
 * exposes a checkpoint callback for the mid-video quiz. No custom controls —
 * native `<video controls>` is enough for a first pass and works on mobile.
 */
export function VideoPlayer({
  itemId, transcodeStatus, onEnded, checkpointSeconds, onCheckpoint, resumeSignal,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const checkpointFiredRef = useRef(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkpointFiredRef.current = false;
  }, [itemId]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const { token } = await fetchVideoToken(itemId);
        if (cancelled) return;
        const src = videoPlaylistUrl(itemId, token);
        const video = videoRef.current;
        if (!video) return;

        if (Hls.isSupported()) {
          const hls = new Hls();
          hlsRef.current = hls;
          hls.loadSource(src);
          hls.attachMedia(video);
          hls.on(Hls.Events.ERROR, (_evt, data) => {
            if (data.fatal) setError("Video playback failed. Please try again.");
          });
        } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
          // Safari/iOS: native HLS support, no hls.js needed.
          video.src = src;
        } else {
          setError("Your browser can't play this video.");
        }
      } catch {
        if (!cancelled) setError("Couldn't load this video. Please try again.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();

    return () => {
      cancelled = true;
      hlsRef.current?.destroy();
      hlsRef.current = null;
    };
  }, [itemId]);

  useEffect(() => {
    if (resumeSignal > 0) videoRef.current?.play().catch(() => undefined);
  }, [resumeSignal]);

  const handleTimeUpdate = () => {
    if (
      checkpointSeconds != null &&
      !checkpointFiredRef.current &&
      videoRef.current &&
      videoRef.current.currentTime >= checkpointSeconds
    ) {
      checkpointFiredRef.current = true;
      videoRef.current.pause();
      onCheckpoint?.();
    }
  };

  if (transcodeStatus !== "ready") {
    return (
      <div className="aspect-video rounded-2xl ring-1 ring-border bg-muted flex items-center justify-center text-sm text-muted-foreground">
        {transcodeStatus === "failed" ? "Video processing failed — contact ops." : "Video is still processing..."}
      </div>
    );
  }

  return (
    <div className="rounded-2xl overflow-hidden ring-1 ring-white/10 bg-black relative">
      {loading && (
        <div className="aspect-video flex items-center justify-center text-sm text-white/70">Loading video...</div>
      )}
      {error && (
        <div className="aspect-video flex items-center justify-center text-sm text-destructive px-4 text-center">
          {error}
        </div>
      )}
      <video
        ref={videoRef}
        controls
        playsInline
        onEnded={onEnded}
        onTimeUpdate={handleTimeUpdate}
        className={loading || error ? "hidden" : "w-full aspect-video"}
      />
    </div>
  );
}
