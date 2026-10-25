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
  // (see the "Back to course" link below). Defaults to true so curriculum is visible.
  const [sidebarOpen, setSidebarOpen] = useState(true);
  // Only used to carry the "opened from a checklist" chain through to the
  // course landing page — same param TaskDrawer/LearnCourse already thread
  // for the completion-celebration "back to your program" nudge.
  const { program, preview } = useSearch({ strict: false }) as { program?: string; preview?: string | boolean };
  const isPreview = Boolean(course.is_preview || preview === "true" || preview === true);

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
    <div className="flex flex-col lg:h-screen">
      {isPreview && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 text-amber-900 dark:text-amber-200 px-4 py-2.5 text-xs font-medium flex items-center justify-between gap-3 shrink-0 z-30">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-amber-500/20 text-amber-900 dark:text-amber-200 border border-amber-500/30">
              Preview Mode
            </span>
            <span>Progress is not recorded in preview mode.</span>
            {course.is_published === false && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-muted text-muted-foreground border border-border">
                Draft
              </span>
            )}
          </div>
          <Link
            to="/lms-authoring/courses/$courseId"
            params={{ courseId: course.id }}
            className="text-primary hover:underline shrink-0 font-semibold"
          >
            Back to Course Editor →
          </Link>
        </div>
      )}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0 overflow-hidden">
        {/* Below `lg` the module list doesn't fit stacked above the content
            the way it does as a fixed-width side column — it just pushed the
            actual lesson off the bottom of the screen. Mobile instead gets a
            "Back to course" link (below) to the landing page's own expandable
            module list (LearnCourse.tsx's ModuleRow) to browse/pick from. */}
        {sidebarOpen && (
          <aside className="hidden lg:block lg:w-[360px] lg:shrink-0 lg:overflow-y-auto border-b lg:border-b-0 lg:border-r border-border/80 dark:border-[#a880ff]/20 bg-background/95 dark:bg-[#05030A]/80 backdrop-blur-md">
            <div className="p-5 sm:p-6 flex items-center justify-between gap-3 border-b border-border/60 dark:border-[#a880ff]/15">
              <div className="min-w-0 flex items-center gap-2">
                <h2 className="font-['Outfit'] text-base sm:text-lg font-bold truncate text-foreground tracking-tight">{course.title}</h2>
                {course.is_published === false && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-muted text-muted-foreground border border-border shrink-0">
                    Draft
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="shrink-0 rounded-lg p-1.5 text-muted-foreground hover:bg-[#a880ff]/10 hover:text-foreground dark:hover:text-white transition-colors cursor-pointer"
                title="Collapse module list"
              >
                <PanelLeftClose className="size-[18px]" />
              </button>
            </div>
          <div className="flex flex-col">
            {course.modules.map((module) => {
              const items = (modulesData[module.module_id] ?? previewData[module.module_id])?.items ?? [];
              const hasItems = (module.total_items ?? (items.length > 0 ? items.length : module.mandatory_total > 0 ? 1 : 0)) > 0;
              const done = hasItems && (module.mandatory_total === 0 || module.mandatory_completed >= module.mandatory_total);
              const isOpen = openModuleId === module.module_id;
              const isPreviewLoading = previewLoadingId === module.module_id;
              return (
                <div key={module.module_id} className="border-t border-border/60 dark:border-[#a880ff]/15">
                  <button
                    onClick={() => toggleModule(module)}
                    className={cn(
                      "w-full flex items-center gap-3.5 px-5 sm:px-6 py-3.5 text-left transition-colors cursor-pointer hover:bg-foreground/5 dark:hover:bg-[#a880ff]/5",
                      isOpen && "bg-foreground/[0.03] dark:bg-[#a880ff]/[0.04]",
                    )}
                  >
                    <span className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold font-['Outfit']",
                      module.locked ? "border border-border dark:border-lms-accent-border/40 text-muted-foreground/60"
                        : done ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/40"
                        : isOpen ? "border border-lms-cta dark:border-lms-accent text-lms-cta dark:text-lms-accent bg-lms-cta-light dark:bg-lms-accent-light"
                        : "border border-border/80 text-muted-foreground",
                    )}>
                      {module.locked ? <Lock className="size-3.5" /> : done ? <CheckCircle2 className="size-3.5" /> : module.position}
                    </span>
                    <span className={cn("flex-1 min-w-0 text-sm truncate font-['Outfit']", module.locked ? "text-muted-foreground/70" : "font-semibold text-foreground")}>
                      {module.title ?? `Module ${module.position}`}
                    </span>
                    <ChevronDown className={cn("size-4 text-muted-foreground shrink-0 transition-transform duration-200", isOpen && "rotate-180")} />
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
                              "w-full flex items-center gap-3 pl-11 pr-5 py-2.5 text-left text-xs sm:text-sm transition-all border-l-2",
                              module.locked ? "cursor-default text-muted-foreground/40 border-transparent"
                                : isSelected ? "cursor-pointer bg-lms-cta-light border-lms-cta dark:border-lms-accent text-foreground dark:text-white font-semibold"
                                : "cursor-pointer text-muted-foreground border-transparent hover:bg-foreground/5 dark:hover:bg-lms-accent/5 hover:text-foreground",
                            )}
                          >
                            <span className="relative shrink-0">
                              <Icon className={cn("size-4", isDone ? "text-emerald-600 dark:text-emerald-400" : isSelected ? "text-lms-cta dark:text-lms-accent" : "text-muted-foreground")} />
                              {isDone && (
                                <CheckCircle2 className="absolute -top-1 -right-1 size-3 text-emerald-600 dark:text-emerald-400 bg-background rounded-full" />
                              )}
                            </span>
                            <span className="truncate">{item.title ?? item.kind}</span>
                          </button>
                        );
                      })}
                      {items.length === 0 && (
                        <div className="pl-11 pr-5 py-2.5 text-xs text-muted-foreground flex items-center gap-2">
                          {module.locked && !isPreviewLoading ? (
                            "Preview not available yet."
                          ) : (
                            <><PlayCircle className="size-3.5" /> Loading...</>
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
            className="lg:hidden flex items-center gap-2 px-5 py-3.5 text-xs sm:text-sm font-semibold text-lms-cta dark:text-lms-accent hover:text-foreground dark:hover:text-white bg-background/95 dark:bg-[#05030A]/95 backdrop-blur border-b border-border/80 dark:border-lms-accent-border/40 transition-colors"
          >
            <ArrowLeft className="size-4" /> Back to course
          </Link>
          {!sidebarOpen && (
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="hidden lg:flex w-full items-center gap-2 px-6 py-3 text-left text-xs sm:text-sm font-semibold text-muted-foreground hover:text-foreground dark:hover:text-white bg-background/95 dark:bg-[#05030A]/95 backdrop-blur border-b border-border/80 dark:border-[#a880ff]/20 cursor-pointer hover:bg-foreground/5 dark:hover:bg-[#a880ff]/5 transition-colors"
            >
              <PanelLeftOpen className="size-4" /> Show course outline
            </button>
          )}
        </div>
        <div className="px-5 sm:px-8 lg:px-12 pb-8 sm:pb-12 pt-6 sm:pt-8">
          <div className="max-w-[1040px] mx-auto">
            {children}
          </div>
        </div>
      </div>
    </div>
  </div>
  );
}
