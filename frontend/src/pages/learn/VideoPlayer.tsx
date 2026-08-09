import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import {
  Play, Pause, Volume2, VolumeX, RotateCcw, PictureInPicture2, Maximize, Minimize,
  AlertCircle, StickyNote,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchCheckpoints, fetchVideoToken, submitCheckpointAnswer, videoPlaylistUrl,
  type CheckpointAnswerResult, type VideoCheckpoint,
} from "@/api/lms";

interface VideoPlayerProps {
  itemId: string;
  transcodeStatus: string | null;
  /** Called once, when playback reaches the end. */
  onEnded: () => void;
}

const SPEEDS = [1, 1.25, 1.5, 2];

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * hls.js wrapper for the token-gated AES-128 stream (LM1-6, D2) with a custom
 * control bar (design 1h) and video checkpoints (2026-08-07): notes render as
 * a non-blocking banner during their window, quizzes pause playback at their
 * timestamp until answered or skipped — both are drawn as marks on the
 * scrubber, not hidden state.
 */
export function VideoPlayer({ itemId, transcodeStatus, onEnded }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const prevTimeRef = useRef(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const [checkpoints, setCheckpoints] = useState<VideoCheckpoint[]>([]);
  const [activeNote, setActiveNote] = useState<VideoCheckpoint | null>(null);
  const [activeQuiz, setActiveQuiz] = useState<VideoCheckpoint | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    fetchCheckpoints(itemId).then(setCheckpoints).catch(() => setCheckpoints([]));
  }, [itemId]);

  // One retry per mount. A fatal error is usually either an expired playback
  // token (segments start 403-ing) or a dropped connection — both recover by
  // re-issuing the token and rebuilding the source, so the student sees a
  // blip instead of a dead end. A second failure is real; surface it.
  const retriedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    retriedRef.current = false;

    async function attach() {
      const { token } = await fetchVideoToken(itemId);
      if (cancelled) return;
      const src = videoPlaylistUrl(itemId, token);
      const video = videoRef.current;
      if (!video) return;

      // Rebuilding after an error: come back to where the student was rather
      // than restarting a 60-minute lecture from zero.
      const resumeAt = video.currentTime;

      if (Hls.isSupported()) {
        hlsRef.current?.destroy();
        const hls = new Hls();
        hlsRef.current = hls;
        hls.loadSource(src);
        hls.attachMedia(video);
        if (resumeAt > 0) {
          hls.once(Hls.Events.MANIFEST_PARSED, () => {
            video.currentTime = resumeAt;
            void video.play().catch(() => undefined);
          });
        }
        hls.on(Hls.Events.ERROR, (_evt, data) => {
          if (!data.fatal || cancelled) return;
          if (!retriedRef.current) {
            retriedRef.current = true;
            // recoverMediaError() is hls.js's own in-place fix for a decode
            // stall and doesn't need a new token; a network error does.
            if (data.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
            else void attach().catch(() => setError("Video playback failed. Please try again."));
            return;
          }
          setError("Video playback failed. Please try again.");
          setLoading(false);
        });
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        // Safari/iOS: native HLS support, no hls.js needed.
        video.src = src;
        if (resumeAt > 0) video.currentTime = resumeAt;
      } else {
        setError("Your browser can't play this video.");
        setLoading(false);
      }
    }

    // No setLoading(true)/setError("") reset here: ItemPane mounts this with
    // key={item.id}, so switching lessons remounts and useState gives us a
    // clean loading=true / error="" already.
    //
    // NB: loading is cleared by the <video>'s onCanPlay, NOT here. Clearing it
    // once attach() resolves only means hls.js has been *told* to start — the
    // first segment is still downloading, so the spinner used to vanish and
    // leave a black player with a live control bar for several seconds.
    void attach().catch(() => {
      if (cancelled) return;
      setError("Couldn't load this video. Please try again.");
      setLoading(false);
    });

    return () => {
      cancelled = true;
      hlsRef.current?.destroy();
      hlsRef.current = null;
    };
  }, [itemId]);

  useEffect(() => {
    const onFsChange = () => setFullscreen(document.fullscreenElement === containerRef.current);
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video) return;
    const t = video.currentTime;
    setCurrentTime(t);
    const prev = prevTimeRef.current;
    prevTimeRef.current = t;

    const note = checkpoints.find(
      (c) => c.kind === "note" && c.end_seconds != null && t >= c.start_seconds && t < c.end_seconds,
    );
    setActiveNote(note ?? null);

    if (!activeQuiz) {
      const crossed = checkpoints.find((c) => c.kind === "quiz" && prev < c.start_seconds && t >= c.start_seconds);
      if (crossed) {
        video.pause();
        setActiveQuiz(crossed);
      }
    }
  };

  const resumeFromQuiz = () => {
    setActiveQuiz(null);
    videoRef.current?.play().catch(() => undefined);
  };

  const togglePlay = () => {
    const video = videoRef.current;
    // A quiz checkpoint must be answered or skipped — the overlay covers the
    // video itself, but the control row sits below it, so without this guard
    // the visible play button would let a student resume without either.
    if (!video || activeQuiz) return;
    if (video.paused) void video.play();
    else video.pause();
  };

  const toggleMute = () => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setMuted(video.muted);
  };

  const restart = () => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = 0;
  };

  const cycleSpeed = () => {
    const video = videoRef.current;
    if (!video) return;
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    video.playbackRate = next;
    setSpeed(next);
  };

  const togglePip = () => {
    const video = videoRef.current;
    if (!video || !document.pictureInPictureEnabled) return;
    if (document.pictureInPictureElement) void document.exitPictureInPicture();
    else void video.requestPictureInPicture();
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void containerRef.current?.requestFullscreen();
  };

  const seekTo = (clientX: number, bar: HTMLDivElement) => {
    const video = videoRef.current;
    if (!video || !duration || activeQuiz) return;
    const rect = bar.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    video.currentTime = ratio * duration;
  };

  if (transcodeStatus !== "ready") {
    return (
      <div className="aspect-video w-[85%] mx-auto rounded-2xl ring-1 ring-border bg-muted flex items-center justify-center text-sm text-muted-foreground text-center px-6">
        {transcodeStatus === "failed"
          ? "Video processing failed — contact ops."
          : "Video is still processing — this can take a minute. It'll appear here automatically once ready."}
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-[85%] mx-auto rounded-2xl overflow-hidden ring-1 ring-white/10 bg-black relative">
      {loading && (
        <div className="aspect-video flex items-center justify-center text-sm text-white/70">Loading video...</div>
      )}
      {error && (
        <div className="aspect-video flex items-center justify-center text-sm text-destructive px-4 text-center">
          {error}
        </div>
      )}
      <div className={loading || error ? "hidden" : "relative"}>
        <video
          ref={videoRef}
          playsInline
          onEnded={onEnded}
          onTimeUpdate={handleTimeUpdate}
          onCanPlay={() => setLoading(false)}
          onLoadedMetadata={() => setDuration(videoRef.current?.duration ?? 0)}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onClick={togglePlay}
          className="w-full aspect-video cursor-pointer"
        />

        {activeNote && "body" in activeNote.content && (
          <div className="absolute left-3 right-3 bottom-3 flex items-start gap-2.5 rounded-xl bg-black/75 backdrop-blur px-4 py-3 text-sm text-white/90 pointer-events-none">
            <StickyNote className="size-4 shrink-0 mt-0.5 text-primary" />
            <span>{activeNote.content.body}</span>
          </div>
        )}

        {activeQuiz && (
          <CheckpointQuizOverlay itemId={itemId} checkpoint={activeQuiz} onResolved={resumeFromQuiz} />
        )}
      </div>

      {!loading && !error && (
        <div className={`px-4 py-3 flex flex-col gap-2.5 bg-black/90 ${activeQuiz ? "opacity-40 pointer-events-none" : ""}`}>
          <div
            className="h-1.5 rounded-full bg-white/15 relative cursor-pointer"
            onClick={(e) => seekTo(e.clientX, e.currentTarget)}
          >
            <div
              className="absolute left-0 top-0 bottom-0 rounded-full bg-primary"
              style={{ width: duration ? `${(currentTime / duration) * 100}%` : "0%" }}
            />
            {duration > 0 && checkpoints.map((c) => (
              <div
                key={c.id}
                title={c.kind === "quiz" ? "Quiz checkpoint" : "Note"}
                className={`absolute top-1/2 -translate-y-1/2 w-[3px] h-3.5 rounded-sm ${c.kind === "quiz" ? "bg-amber-400" : "bg-sky-400"}`}
                style={{ left: `${(c.start_seconds / duration) * 100}%` }}
              />
            ))}
          </div>

          <div className="flex items-center gap-4 text-white/80">
            <button onClick={togglePlay} className="text-white hover:text-white/80 transition-colors cursor-pointer">
              {isPlaying ? <Pause className="size-[19px]" /> : <Play className="size-[19px]" />}
            </button>
            <button onClick={toggleMute} className="hover:text-white transition-colors cursor-pointer">
              {muted ? <VolumeX className="size-[19px]" /> : <Volume2 className="size-[19px]" />}
            </button>
            <button onClick={restart} className="hover:text-white transition-colors cursor-pointer" title="Restart">
              <RotateCcw className="size-[19px]" />
            </button>
            <div className="font-mono text-xs text-white">{formatClock(currentTime)} / {formatClock(duration)}</div>
            <div className="flex items-center gap-4 ml-auto">
              <button onClick={cycleSpeed} className="font-display text-sm font-semibold text-white cursor-pointer" title="Playback speed">
                {speed}×
              </button>
              {document.pictureInPictureEnabled && (
                <button onClick={togglePip} className="hover:text-white transition-colors cursor-pointer" title="Picture in picture">
                  <PictureInPicture2 className="size-[19px]" />
                </button>
              )}
              <button onClick={toggleFullscreen} className="hover:text-white transition-colors cursor-pointer" title="Fullscreen">
                {fullscreen ? <Minimize className="size-[19px]" /> : <Maximize className="size-[19px]" />}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CheckpointQuizOverlay({
  itemId, checkpoint, onResolved,
}: { itemId: string; checkpoint: VideoCheckpoint; onResolved: () => void }) {
  const content = "question_type" in checkpoint.content ? checkpoint.content : null;

  const [selected, setSelected] = useState<number | number[] | string>(() =>
    content?.question_type === "multiselect" ? [] : content?.question_type === "open" ? "" : -1,
  );
  const [result, setResult] = useState<CheckpointAnswerResult | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!content) return null;

  const canSubmit =
    content.question_type === "open" ? typeof selected === "string" && selected.trim().length > 0
    : content.question_type === "mcq" ? typeof selected === "number" && selected >= 0
    : Array.isArray(selected) && selected.length > 0;

  const submit = async () => {
    setSubmitting(true);
    try {
      const res = await submitCheckpointAnswer(itemId, checkpoint.id, selected);
      setResult(res);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleMulti = (i: number) => {
    setSelected((prev) => {
      const arr = Array.isArray(prev) ? prev : [];
      return arr.includes(i) ? arr.filter((x) => x !== i) : [...arr, i];
    });
  };

  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl bg-card ring-1 ring-primary/25 shadow-2xl p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-amber-500">
            <AlertCircle className="size-3.5" /> Checkpoint · paused at {formatClock(checkpoint.start_seconds)}
          </div>
        </div>
        <p className="font-display text-lg font-semibold leading-snug">{content.prompt}</p>

        {content.question_type === "mcq" && content.options && (
          <div className="flex flex-col gap-2">
            {content.options.map((opt, i) => (
              <button
                key={i}
                disabled={!!result}
                onClick={() => setSelected(i)}
                className={`text-left px-3.5 py-2.5 rounded-xl ring-1 text-sm cursor-pointer disabled:cursor-default transition-colors ${
                  selected === i ? "ring-primary/50 bg-primary/10" : "ring-border hover:bg-muted/50"
                }`}
              >
                {opt.text}
              </button>
            ))}
          </div>
        )}

        {content.question_type === "multiselect" && content.options && (
          <div className="flex flex-col gap-2">
            {content.options.map((opt, i) => {
              const checked = Array.isArray(selected) && selected.includes(i);
              return (
                <button
                  key={i}
                  disabled={!!result}
                  onClick={() => toggleMulti(i)}
                  className={`text-left px-3.5 py-2.5 rounded-xl ring-1 text-sm cursor-pointer disabled:cursor-default flex items-center gap-2.5 transition-colors ${
                    checked ? "ring-primary/50 bg-primary/10" : "ring-border hover:bg-muted/50"
                  }`}
                >
                  <span className={`size-4 rounded shrink-0 ring-1 ${checked ? "bg-primary ring-primary" : "ring-border"}`} />
                  {opt.text}
                </button>
              );
            })}
          </div>
        )}

        {content.question_type === "open" && (
          <textarea
            value={typeof selected === "string" ? selected : ""}
            onChange={(e) => setSelected(e.target.value)}
            disabled={!!result}
            rows={3}
            placeholder="Type your answer..."
            className="w-full px-3 py-2 rounded-xl ring-1 ring-border bg-background text-sm resize-none focus:outline-none focus:ring-primary/40"
          />
        )}

        {result && (
          <p className={`text-sm ${result.correct === null ? "text-muted-foreground" : result.correct ? "text-emerald-500" : "text-destructive"}`}>
            {result.correct === null ? "Noted — thanks for answering." : result.correct ? "Correct!" : "Not quite."}
            {result.explanation && ` ${result.explanation}`}
          </p>
        )}

        <div className="flex items-center justify-between gap-3 pt-1">
          <button onClick={onResolved} className="text-sm text-muted-foreground hover:text-foreground cursor-pointer">
            Skip
          </button>
          {result ? (
            <Button onClick={onResolved}>Continue</Button>
          ) : (
            <Button onClick={() => void submit()} disabled={!canSubmit || submitting}>
              {submitting ? "Checking..." : "Check answer"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
