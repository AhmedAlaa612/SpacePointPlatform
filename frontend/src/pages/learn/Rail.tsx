import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";

/**
 * Horizontal scrolling shelf for the landing page (2026-08-12) — the
 * operator's ask was to browse paths and courses as rows on /learn rather
 * than navigating to separate Catalog/Paths tabs.
 *
 * Cards are fixed-width and the track scrolls on overflow, so a rail with
 * three items and a rail with thirty look the same. `snap-x` keeps a card
 * aligned to the left edge after a flick on touch.
 */
export function Rail({
  title, subtitle, onSeeAll, seeAllLabel = "See all", children,
}: {
  title: string;
  subtitle?: string;
  onSeeAll?: () => void;
  seeAllLabel?: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="font-display text-xl sm:text-2xl font-bold tracking-tight">{title}</h2>
          {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
        </div>
        {onSeeAll && (
          <button
            onClick={onSeeAll}
            className="flex shrink-0 items-center gap-1.5 text-sm font-medium text-primary hover:opacity-80 cursor-pointer"
          >
            {seeAllLabel} <ArrowRight className="size-3.5" />
          </button>
        )}
      </div>
      {/* -mx/px pair lets cards bleed to the viewport edge while keeping the
          first card aligned with the page gutter. */}
      <div className="-mx-5 sm:-mx-8 lg:-mx-14 px-5 sm:px-8 lg:px-14 overflow-x-auto snap-x scroll-pl-5 sm:scroll-pl-8 lg:scroll-pl-14 [scrollbar-width:thin]">
        <div className="flex gap-4 pb-2">{children}</div>
      </div>
    </section>
  );
}

/** Fixed-width card slot for a Rail — keeps every rail's rhythm identical. */
export function RailCard({ onClick, children }: { onClick?: () => void; children: ReactNode }) {
  return (
    <div
      onClick={onClick}
      className="w-[260px] sm:w-[290px] shrink-0 snap-start rounded-2xl border border-border bg-card overflow-hidden cursor-pointer hover:ring-1 hover:ring-primary/30 transition-shadow"
    >
      {children}
    </div>
  );
}
