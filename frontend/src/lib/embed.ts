/** YouTube/Vimeo URL → embeddable iframe src. Extracted out of
 * `pages/instructors/TrainingPlayer.tsx` (2026-09) so the Roadmap board's
 * task drawer can render a `video`-kind guideline the same way instructor
 * training videos already render — same "paste a URL, no upload" posture
 * (see docs/HANDOFF_LMS.md §11's video-upload decision). Falls back to the
 * original URL for a host this doesn't recognize; the caller decides
 * whether to iframe that anyway or offer it as a plain outbound link. */
// `modestbranding` drops the large YouTube logo watermark that otherwise
// sits over the paused/playing video; `rel=0` keeps the end-of-video
// screen to the same channel instead of unrelated recommendations.
// YouTube's embed terms don't allow removing the small logo in the
// control bar itself — this is as minimal as their API allows.
const YT_PARAMS = "modestbranding=1&rel=0";

export function toEmbedUrl(url: string): string {
  if (!url) return "";
  try {
    if (url.includes("youtu.be/")) {
      const id = url.split("youtu.be/")[1].split(/[?&]/)[0];
      return `https://www.youtube.com/embed/${id}?${YT_PARAMS}`;
    }
    const ytMatch = url.match(/[?&]v=([^&]+)/);
    if (ytMatch) return `https://www.youtube.com/embed/${ytMatch[1]}?${YT_PARAMS}`;
    if (url.includes("youtube.com/embed/")) {
      return `${url}${url.includes("?") ? "&" : "?"}${YT_PARAMS}`;
    }
    const vimeoMatch = url.match(/vimeo\.com\/(\d+)/);
    if (vimeoMatch) return `https://player.vimeo.com/video/${vimeoMatch[1]}`;
  } catch {
    /* ignore */
  }
  return url;
}

/** Whether `toEmbedUrl` recognized this as an embeddable host — the drawer
 * shows an iframe when true, a plain "open in new tab" link otherwise. */
export function isKnownEmbedHost(url: string): boolean {
  return /youtu\.be|youtube\.com|vimeo\.com/i.test(url);
}
