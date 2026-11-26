import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpen,
  Calculator,
  CheckCircle2,
  ClipboardList,
  GraduationCap,
  List,
  Star,
  X,
} from "lucide-react";
import { apiBaseUrl } from "@/api/client";
import {
  createBookReaderSession,
  submitBookExercise,
  syncBookProgress,
  type BookExercisePayload,
  type BookProgressSyncPayload,
} from "@/api/lms_books";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Button } from "@/components/ui/button";

interface BookBridgeState {
  currentSpread?: string;
  currentChapter?: string;
  currentTitle?: string;
  activeProfile?: string;
  lang?: "en" | "ar";
  theme?: "light" | "dark";
  teacher?: boolean;
  visitedSpreads?: string[];
  stars?: Record<string, number>;
  starsEarned?: number;
  starsPossible?: number;
  completionPct?: number;
  spreadIndex?: number;
  totalSpreads?: number;
  rawState?: Record<string, unknown>;
}

export default function LearnBookReader() {
  const { bookId } = useParams({ strict: false }) as { bookId: string };
  const search = useSearch({ strict: false }) as {
    profile?: string;
    chapter?: string;
    spread?: string;
    program?: string;
    itemId?: string;
    editionId?: string;
  };

  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  const [tocOpen, setTocOpen] = useState(false);
  const [liveState, setLiveState] = useState<BookBridgeState>({});
  const [selectedLang, setSelectedLang] = useState<"en" | "ar">("en");
  const [teacherMode, setTeacherMode] = useState<boolean>(false);

  const initialTheme = useMemo<"light" | "dark">(
    () => (document.documentElement.classList.contains("dark") ? "dark" : "light"),
    [],
  );

  const { data: session, isLoading, error } = useQuery({
    queryKey: [
      "lms-book-reader-session",
      bookId,
      search.profile ?? "",
      search.chapter ?? "",
      search.spread ?? "",
      search.editionId ?? "",
      search.itemId ?? "",
    ],
    queryFn: () =>
      createBookReaderSession(bookId, {
        profile: search.profile,
        chapter: search.chapter,
        spread: search.spread,
        theme: initialTheme,
        edition_id: search.editionId,
        item_id: search.itemId,
      }),
    staleTime: 1000 * 60 * 30,
  });

  useEffect(() => {
    if (!session) return;
    if (session.progress) {
      setLiveState({
        currentSpread: session.progress.current_spread ?? undefined,
        currentChapter: session.progress.current_chapter ?? undefined,
        activeProfile: session.progress.active_profile ?? undefined,
        visitedSpreads: session.progress.visited_spreads,
        stars: session.progress.stars,
        starsEarned: session.progress.stars_earned,
        starsPossible: session.progress.stars_possible,
        completionPct: session.progress.completion_pct,
      });
    }
  }, [session]);

  const sendCmd = useCallback((cmd: string, value?: unknown) => {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    win.postMessage({ type: "SP_BOOK_CMD", cmd, value }, "*");
  }, []);

  // Keep book dark/light theme synced with portal ThemeToggle
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const dark = document.documentElement.classList.contains("dark");
      sendCmd("setTheme", dark ? "dark" : "light");
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, [sendCmd]);

  const allowedOrigin = useMemo(() => {
    try {
      return new URL(apiBaseUrl, window.location.origin).origin;
    } catch {
      return window.location.origin;
    }
  }, []);

  // Receive bridge events (ready, navigation, progress sync, exercise response)
  useEffect(() => {
    if (!session) return;

    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin && e.origin !== allowedOrigin) return;
      if (!e.data || typeof e.data !== "object") return;
      const msg = e.data as { type?: string; bookId?: string; payload?: unknown };
      if (msg.bookId && msg.bookId !== session.book_id) return;

      if (msg.type === "SP_BOOK_READY" || msg.type === "SP_BOOK_NAVIGATED") {
        const snap = (msg.payload || {}) as BookBridgeState;
        setLiveState((prev) => ({ ...prev, ...snap }));
        if (snap.lang === "en" || snap.lang === "ar") setSelectedLang(snap.lang);
        if (typeof snap.teacher === "boolean") setTeacherMode(snap.teacher);
      } else if (msg.type === "SP_BOOK_STATE_SYNC") {
        const snap = (msg.payload || {}) as BookBridgeState;
        setLiveState((prev) => ({ ...prev, ...snap }));
        const syncBody: BookProgressSyncPayload = {
          current_spread: snap.currentSpread ?? null,
          current_chapter: snap.currentChapter ?? null,
          active_profile: snap.activeProfile ?? null,
          visited_spreads: snap.visitedSpreads,
          stars: snap.stars,
          stars_earned: snap.starsEarned,
          stars_possible: snap.starsPossible,
          completion_pct: snap.completionPct,
          raw_state: snap.rawState,
        };
        void syncBookProgress(session.book_id, syncBody).then(() => {
          if (search.program) {
            void queryClient.invalidateQueries({ queryKey: ["lms-checklist", search.program] });
          }
          void queryClient.invalidateQueries({ queryKey: ["lms-book-detail", session.book_id] });
        });
      } else if (msg.type === "SP_BOOK_EXERCISE_RESPONSE") {
        const ex = msg.payload as BookExercisePayload;
        if (!ex || !ex.exercise_key) return;
        void submitBookExercise(session.book_id, ex).then(() => {
          if (search.program) {
            void queryClient.invalidateQueries({ queryKey: ["lms-checklist", search.program] });
          }
        });
      }
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [session, allowedOrigin, queryClient, search.program]);

  const iframeSrc = useMemo(() => {
    if (!session) return "";
    if (session.bundle_url.startsWith("http")) return session.bundle_url;
    return `${apiBaseUrl.replace(/\/$/, "")}${session.bundle_url}`;
  }, [session]);

  const visitedSet = useMemo(() => new Set(liveState.visitedSpreads ?? []), [liveState.visitedSpreads]);

  const filteredChapters = useMemo(() => session?.outline ?? [], [session]);

  if (isLoading) {
    return (
      <div className="h-dvh w-full flex items-center justify-center bg-background text-sm text-muted-foreground">
        Opening book...
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="h-dvh w-full flex flex-col items-center justify-center gap-4 bg-background px-5 text-center">
        <p className="text-sm text-[#E11D48] font-medium">Couldn&apos;t open this book.</p>
        <Link to="/learn/books/$bookId" params={{ bookId }}>
          <Button variant="outline" className="rounded-[10px]">Back to Book</Button>
        </Link>
      </div>
    );
  }

  const bilingual = session.languages.includes("ar") && session.languages.includes("en");
  const pct = liveState.completionPct ?? 0;
  const starsEarned = liveState.starsEarned ?? 0;

  return (
    <div className="w-full h-dvh flex flex-col bg-background overflow-hidden">
      {/* Unified Reader Top Bar */}
      <header className="h-14 shrink-0 border-b border-border bg-card px-3 sm:px-5 flex items-center justify-between gap-2 z-20">
        <div className="flex items-center gap-2.5 min-w-0">
          {search.program ? (
            <Link
              to="/learn/checklists/$assignmentId"
              params={{ assignmentId: search.program }}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline shrink-0"
            >
              <ArrowLeft className="size-4" />
              <span className="hidden sm:inline">Program</span>
            </Link>
          ) : (
            <Link
              to="/learn/books/$bookId"
              params={{ bookId }}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline shrink-0"
            >
              <ArrowLeft className="size-4" />
              <span className="hidden sm:inline">Book</span>
            </Link>
          )}

          <div className="hidden md:flex items-center gap-2 text-sm text-foreground font-semibold">
            <BookOpen className="size-4 text-primary shrink-0" />
            <span>{liveState.currentTitle || session.title}</span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {!session.locked_scope && (session.editions?.length ?? 0) > 0 && (
            <select
              aria-label="Edition"
              value={search.editionId ?? session.edition_id ?? ""}
              onChange={(e) => {
                const nextId = e.target.value;
                void navigate({
                  to: `/learn/books/${bookId}/read`,
                  search: {
                    ...(search.program ? { program: search.program } : {}),
                    ...(nextId ? { editionId: nextId } : {}),
                  } as never,
                  replace: true,
                });
              }}
              className="hidden lg:block h-8 px-2.5 text-xs font-medium rounded-[10px] border border-border bg-background text-foreground focus:outline-none focus:border-primary"
            >
              <option value="">Full Book</option>
              {(session.editions ?? []).map((ed) => (
                <option key={ed.id} value={ed.id}>
                  {selectedLang === "ar" && ed.title_ar ? ed.title_ar : ed.title}
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            onClick={() => setTocOpen(true)}
            className="inline-flex items-center gap-1.5 h-8 px-2.5 sm:px-3 text-xs font-semibold rounded-[10px] border border-border bg-background hover:bg-muted text-foreground cursor-pointer"
          >
            <List className="size-3.5 text-primary" />
            <span>Contents</span>
          </button>

          <button
            type="button"
            onClick={() => sendCmd("openFx")}
            className="hidden sm:inline-flex items-center gap-1.5 h-8 px-3 text-xs font-semibold rounded-[10px] border border-border bg-background hover:bg-muted text-foreground cursor-pointer"
          >
            <Calculator className="size-3.5 text-primary" />
            <span>Formulas</span>
          </button>

          <button
            type="button"
            onClick={() => sendCmd("openMissionFile")}
            className="hidden md:inline-flex items-center gap-1.5 h-8 px-3 text-xs font-semibold rounded-[10px] border border-border bg-background hover:bg-muted text-foreground cursor-pointer"
          >
            <ClipboardList className="size-3.5 text-primary" />
            <span>Notebook</span>
          </button>

          {bilingual && (
            <div className="inline-flex rounded-[10px] border border-border bg-background p-0.5 text-xs">
              <button
                type="button"
                onClick={() => {
                  setSelectedLang("en");
                  sendCmd("setLang", "en");
                }}
                className={`px-2 py-1 rounded-[8px] font-semibold cursor-pointer ${
                  selectedLang === "en" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                }`}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => {
                  setSelectedLang("ar");
                  sendCmd("setLang", "ar");
                }}
                className={`px-2 py-1 rounded-[8px] font-semibold cursor-pointer ${
                  selectedLang === "ar" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                }`}
              >
                عربي
              </button>
            </div>
          )}

          {session.can_teacher && (
            <button
              type="button"
              onClick={() => {
                const next = !teacherMode;
                setTeacherMode(next);
                sendCmd("setTeacher", next);
              }}
              className={`inline-flex items-center gap-1.5 h-8 px-2.5 text-xs font-semibold rounded-[10px] border cursor-pointer ${
                teacherMode
                  ? "border-[#16A34A] bg-[#DCFCE7] text-[#15803D]"
                  : "border-border bg-background text-muted-foreground hover:text-foreground"
              }`}
            >
              <GraduationCap className="size-3.5" />
              <span className="hidden sm:inline">Teacher</span>
            </button>
          )}

          <div className="hidden sm:flex items-center gap-2 px-2.5 h-8 rounded-[10px] bg-primary/10 text-primary text-xs font-semibold">
            <span>{pct}%</span>
            {starsEarned > 0 && (
              <span className="inline-flex items-center gap-1">
                <Star className="size-3 fill-primary" />
                {starsEarned}
              </span>
            )}
          </div>

          <ThemeToggle className="rounded-[10px] p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer" />
        </div>
      </header>

      {/* Book Iframe */}
      <div className="flex-1 min-h-0 w-full relative bg-background">
        <iframe
          ref={iframeRef}
          src={iframeSrc}
          title={session.title}
          className="w-full h-full border-0 block"
          allow="fullscreen"
        />
      </div>

      {/* Slide-over Contents Drawer */}
      {tocOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="fixed inset-0 bg-black/50"
            onClick={() => setTocOpen(false)}
          />
          <aside className="relative z-10 w-full max-w-md h-full bg-card border-l border-border flex flex-col">
            <div className="h-14 px-5 border-b border-border flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2 font-display font-bold text-base">
                <BookOpen className="size-4 text-primary" />
                <span>Contents</span>
              </div>
              <button
                type="button"
                onClick={() => setTocOpen(false)}
                className="p-1.5 rounded-[10px] text-muted-foreground hover:bg-muted cursor-pointer"
                aria-label="Close contents"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-5">
              {filteredChapters.map((ch) => (
                <div key={ch.key} className="space-y-2">
                  <div className="flex items-center gap-2">
                    {ch.code && (
                      <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded-[10px] bg-primary/10 text-primary shrink-0">
                        {ch.code}
                      </span>
                    )}
                    <h3 className="text-sm font-bold text-foreground">
                      {selectedLang === "ar" && ch.title_ar ? ch.title_ar : ch.title_en}
                    </h3>
                  </div>

                  <div className="flex flex-col gap-1 pl-2">
                    {ch.lessons.map((lesson) => {
                      const active = liveState.currentSpread === lesson.spread;
                      const visited = visitedSet.has(lesson.spread);
                      return (
                        <button
                          key={lesson.spread}
                          type="button"
                          onClick={() => {
                            sendCmd("gotoSpread", lesson.spread);
                            setTocOpen(false);
                          }}
                          className={`w-full px-3 py-2 rounded-[10px] text-left text-sm flex items-center justify-between gap-2 transition-colors cursor-pointer ${
                            active
                              ? "bg-primary/10 text-primary font-semibold border border-primary/30"
                              : "hover:bg-muted text-foreground"
                          }`}
                        >
                          <span className="flex items-center gap-2">
                            {visited ? (
                              <CheckCircle2 className="size-3.5 text-[#16A34A] shrink-0" />
                            ) : (
                              <span className="size-1.5 rounded-full bg-muted-foreground/40 shrink-0 ml-1 mr-0.5" />
                            )}
                            <span>
                              {selectedLang === "ar" && lesson.title_ar ? lesson.title_ar : lesson.title_en}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
