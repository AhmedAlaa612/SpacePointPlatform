import { useMemo, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { BookOpen, Eye, Plus, Search, Trash2 } from "lucide-react";
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives";
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common";
import { useToast } from "@/components/ui/toast";
import { BookCover } from "@/components/lms/BookCover";
import {
  adminCreateBookApi,
  adminDeleteBookApi,
  adminListBooksApi,
  adminPublishBookApi,
  adminUnpublishBookApi,
  type AdminBook,
} from "@/api/lms_books";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
    return err.response.data.detail;
  }
  return fallback;
}

function formatPriceLabel(book: AdminBook): string {
  if (book.access_mode === "open") return "Free";
  if (book.access_mode === "invite") return "Invite only";
  const amount = ((book.price_cents ?? 0) / 100).toFixed(2);
  return `${amount} ${book.currency || "AED"}`;
}

const inputCls =
  "w-full h-10 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:border-primary transition-colors";

export default function LmsBooks() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [query, setQuery] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AdminBook | null>(null);
  const [deleteError, setDeleteError] = useState("");

  // Create modal state
  const [title, setTitle] = useState("");
  const [titleAr, setTitleAr] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [authorName, setAuthorName] = useState("");
  const [accessMode, setAccessMode] = useState<"open" | "invite" | "paid">("open");
  const [priceMajor, setPriceMajor] = useState("");
  const [currency, setCurrency] = useState("AED");
  const [accessDays, setAccessDays] = useState("");
  const [createError, setCreateError] = useState("");

  const { data: books = [], isLoading } = useQuery({
    queryKey: ["lms-admin-books"],
    queryFn: adminListBooksApi,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-books"] });

  const createMutation = useMutation({
    mutationFn: () => {
      const priceCents =
        accessMode === "paid" && priceMajor.trim()
          ? Math.round(Number(priceMajor.trim()) * 100)
          : null;
      const parsedDays = accessDays.trim() ? Number(accessDays.trim()) : null;
      return adminCreateBookApi({
        title: title.trim(),
        title_ar: titleAr.trim() || null,
        subtitle: subtitle.trim() || null,
        author_name: authorName.trim() || null,
        access_mode: accessMode,
        price_cents: priceCents,
        currency: (currency.trim() || "AED").toUpperCase(),
        access_days: parsedDays,
      });
    },
    onSuccess: (created) => {
      setCreateOpen(false);
      setTitle("");
      setTitleAr("");
      setSubtitle("");
      setAuthorName("");
      setAccessMode("open");
      setPriceMajor("");
      setCurrency("AED");
      setAccessDays("");
      setCreateError("");
      invalidate();
      toast.success("Book created");
      void navigate({ to: "/lms-authoring/books/$bookId", params: { bookId: created.id } });
    },
    onError: (err) => setCreateError(errorDetail(err, "Failed to create book")),
  });

  const togglePublishMutation = useMutation({
    mutationFn: (book: AdminBook) =>
      book.is_published ? adminUnpublishBookApi(book.id) : adminPublishBookApi(book.id),
    onSuccess: (updated) => {
      invalidate();
      toast.success(updated.is_published ? "Book published" : "Book unpublished");
    },
    onError: (err) => toast.error(errorDetail(err, "Failed to update publish status")),
  });

  const deleteMutation = useMutation({
    mutationFn: (bookId: string) => adminDeleteBookApi(bookId),
    onSuccess: () => {
      setDeleteTarget(null);
      setDeleteError("");
      invalidate();
      toast.success("Book deleted");
    },
    onError: (err) => setDeleteError(errorDetail(err, "Failed to delete book")),
  });

  const handleCreateSubmit = () => {
    if (!title.trim()) {
      setCreateError("Title is required");
      return;
    }
    if (accessMode === "paid") {
      const num = Number(priceMajor.trim());
      if (!priceMajor.trim() || Number.isNaN(num) || num <= 0) {
        setCreateError("Paid books require a price greater than 0");
        return;
      }
    }
    if (accessDays.trim()) {
      const d = Number(accessDays.trim());
      if (!Number.isInteger(d) || d <= 0) {
        setCreateError("Access days must be a positive whole number");
        return;
      }
    }
    setCreateError("");
    createMutation.mutate();
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return books;
    return books.filter(
      (b) =>
        b.title.toLowerCase().includes(q) ||
        (b.title_ar ?? "").toLowerCase().includes(q) ||
        (b.author_name ?? "").toLowerCase().includes(q) ||
        b.slug.toLowerCase().includes(q),
    );
  }, [books, query]);

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
      <PageHeader
        title="Books"
        subtitle="Manage interactive books, bundles, access modes, and learner analytics."
        action={
          <button
            type="button"
            onClick={() => {
              setCreateError("");
              setCreateOpen(true);
            }}
            className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors cursor-pointer"
          >
            <Plus size={16} />
            New book
          </button>
        }
      />

      <div className="mb-5 relative max-w-sm">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search books by title or author"
          className={`${inputCls} pl-9 bg-card`}
        />
      </div>

      {isLoading ? (
        <Spinner />
      ) : filtered.length === 0 ? (
        <div className="border border-border rounded-[10px] bg-card">
          <EmptyState
            icon={<BookOpen size={32} />}
            title={query ? "No matching books" : "No books yet"}
            description={query ? "Try a different search query." : "Create your first interactive book to get started."}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map((book) => (
            <div
              key={book.id}
              className="border border-border rounded-[10px] bg-card p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-4"
            >
              <div className="flex items-start gap-4 min-w-0">
                <Link
                  to="/lms-authoring/books/$bookId"
                  params={{ bookId: book.id }}
                  className="shrink-0 aspect-[3/4] w-14 h-[75px] rounded-[10px] overflow-hidden border border-border bg-muted block"
                >
                  <BookCover
                    title={book.title}
                    coverUrl={book.cover_url}
                    coverPageUrl={book.cover_page_url}
                    compact
                  />
                </Link>

                <div className="flex flex-col gap-1.5 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      to="/lms-authoring/books/$bookId"
                      params={{ bookId: book.id }}
                      className="text-base font-semibold text-foreground hover:text-primary transition-colors"
                    >
                      {book.title}
                    </Link>
                    {book.title_ar && (
                      <span dir="rtl" className="text-sm text-muted-foreground">
                        {book.title_ar}
                      </span>
                    )}
                  </div>

                  {book.author_name && (
                    <p className="text-xs text-muted-foreground">{book.author_name}</p>
                  )}

                  <div className="flex flex-wrap items-center gap-2 mt-0.5">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-[10px] text-xs font-medium border ${
                        book.is_published
                          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                          : "bg-muted text-muted-foreground border-border"
                      }`}
                    >
                      {book.is_published ? "Published" : "Draft"}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-[10px] text-xs font-medium border border-border bg-background text-foreground">
                      {book.bundle_version > 0 ? `v${book.bundle_version}` : "No bundle"}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-[10px] text-xs font-medium border border-border bg-background text-muted-foreground">
                      {formatPriceLabel(book)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between lg:justify-end gap-6">
                <div className="flex items-center gap-5 text-sm">
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Enrolled</p>
                    <p className="font-semibold text-foreground">{book.enrollments_count}</p>
                  </div>
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Readers</p>
                    <p className="font-semibold text-foreground">{book.active_readers_count}</p>
                  </div>
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Avg Progress</p>
                    <p className="font-semibold text-foreground">{book.avg_completion_pct}%</p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    to="/lms-authoring/books/$bookId"
                    params={{ bookId: book.id }}
                    className="inline-flex items-center justify-center h-9 px-3 rounded-[10px] border border-border bg-background text-xs font-medium text-foreground hover:bg-muted transition-colors"
                  >
                    Open
                  </Link>

                  {book.bundle_version > 0 ? (
                    <Link
                      to="/learn/books/$bookId/read"
                      params={{ bookId: book.id }}
                      className="inline-flex items-center gap-1.5 h-9 px-3 rounded-[10px] border border-border bg-background text-xs font-medium text-foreground hover:bg-muted transition-colors"
                    >
                      <Eye size={14} />
                      Preview
                    </Link>
                  ) : (
                    <button
                      type="button"
                      disabled
                      className="inline-flex items-center gap-1.5 h-9 px-3 rounded-[10px] border border-border bg-background text-xs font-medium text-muted-foreground opacity-50 cursor-not-allowed"
                    >
                      <Eye size={14} />
                      Preview
                    </button>
                  )}

                  <button
                    type="button"
                    disabled={
                      togglePublishMutation.isPending || (!book.is_published && book.bundle_version === 0)
                    }
                    onClick={() => togglePublishMutation.mutate(book)}
                    className={`h-9 px-3 rounded-[10px] text-xs font-medium border transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                      book.is_published
                        ? "border-border bg-background text-foreground hover:bg-muted"
                        : "border-primary bg-primary text-primary-foreground hover:bg-primary/90"
                    }`}
                  >
                    {book.is_published ? "Unpublish" : "Publish"}
                  </button>

                  <button
                    type="button"
                    aria-label={`Delete ${book.title}`}
                    onClick={() => {
                      setDeleteError("");
                      setDeleteTarget(book);
                    }}
                    className="inline-flex items-center justify-center w-9 h-9 rounded-[10px] border border-border bg-background text-muted-foreground hover:text-rose-600 hover:border-rose-500/40 transition-colors cursor-pointer"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {createOpen && (
        <Modal title="New book" onClose={() => setCreateOpen(false)}>
          <div className="flex flex-col gap-3">
            <Field label="Title">
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="SatKit Space Systems"
                className={inputCls}
                autoFocus
              />
            </Field>
            <Field label="Arabic Title">
              <input
                type="text"
                dir="rtl"
                value={titleAr}
                onChange={(e) => setTitleAr(e.target.value)}
                placeholder="كتاب أنظمة الفضاء"
                className={inputCls}
              />
            </Field>
            <Field label="Subtitle">
              <input
                type="text"
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                placeholder="Interactive orbital mechanics and CubeSat labs"
                className={inputCls}
              />
            </Field>
            <Field label="Author">
              <input
                type="text"
                value={authorName}
                onChange={(e) => setAuthorName(e.target.value)}
                placeholder="SpacePoint"
                className={inputCls}
              />
            </Field>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Access mode">
                <select
                  value={accessMode}
                  onChange={(e) => setAccessMode(e.target.value as "open" | "invite" | "paid")}
                  className={`${inputCls} cursor-pointer`}
                >
                  <option value="open">Free (Open)</option>
                  <option value="invite">Invite / Program only</option>
                  <option value="paid">Paid</option>
                </select>
              </Field>
              <Field label="Access days (optional)">
                <input
                  type="number"
                  min={1}
                  value={accessDays}
                  onChange={(e) => setAccessDays(e.target.value)}
                  placeholder="Unlimited"
                  className={inputCls}
                />
              </Field>
            </div>

            {accessMode === "paid" && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Price">
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={priceMajor}
                    onChange={(e) => setPriceMajor(e.target.value)}
                    placeholder="99.00"
                    className={inputCls}
                  />
                </Field>
                <Field label="Currency">
                  <input
                    type="text"
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                    placeholder="AED"
                    className={inputCls}
                  />
                </Field>
              </div>
            )}

            {createError && (
              <div className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-[10px] px-3 py-2">
                {createError}
              </div>
            )}

            <ModalActions
              onCancel={() => setCreateOpen(false)}
              onConfirm={handleCreateSubmit}
              loading={createMutation.isPending}
              confirmText="Create book"
            />
          </div>
        </Modal>
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete book"
          description={`Delete "${deleteTarget.title}" and all reader progress and responses?`}
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          error={deleteError || null}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}
    </div>
  );
}
