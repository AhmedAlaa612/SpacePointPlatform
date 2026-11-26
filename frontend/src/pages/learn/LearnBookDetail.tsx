import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Globe,
  Layers,
  Lock,
  Play,
  Star,
  User as UserIcon,
} from "lucide-react";
import {
  enrollInBook,
  fetchBookDetail,
  fetchPublicBookDetail,
  startBookCheckout,
  type BookChapter,
} from "@/api/lms_books";
import { useAuth } from "@/context/AuthContext";
import { BookCover } from "@/components/lms/BookCover";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
    return err.response.data.detail;
  }
  return fallback;
}

export default function LearnBookDetail() {
  const { bookId } = useParams({ strict: false }) as { bookId: string };
  const search = useSearch({ strict: false }) as { editionId?: string; itemId?: string };
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAuthed = !!user;

  const [selectedEditionId, setSelectedEditionId] = useState<string>(search.editionId ?? "");
  const [expandedKeys, setExpandedKeys] = useState<Record<string, boolean>>({});
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState("");

  const { data: book, isLoading, error } = useQuery({
    queryKey: [isAuthed ? "lms-book-detail" : "lms-public-book-detail", bookId, search.editionId ?? "", search.itemId ?? ""],
    queryFn: () =>
      isAuthed
        ? fetchBookDetail(bookId, { edition_id: search.editionId, item_id: search.itemId })
        : fetchPublicBookDetail(bookId),
  });

  const activeEditionId = book?.locked_scope
    ? (book.edition_id ?? "")
    : (selectedEditionId || search.editionId || "");
  const visitedSet = useMemo(() => new Set(book?.progress?.visited_spreads ?? []), [book]);

  const groupedOutline = useMemo(() => {
    if (!book?.outline) return [];
    const activeEdObj = !book.locked_scope && activeEditionId
      ? (book.editions ?? []).find((e) => e.id === activeEditionId)
      : undefined;
    const allowedGroups = activeEdObj?.chapter_keys?.length ? new Set(activeEdObj.chapter_keys) : null;
    const filtered = allowedGroups
      ? book.outline.filter((ch) => allowedGroups.has(ch.key))
      : book.outline;

    const groups: { part: string; chapters: BookChapter[] }[] = [];
    for (const ch of filtered) {
      const partName = ch.part || "Chapters";
      let bucket = groups.find((g) => g.part === partName);
      if (!bucket) {
        bucket = { part: partName, chapters: [] };
        groups.push(bucket);
      }
      bucket.chapters.push(ch);
    }
    return groups;
  }, [book, activeEditionId]);

  const toggleChapter = (key: string) => {
    setExpandedKeys((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const openReader = (opts?: { chapter?: string; spread?: string }) => {
    if (!book) return;
    const effEditionId = book.locked_scope
      ? (book.edition_id || search.editionId)
      : (activeEditionId || undefined);
    void navigate({
      to: `/learn/books/${book.id}/read`,
      search: {
        ...(effEditionId ? { editionId: effEditionId } : {}),
        ...(search.itemId ? { itemId: search.itemId } : {}),
        ...(opts?.chapter ? { chapter: opts.chapter } : {}),
        ...(opts?.spread ? { spread: opts.spread } : {}),
      } as never,
    });
  };

  const canRead = Boolean(book && (book.enrolled || book.is_preview));
  const isPaid = Boolean(book && book.access_mode === "paid" && book.price_cents && book.price_cents > 0);

  const handlePrimaryCta = async () => {
    if (!book) return;
    if (!isAuthed) {
      void navigate({ to: "/learn/login" });
      return;
    }
    setActionError("");
    if (canRead) {
      openReader();
      return;
    }
    setActionPending(true);
    try {
      if (isPaid) {
        const { checkout_url } = await startBookCheckout(book.id);
        window.location.href = checkout_url;
        return;
      }
      await enrollInBook(book.id);
      await queryClient.invalidateQueries({ queryKey: ["lms-book-detail", bookId] });
      openReader();
    } catch (err) {
      setActionError(errorDetail(err, "Unable to open this book right now."));
      setActionPending(false);
    }
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1180px] px-5 py-10">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }
  if (error || !book) {
    return (
      <div className="mx-auto max-w-[1180px] px-5 py-10 space-y-4">
        <p className="text-sm text-destructive">Couldn&apos;t load this book.</p>
        <Link to="/learn/books" className="text-sm font-semibold text-primary hover:underline">
          Back to Books
        </Link>
      </div>
    );
  }

  const pct = book.progress?.completion_pct ?? 0;
  const starsEarned = book.progress?.stars_earned ?? 0;
  const starsPossible = book.progress?.stars_possible ?? 0;

  return (
    <div className="mx-auto max-w-[1180px] px-5 sm:px-8 lg:px-10 py-8 sm:py-10 flex flex-col gap-8">
      <div className="flex items-center gap-2 text-sm text-muted-foreground flex-wrap">
        <Link to="/learn/books" className="text-primary hover:opacity-80 font-medium">
          Books
        </Link>
        <ChevronRight className="size-3.5 shrink-0" />
        <span className="text-foreground font-medium">{book.title}</span>
      </div>

      <div className="grid lg:grid-cols-[1fr_360px] gap-10 items-start">
        <div className="flex flex-col gap-8 min-w-0">
          {/* Hero block */}
          <div className="flex flex-col sm:flex-row gap-6 items-start">
            <div className="w-44 sm:w-48 aspect-[3/4] shrink-0 rounded-[10px] overflow-hidden border border-border bg-[#18181B]">
              <BookCover
                title={book.title}
                coverUrl={book.cover_url}
                coverPageUrl={book.cover_page_url}
                chapterCount={book.outline.length}
                languages={book.languages}
              />
            </div>

            <div className="flex flex-col gap-3 min-w-0 flex-1">
              <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight leading-tight text-foreground">
                {book.title}
              </h1>
              {book.description && (
                <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">{book.description}</p>
              )}

              <div className="flex flex-wrap items-center gap-4 pt-2 text-sm text-muted-foreground">
                {book.author_name && (
                  <span className="inline-flex items-center gap-1.5">
                    <UserIcon className="size-4 text-primary" />
                    {book.author_name}
                  </span>
                )}
                <span className="inline-flex items-center gap-1.5">
                  <Layers className="size-4 text-primary" />
                  {book.outline.length} chapters
                </span>
                <span className="inline-flex items-center gap-1.5 uppercase">
                  <Globe className="size-4 text-primary" />
                  {book.languages.join(" / ")}
                </span>
              </div>
            </div>
          </div>

          {/* Edition selector (only for full-access readers; strictly scoped students see only their assigned slice) */}
          {!book.locked_scope && (book.editions?.length ?? 0) > 0 && (
            <div className="flex flex-col gap-2">
              <label className="text-sm font-semibold text-foreground">Edition</label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setSelectedEditionId("")}
                  className={`px-3.5 py-2 text-sm font-medium rounded-[10px] border transition-colors cursor-pointer ${
                    !activeEditionId
                      ? "border-primary bg-primary/10 text-primary font-semibold"
                      : "border-border bg-card text-foreground hover:bg-muted"
                  }`}
                >
                  Full Book
                </button>
                {(book.editions ?? []).map((ed) => {
                  const active = ed.id === activeEditionId;
                  return (
                    <button
                      key={ed.id}
                      type="button"
                      onClick={() => setSelectedEditionId(ed.id)}
                      className={`px-3.5 py-2 text-sm font-medium rounded-[10px] border transition-colors cursor-pointer ${
                        active
                          ? "border-primary bg-primary/10 text-primary font-semibold"
                          : "border-border bg-card text-foreground hover:bg-muted"
                      }`}
                    >
                      {ed.title}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Book Outline */}
          <div className="flex flex-col gap-4">
            <h2 className="font-display text-xl sm:text-2xl font-bold tracking-tight">Outline</h2>
            {groupedOutline.length === 0 ? (
              <p className="text-sm text-muted-foreground">Outline will appear once the book bundle is uploaded.</p>
            ) : (
              <div className="flex flex-col gap-6">
                {groupedOutline.map((group) => (
                  <div key={group.part} className="flex flex-col gap-2.5">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                      {group.part}
                    </h3>
                    <div className="flex flex-col gap-2">
                      {group.chapters.map((ch) => {
                        const isOpen = Boolean(expandedKeys[ch.key]);
                        const visitedInCh = ch.lessons.filter((l) => visitedSet.has(l.spread)).length;
                        return (
                          <div
                            key={ch.key}
                            className="rounded-[10px] border border-border bg-card overflow-hidden"
                          >
                            <button
                              type="button"
                              onClick={() => toggleChapter(ch.key)}
                              className="w-full px-4 py-3.5 flex items-center justify-between gap-4 text-left hover:bg-muted/50 transition-colors cursor-pointer"
                            >
                              <div className="flex items-center gap-3 min-w-0">
                                {ch.code && (
                                  <span className="text-xs font-mono font-semibold px-2 py-1 rounded-[10px] bg-primary/10 text-primary shrink-0">
                                    {ch.code}
                                  </span>
                                )}
                                <span className="font-semibold text-sm sm:text-base text-foreground">
                                  {ch.title_en}
                                </span>
                              </div>
                              <div className="flex items-center gap-3 shrink-0 text-xs text-muted-foreground">
                                {canRead && ch.lessons.length > 0 && (
                                  <span>
                                    {visitedInCh}/{ch.lessons.length}
                                  </span>
                                )}
                                {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                              </div>
                            </button>

                            {isOpen && ch.lessons.length > 0 && (
                              <div className="border-t border-border divide-y divide-border bg-background">
                                {ch.lessons.map((lesson) => {
                                  const visited = visitedSet.has(lesson.spread);
                                  return (
                                    <button
                                      key={lesson.spread}
                                      type="button"
                                      disabled={!canRead}
                                      onClick={() => openReader({ spread: lesson.spread })}
                                      className={`w-full px-4 py-2.5 flex items-center justify-between gap-3 text-left text-sm ${
                                        canRead
                                          ? "hover:bg-primary/5 cursor-pointer text-foreground"
                                          : "text-muted-foreground cursor-default"
                                      }`}
                                    >
                                      <span className="flex items-center gap-2.5">
                                        {visited ? (
                                          <CheckCircle2 className="size-4 text-[#16A34A] shrink-0" />
                                        ) : (
                                          <BookOpen className="size-4 text-muted-foreground shrink-0" />
                                        )}
                                        <span>{lesson.title_en}</span>
                                      </span>
                                      {canRead && (
                                        <span className="text-xs font-semibold text-primary shrink-0">
                                          Open
                                        </span>
                                      )}
                                    </button>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sticky Action Card */}
        <Card className="p-6 rounded-[10px] border border-border bg-card lg:sticky lg:top-8 flex flex-col gap-5">
          {canRead ? (
            <>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-foreground">Your progress</span>
                  <span className="text-sm font-bold text-primary">{pct}%</span>
                </div>
                <div className="h-2.5 w-full rounded-[10px] bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-[10px]"
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
                {starsPossible > 0 && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground pt-1">
                    <Star className="size-4 text-primary fill-primary" />
                    <span>
                      <strong className="text-foreground">{starsEarned}</strong> / {starsPossible} stars earned
                    </span>
                  </div>
                )}
              </div>

              <Button
                type="button"
                size="lg"
                disabled={book.bundle_version <= 0}
                onClick={() => void handlePrimaryCta()}
                className="w-full rounded-[10px] gap-2"
              >
                <Play className="size-4" />
                {book.bundle_version <= 0
                  ? "Coming soon"
                  : pct > 0
                    ? "Continue reading"
                    : "Start reading"}
              </Button>
            </>
          ) : book.access_mode === "invite" ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Lock className="size-4 text-primary" />
                <span>Program or invite access</span>
              </div>
              {!isAuthed && (
                <Button
                  type="button"
                  onClick={() => void navigate({ to: "/learn/login" })}
                  className="w-full rounded-[10px]"
                >
                  Log in
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-baseline justify-between">
                <span className="text-2xl font-display font-bold text-foreground">
                  {isPaid ? formatPrice(book.price_cents!, book.currency) : "Free"}
                </span>
                {book.access_days && (
                  <span className="text-xs text-muted-foreground">{book.access_days} days access</span>
                )}
              </div>

              <Button
                type="button"
                size="lg"
                disabled={actionPending || book.bundle_version <= 0}
                onClick={() => void handlePrimaryCta()}
                className="w-full rounded-[10px] gap-2"
              >
                <BookOpen className="size-4" />
                {book.bundle_version <= 0
                  ? "Coming soon"
                  : !isAuthed
                    ? isPaid
                      ? "Log in to buy"
                      : "Log in to read"
                    : actionPending
                      ? "Opening..."
                      : isPaid
                        ? "Buy book"
                        : "Read book"}
              </Button>
            </div>
          )}

          {actionError && (
            <p className="text-sm text-[#E11D48] font-medium">{actionError}</p>
          )}
        </Card>
      </div>
    </div>
  );
}
