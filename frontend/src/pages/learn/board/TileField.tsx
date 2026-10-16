import { useEffect, useRef, useState } from "react";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { cn } from "@/lib/utils";
import { TaskTile } from "./TaskTile";
import { TraceLayer } from "./TraceLayer";
import type { BoardTile } from "./roadmap";

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** The tile field — desktop: rows of four, serpentine (row 2 reversed, row 3
 * forward, ...); tablet/iPad: rows of two, serpentine; mobile: a single
 * alternating left/right column. Even visual columns offset `mt-4`. One
 * `TraceLayer` behind whichever layout is rendered, measuring measured DOM
 * geometry via ResizeObserver. */
export function TileField({
  items, liveTaskId, onOpenItem,
}: {
  items: BoardTile[];
  liveTaskId: string | null;
  onOpenItem: (item: BoardTile) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const tileRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // Initial media query matches for SSR/first paint before ResizeObserver measures container
  const isDesktopQuery = useMediaQuery("(min-width: 1080px)");
  const isTabletQuery = useMediaQuery("(min-width: 768px)");

  const [containerWidth, setContainerWidth] = useState<number | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 4 tiles of 158px + 3 gaps of 16px require >= 680px.
  // 2 tiles of 158px + 1 gap of 16px require >= 332px (comfortably at >= 400px).
  // Narrower screens (< 400px) use the mobile single alternating column.
  const columns = containerWidth !== null
    ? (containerWidth >= 680 ? 4 : containerWidth >= 400 ? 2 : 1)
    : (isDesktopQuery ? 4 : isTabletQuery ? 2 : 1);

  const isMobile = columns === 1;

  const registerRef = (id: string) => (el: HTMLDivElement | null) => {
    if (el) tileRefs.current.set(id, el);
    else tileRefs.current.delete(id);
  };

  return (
    // `isolate` (not just `relative`) is required: a merely-positioned
    // ancestor with no z-index doesn't contain a negative-z-index child's
    // stacking — without this the trace SVG (-z-[1]) escapes to whichever
    // ancestor DOES establish a stacking context and paints behind the
    // whole page instead of just behind these tiles.
    <div ref={containerRef} className="relative isolate">
      <TraceLayer containerRef={containerRef} tileRefs={tileRefs} items={items} isMobile={isMobile} />

      {!isMobile ? (
        <div className="flex flex-col gap-[46px]">
          {chunk(items, columns).map((row, rowIndex) => {
            const reversed = rowIndex % 2 === 1;
            return (
              <div
                key={rowIndex}
                className={cn("flex items-start justify-between gap-4", reversed && "flex-row-reverse")}
              >
                {row.map((item, domIndex) => {
                  const visualCol = reversed ? columns - 1 - domIndex : domIndex;
                  return (
                    <div key={item.id} className={cn(visualCol % 2 === 1 && "mt-4")}>
                      <TaskTile
                        tile={item}
                        number={items.indexOf(item) + 1}
                        isPulsing={item.id === liveTaskId}
                        onOpen={() => onOpenItem(item)}
                        tileRef={registerRef(item.id)}
                      />
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex flex-col gap-9">
          {items.map((item, index) => (
            <div key={item.id} className={cn("flex", index % 2 === 0 ? "justify-start" : "justify-end")}>
              <TaskTile
                tile={item}
                number={index + 1}
                isPulsing={item.id === liveTaskId}
                onOpen={() => onOpenItem(item)}
                tileRef={registerRef(item.id)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
