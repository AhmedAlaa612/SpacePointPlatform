import { useRef } from "react";
import type { LmsProgramChecklistItem } from "@/api/lms";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { cn } from "@/lib/utils";
import { TaskTile } from "./TaskTile";
import { TraceLayer } from "./TraceLayer";

const DESKTOP_ROW_SIZE = 4;

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** The tile field — desktop: three-plus rows of four, serpentine (row 2
 * reversed, row 3 forward, ...), even visual columns offset `mt-4`. Mobile:
 * a single alternating left/right column. One `TraceLayer` behind either
 * layout, measuring whichever is actually rendered (only one DOM shape
 * exists at a time — see `useMediaQuery`, not a single reflowing flex
 * container, since the two layouts are structurally different per the
 * design spec). */
export function TileField({
  items, liveTaskId, onOpenItem,
}: {
  items: LmsProgramChecklistItem[];
  liveTaskId: string | null;
  onOpenItem: (item: LmsProgramChecklistItem) => void;
}) {
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const containerRef = useRef<HTMLDivElement>(null);
  const tileRefs = useRef<Map<string, HTMLDivElement>>(new Map());

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
      <TraceLayer containerRef={containerRef} tileRefs={tileRefs} items={items} />

      {isDesktop ? (
        <div className="flex flex-col gap-[46px]">
          {chunk(items, DESKTOP_ROW_SIZE).map((row, rowIndex) => {
            const reversed = rowIndex % 2 === 1;
            return (
              <div
                key={rowIndex}
                className={cn("flex items-start justify-between gap-4", reversed && "flex-row-reverse")}
              >
                {row.map((item, domIndex) => {
                  const visualCol = reversed ? row.length - 1 - domIndex : domIndex;
                  return (
                    <div key={item.id} className={cn(visualCol % 2 === 1 && "mt-4")}>
                      <TaskTile
                        item={item}
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
                item={item}
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
