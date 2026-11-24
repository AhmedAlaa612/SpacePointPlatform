import { useEffect, useRef, useState } from "react";
import { BookOpen } from "lucide-react";
import { apiBaseUrl } from "@/api/client";
import { cn } from "@/lib/utils";

interface BookCoverProps {
  title: string;
  coverUrl?: string | null;
  coverPageUrl?: string | null;
  chapterCount?: number;
  languages?: string[];
  compact?: boolean;
  className?: string;
}

function resolveCoverPageSrc(coverPageUrl?: string | null): string | null {
  if (!coverPageUrl) return null;
  if (/^https?:\/\//i.test(coverPageUrl)) return coverPageUrl;
  const base = (apiBaseUrl || "").replace(/\/$/, "");
  const rel = coverPageUrl.startsWith("/") ? coverPageUrl : `/${coverPageUrl}`;
  return `${base}${rel}`;
}

export function BookCover({
  title,
  coverUrl,
  coverPageUrl,
  chapterCount,
  languages,
  compact = false,
  className,
}: BookCoverProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  const [iframeLoaded, setIframeLoaded] = useState(false);

  const pageSrc = !coverUrl ? resolveCoverPageSrc(coverPageUrl) : null;

  useEffect(() => {
    setIframeLoaded(false);
  }, [pageSrc]);

  useEffect(() => {
    if (!pageSrc) return;
    const el = hostRef.current;
    if (!el) return;

    const measure = () => {
      const next = el.clientWidth;
      if (next > 0) setWidth(next);
    };
    measure();

    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [pageSrc]);

  if (coverUrl) {
    return (
      <div className={cn("relative w-full h-full overflow-hidden bg-muted", className)}>
        <img src={coverUrl} alt={title} className="w-full h-full object-cover" />
      </div>
    );
  }

  const fallbackView = compact ? (
    <div className="w-full h-full bg-[#18181B] text-white flex items-center justify-center border-t-2 border-[#7C3AED]">
      <BookOpen className="size-4 text-zinc-300" />
    </div>
  ) : (
    <div className="w-full h-full bg-[#18181B] text-white flex flex-col justify-between p-5 border-t-4 border-[#7C3AED]">
      <div className="flex items-center justify-between gap-2">
        <img src="/space-logo-white.png" alt="SpacePoint" className="h-4 w-auto object-contain" />
        <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-1 rounded-[10px] bg-[#2E1065] text-white">
          Book
        </span>
      </div>
      <h3 className="font-display text-lg font-bold leading-snug text-white">
        {title}
      </h3>
      <div className="flex items-center justify-between text-xs text-zinc-400">
        {typeof chapterCount === "number" ? <span>{chapterCount} chapters</span> : <span />}
        {languages?.length ? <span className="uppercase">{languages.join(" / ")}</span> : null}
      </div>
    </div>
  );

  if (!pageSrc) {
    return <div className={cn("relative w-full h-full overflow-hidden", className)}>{fallbackView}</div>;
  }

  const scale = width > 0 ? width / 480 : 0.4;

  return (
    <div ref={hostRef} className={cn("relative w-full h-full overflow-hidden bg-[#18181B]", className)}>
      {fallbackView}
      <iframe
        src={pageSrc}
        title={title}
        sandbox=""
        scrolling="no"
        tabIndex={-1}
        aria-hidden="true"
        onLoad={() => setIframeLoaded(true)}
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "480px",
          height: "640px",
          border: 0,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
          pointerEvents: "none",
        }}
        className={iframeLoaded ? "opacity-100 transition-opacity duration-150" : "opacity-0"}
      />
    </div>
  );
}
