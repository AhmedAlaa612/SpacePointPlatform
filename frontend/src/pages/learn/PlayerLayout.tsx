import { useState, type ReactNode } from "react";
import { Link, useSearch } from "@tanstack/react-router";
import {
  ArrowLeft, CheckCircle2, ChevronDown, FileText, HelpCircle, Layers, Lock, PanelLeftClose, PanelLeftOpen,
  Paperclip, PlayCircle, Rocket, Video as VideoIcon,
} from "lucide-react";
import { fetchModule, type CourseDetail, type ModuleDetail, type ModuleItem, type ModuleLock } from "@/api/lms";
import { cn } from "@/lib/utils";

const KIND_ICON: Record<ModuleItem["kind"], typeof VideoIcon> = {
  video: VideoIcon, text: FileText, quiz: HelpCircle, flashcards: Layers, attachment: Paperclip, mission: Rocket,
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
  // Whole-column collapse (2026-09), independent of any single module's own
  // open/closed state — a "sign to expand/collapse the sidebar itself", not
  // just its rows. Desktop only; mobile already has no column to collapse
  // (see the "Back to course" link below).
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // Only used to carry the "opened from a checklist" chain through to the
  // course landing page — same param TaskDrawer/LearnCourse already thread
  // for the completion-celebration "back to your program" nudge.
  const { program } = useSearch({ strict: false }) as { program?: string };

  // A locked module's items were never fetched by LearnPlayer's own
  // loadUnlockedModules (unlocked-only, by design — see its own docblock) —
  // fetched here instead, on demand, the first time a locked row is opened.
  // Same "preview it, nothing more" pattern LearnCourse.tsx's ModuleRow
  // already uses on the landing page, so locked modules get a real chevron
  // + preview here too instead of being fully inert.
  const [previewData, setPreviewData] = useState<Record<string, ModuleDetail>>({});
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null);

  const toggleModule = (module: ModuleLock) => {
    const isOpen = openModuleId === module.module_id;
    setOpenModuleId(isOpen ? null : module.module_id);
    if (!isOpen && module.locked && !modulesData[module.module_id] && !previewData[module.module_id]) {
      setPreviewLoadingId(module.module_id);
      fetchModule(module.module_id)
        .then((m) => setPreviewData((prev) => ({ ...prev, [module.module_id]: m })))
        .catch(() => {})
        .finally(() => setPreviewLoadingId((cur) => (cur === module.module_id ? null : cur)));
    }
  };

  // lg:h-screen, not a calc() subtracting a navbar height — that was left
  // over from the pre-Roadmap-redesign top navbar (LearnNav.tsx, deleted).
  // The sidebar replacing it is `fixed`, so it takes no space out of this
  // row; the old offset just left a dead strip at the bottom of the
  // viewport where this row's internal overflow-y-auto panes fell 72px
  // short of the real screen height.
  return (
    <div className="flex flex-col lg:flex-row lg:h-screen">
      {/* Below `lg` the module list doesn't fit stacked above the content
          the way it does as a fixed-width side column — it just pushed the
          actual lesson off the bottom of the screen. Mobile instead gets a
          "Back to course" link (below) to the landing page's own expandable
          module list (LearnCourse.tsx's ModuleRow) to browse/pick from. */}
      {sidebarOpen && (
        <aside className="hidden lg:block lg:w-[380px] lg:shrink-0 lg:overflow-y-auto border-b lg:border-b-0 lg:border-r border-border bg-card/30">
          <div className="p-5 sm:p-6 flex items-center justify-between gap-2">
            <h2 className="font-display text-lg font-bold truncate">{course.title}</h2>
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="shrink-0 rounded-lg p-1.5 text-muted-foreground hover:bg-foreground/5 hover:text-foreground transition-colors cursor-pointer"
              title="Collapse module list"
            >
              <PanelLeftClose className="size-[18px]" />
            </button>
          </div>
          <div className="flex flex-col">
            {course.modules.map((module) => {
              const items = (modulesData[module.module_id] ?? previewData[module.module_id])?.items ?? [];
              const done = module.mandatory_total > 0 && module.mandatory_completed >= module.mandatory_total;
              const isOpen = openModuleId === module.module_id;
              const isPreviewLoading = previewLoadingId === module.module_id;
              return (
                <div key={module.module_id} className="border-t border-border/60">
                  <button
                    onClick={() => toggleModule(module)}
                    className={cn(
                      "w-full flex items-center gap-3.5 px-5 sm:px-6 py-4 text-left transition-colors cursor-pointer hover:bg-foreground/5",
                      isOpen && "bg-foreground/[0.03]",
                    )}
                  >
                    <span className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
                      module.locked ? "ring-1 ring-border text-muted-foreground"
                        : done ? "bg-emerald-500/15 text-emerald-500 ring-1 ring-emerald-500/40"
                        : isOpen ? "ring-1.5 ring-primary text-primary"
                        : "ring-1 ring-border text-muted-foreground",
                    )}>
                      {module.locked ? <Lock className="size-4" /> : done ? <CheckCircle2 className="size-4" /> : module.position}
                    </span>
                    <span className={cn("flex-1 min-w-0 text-base truncate", module.locked ? "text-muted-foreground" : "font-medium")}>
                      {module.title ?? `Module ${module.position}`}
                    </span>
                    <ChevronDown className={cn("size-5 text-muted-foreground shrink-0 transition-transform", isOpen && "rotate-180")} />
                  </button>
                  {isOpen && (
                    <div className="pb-2">
                      {items.map((item) => {
                        const Icon = KIND_ICON[item.kind];
                        const isSelected = item.id === selectedItemId;
                        const isDone = item.status === "completed" || item.status === "skipped";
                        return (
                          <button
                            key={item.id}
                            onClick={() => !module.locked && onSelectItem(item.id)}
                            disabled={module.locked}
                            className={cn(
                              "w-full flex items-center gap-2.5 pl-12 pr-5 py-2.5 text-left text-sm transition-colors",
                              module.locked ? "cursor-default text-muted-foreground/70"
                                : isSelected ? "cursor-pointer bg-primary/10 text-foreground font-medium"
                                : "cursor-pointer text-muted-foreground hover:bg-foreground/5",
                            )}
                          >
                            <span className="relative shrink-0">
                              <Icon className={cn("size-4", isDone && "text-emerald-500", isSelected && "text-primary")} />
                              {isDone && (
                                <CheckCircle2 className="absolute -top-0.5 -right-1 size-3 text-emerald-500 bg-card rounded-full" />
                              )}
                            </span>
                            <span className="truncate">{item.title ?? item.kind}</span>
                          </button>
                        );
                      })}
                      {items.length === 0 && (
                        <div className="pl-12 pr-5 py-2.5 text-sm text-muted-foreground flex items-center gap-2">
                          {module.locked && !isPreviewLoading ? (
                            "Preview not available yet."
                          ) : (
                            <><PlayCircle className="size-4" /> Loading...</>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </aside>
      )}

      <div className="flex-1 min-w-0 overflow-y-auto">
        <div className="sticky top-0 z-10">
          <Link
            to="/learn/courses/$courseId"
            params={{ courseId: course.id }}
            search={program ? ({ program } as never) : undefined}
            className="lg:hidden flex items-center gap-2 px-5 py-3.5 text-sm font-semibold text-primary bg-background/95 backdrop-blur border-b border-border"
          >
            <ArrowLeft className="size-4" /> Back to course
          </Link>
          {!sidebarOpen && (
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="hidden lg:flex w-full items-center gap-2 px-6 py-3.5 text-left text-sm font-semibold text-primary bg-background/95 backdrop-blur border-b border-border cursor-pointer hover:bg-foreground/5 transition-colors"
            >
              <PanelLeftOpen className="size-4" /> Show course outline
            </button>
          )}
        </div>
        <div className="px-5 sm:px-8 lg:px-12 pb-5 sm:pb-8 lg:pb-12 pt-5 sm:pt-6 lg:pt-6">
          <div className="max-w-[1040px] mx-auto">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
