import { useState, type ReactNode } from "react";
import {
  CheckCircle2, ChevronDown, FileText, HelpCircle, Layers, Lock, PlayCircle, Video as VideoIcon,
} from "lucide-react";
import type { CourseDetail, ModuleDetail, ModuleItem } from "@/api/lms";
import { cn } from "@/lib/utils";

const KIND_ICON: Record<ModuleItem["kind"], typeof VideoIcon> = {
  video: VideoIcon, text: FileText, quiz: HelpCircle, flashcards: Layers,
};

/** The sidebar + content-pane split (design 1h) — owns which item is
 * selected; no route change per item. Net-new (can't reuse Sidebar.tsx —
 * D1 — and this is a different shape: content list, not a portal nav). */
export function PlayerLayout({
  course, modulesData, selectedItemId, onSelectItem, children,
}: {
  course: CourseDetail;
  modulesData: Record<string, ModuleDetail>;
  selectedItemId: string | null;
  onSelectItem: (itemId: string) => void;
  children: ReactNode;
}) {
  const [openModuleId, setOpenModuleId] = useState<string | null>(() => {
    const current = course.modules.find((m) => !m.locked && m.mandatory_completed < m.mandatory_total);
    return current?.module_id ?? course.modules.find((m) => !m.locked)?.module_id ?? null;
  });

  return (
    <div className="flex flex-col lg:flex-row lg:h-[calc(100vh-72px)]">
      <aside className="lg:w-[340px] lg:shrink-0 lg:overflow-y-auto border-b lg:border-b-0 lg:border-r border-border bg-card/30">
        <div className="p-4 sm:p-5">
          <h2 className="font-display text-base font-bold truncate">{course.title}</h2>
        </div>
        <div className="flex flex-col">
          {course.modules.map((module) => {
            const items = modulesData[module.module_id]?.items ?? [];
            const done = module.mandatory_total > 0 && module.mandatory_completed >= module.mandatory_total;
            const isOpen = openModuleId === module.module_id;
            return (
              <div key={module.module_id} className="border-t border-border/60">
                <button
                  onClick={() => !module.locked && setOpenModuleId(isOpen ? null : module.module_id)}
                  disabled={module.locked}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 sm:px-5 py-3.5 text-left transition-colors",
                    module.locked ? "cursor-default" : "cursor-pointer hover:bg-foreground/5",
                    isOpen && "bg-foreground/[0.03]",
                  )}
                >
                  <span className={cn(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                    module.locked ? "ring-1 ring-border text-muted-foreground"
                      : done ? "bg-emerald-500/15 text-emerald-500 ring-1 ring-emerald-500/40"
                      : isOpen ? "ring-1.5 ring-primary text-primary"
                      : "ring-1 ring-border text-muted-foreground",
                  )}>
                    {module.locked ? <Lock className="size-3" /> : done ? <CheckCircle2 className="size-3.5" /> : module.position}
                  </span>
                  <span className={cn("flex-1 min-w-0 text-sm truncate", module.locked ? "text-muted-foreground" : "font-medium")}>
                    {module.title ?? `Module ${module.position}`}
                  </span>
                  {!module.locked && (
                    <ChevronDown className={cn("size-4 text-muted-foreground shrink-0 transition-transform", isOpen && "rotate-180")} />
                  )}
                </button>
                {isOpen && !module.locked && (
                  <div className="pb-2">
                    {items.map((item) => {
                      const Icon = KIND_ICON[item.kind];
                      const isSelected = item.id === selectedItemId;
                      const isDone = item.status === "completed" || item.status === "skipped";
                      return (
                        <button
                          key={item.id}
                          onClick={() => onSelectItem(item.id)}
                          className={cn(
                            "w-full flex items-center gap-2.5 pl-11 pr-4 py-2 text-left text-sm transition-colors cursor-pointer",
                            isSelected ? "bg-primary/10 text-foreground font-medium" : "text-muted-foreground hover:bg-foreground/5",
                          )}
                        >
                          {isDone ? (
                            <CheckCircle2 className="size-3.5 shrink-0 text-emerald-500" />
                          ) : (
                            <Icon className={cn("size-3.5 shrink-0", isSelected && "text-primary")} />
                          )}
                          <span className="truncate">{item.title ?? item.kind}</span>
                        </button>
                      );
                    })}
                    {items.length === 0 && (
                      <div className="pl-11 pr-4 py-2 text-xs text-muted-foreground flex items-center gap-2">
                        <PlayCircle className="size-3.5" /> Loading...
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </aside>

      <div className="flex-1 min-w-0 overflow-y-auto p-5 sm:p-8 lg:p-10">
        <div className="max-w-[720px] mx-auto">
          {children}
        </div>
      </div>
    </div>
  );
}
