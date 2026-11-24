import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  ArrowLeft,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Download,
  Eye,
  FileArchive,
  ImagePlus,
  Trash2,
} from "lucide-react";
import { EmptyState, Spinner } from "@/components/ui/primitives";
import { ConfirmDialog, Field } from "@/pages/admin/components/common";
import { useToast } from "@/components/ui/toast";
import { getCohortsApi } from "@/api/sessions/cohorts";
import { BookCover } from "@/components/lms/BookCover";
import { AssignPanel } from "./components/AssignPanel";
import {
  adminBulkGrantBookEnrollmentApi,
  adminExportBookCsvApi,
  adminGetBookAnalyticsApi,
  adminGetBookApi,
  adminGrantBookEnrollmentApi,
  adminListBookEnrollmentsApi,
  adminPublishBookApi,
  adminRevokeBookEnrollmentApi,
  adminUnpublishBookApi,
  adminUpdateBookApi,
  adminUploadBookBundleApi,
  adminUploadBookCoverApi,
  type BookEnrollmentRow,
} from "@/api/lms_books";

type BookTab = "details" | "bundle" | "enrollments" | "analytics";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
    return err.response.data.detail;
  }
  return fallback;
}

function formatBytes(bytes: number | null): string {
  if (bytes == null || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

const inputCls =
  "w-full h-10 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:border-primary transition-colors";
const textareaCls =
  "w-full p-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:border-primary transition-colors min-h-[110px]";

export default function LmsBookDetail() {
  const { bookId } = useParams({ strict: false }) as { bookId: string };
  const queryClient = useQueryClient();
  const toast = useToast();

  const coverInputRef = useRef<HTMLInputElement>(null);
  const bundleInputRef = useRef<HTMLInputElement>(null);

  const [tab, setTab] = useState<BookTab>("details");
  const [expandedChapters, setExpandedChapters] = useState<Record<string, boolean>>({});
  const [cohortId, setCohortId] = useState("");
  const [bulkResult, setBulkResult] = useState<{ granted: number; already_enrolled: number } | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<BookEnrollmentRow | null>(null);
  const [revokeError, setRevokeError] = useState("");
  const [exporting, setExporting] = useState(false);

  // Details form state
  const [title, setTitle] = useState("");
  const [titleAr, setTitleAr] = useState("");
  const [slug, setSlug] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [authorName, setAuthorName] = useState("");
  const [description, setDescription] = useState("");
  const [languagesText, setLanguagesText] = useState("en");
  const [defaultProfile, setDefaultProfile] = useState("all");
  const [accessMode, setAccessMode] = useState<"open" | "invite" | "paid">("open");
  const [priceMajor, setPriceMajor] = useState("");
  const [currency, setCurrency] = useState("AED");
  const [accessDays, setAccessDays] = useState("");
  const [formError, setFormError] = useState("");

  const { data: book, isLoading } = useQuery({
    queryKey: ["lms-admin-book", bookId],
    queryFn: () => adminGetBookApi(bookId),
  });

  useEffect(() => {
    if (!book) return;
    setTitle(book.title);
    setTitleAr(book.title_ar ?? "");
    setSlug(book.slug);
    setSubtitle(book.subtitle ?? "");
    setAuthorName(book.author_name ?? "");
    setDescription(book.description ?? "");
    setLanguagesText((book.languages?.length ? book.languages : ["en"]).join(", "));
    setDefaultProfile(book.default_profile || "all");
    setAccessMode(book.access_mode);
    setPriceMajor(book.price_cents != null ? (book.price_cents / 100).toFixed(2) : "");
    setCurrency(book.currency || "AED");
    setAccessDays(book.access_days != null ? String(book.access_days) : "");
  }, [book]);

  const { data: enrollments = [], isLoading: enrollmentsLoading } = useQuery({
    queryKey: ["lms-admin-book-enrollments", bookId],
    queryFn: () => adminListBookEnrollmentsApi(bookId),
    enabled: tab === "enrollments",
  });

  const { data: cohorts = [] } = useQuery({
    queryKey: ["sessions-cohorts-all"],
    queryFn: () => getCohortsApi(),
    enabled: tab === "analytics",
  });

  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ["lms-admin-book-analytics", bookId, cohortId],
    queryFn: () => adminGetBookAnalyticsApi(bookId, cohortId || undefined),
    enabled: tab === "analytics",
  });

  const invalidateBook = () => {
    void queryClient.invalidateQueries({ queryKey: ["lms-admin-book", bookId] });
    void queryClient.invalidateQueries({ queryKey: ["lms-admin-books"] });
  };

  const updateMutation = useMutation({
    mutationFn: () => {
      const langs = languagesText
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean);
      const priceCents =
        accessMode === "paid" && priceMajor.trim()
          ? Math.round(Number(priceMajor.trim()) * 100)
          : null;
      const parsedDays = accessDays.trim() ? Number(accessDays.trim()) : null;
      return adminUpdateBookApi(bookId, {
        title: title.trim(),
        title_ar: titleAr.trim() || null,
        slug: slug.trim() || undefined,
        subtitle: subtitle.trim() || null,
        author_name: authorName.trim() || null,
        description: description.trim() || null,
        languages: langs.length > 0 ? langs : ["en"],
        default_profile: defaultProfile || "all",
        access_mode: accessMode,
        price_cents: priceCents,
        currency: (currency.trim() || "AED").toUpperCase(),
        access_days: parsedDays,
      });
    },
    onSuccess: () => {
      setFormError("");
      invalidateBook();
      toast.success("Book details saved");
    },
    onError: (err) => setFormError(errorDetail(err, "Failed to update book")),
  });

  const handleSaveDetails = () => {
    if (!title.trim()) {
      setFormError("Title is required");
      return;
    }
    if (accessMode === "paid") {
      const n = Number(priceMajor.trim());
      if (!priceMajor.trim() || Number.isNaN(n) || n <= 0) {
        setFormError("Paid books require a positive price");
        return;
      }
    }
    if (accessDays.trim()) {
      const d = Number(accessDays.trim());
      if (!Number.isInteger(d) || d <= 0) {
        setFormError("Access days must be a positive whole number");
        return;
      }
    }
    setFormError("");
    updateMutation.mutate();
  };

  const togglePublishMutation = useMutation({
    mutationFn: () => (book?.is_published ? adminUnpublishBookApi(bookId) : adminPublishBookApi(bookId)),
    onSuccess: (updated) => {
      invalidateBook();
      toast.success(updated.is_published ? "Book published" : "Book unpublished");
    },
    onError: (err) => toast.error(errorDetail(err, "Failed to change publish status")),
  });

  const coverMutation = useMutation({
    mutationFn: (file: File) => adminUploadBookCoverApi(bookId, file),
    onSuccess: () => {
      invalidateBook();
      toast.success("Cover uploaded");
    },
    onError: (err) => toast.error(errorDetail(err, "Failed to upload cover")),
  });

  const bundleMutation = useMutation({
    mutationFn: (file: File) => adminUploadBookBundleApi(bookId, file),
    onSuccess: (res) => {
      invalidateBook();
      toast.success(
        `Uploaded v${res.bundle_version} (${res.files_uploaded} files, ${res.chapters_detected} chapters)`,
      );
    },
    onError: (err) => toast.error(errorDetail(err, "Failed to upload bundle")),
  });

  const grantMutation = useMutation({
    mutationFn: (userId: string) => adminGrantBookEnrollmentApi(bookId, { user_id: userId }),
    onSuccess: () => {
      invalidateBook();
      void queryClient.invalidateQueries({ queryKey: ["lms-admin-book-enrollments", bookId] });
      toast.success("Access granted");
    },
    onError: (err) => toast.error(errorDetail(err, "Failed to grant access")),
  });

  const bulkGrantMutation = useMutation({
    mutationFn: (role: string) => adminBulkGrantBookEnrollmentApi(bookId, role),
    onSuccess: (res) => {
      setBulkResult(res);
      invalidateBook();
      void queryClient.invalidateQueries({ queryKey: ["lms-admin-book-enrollments", bookId] });
      toast.success(`Assigned ${res.granted} user${res.granted === 1 ? "" : "s"}`);
    },
    onError: (err) => toast.error(errorDetail(err, "Failed to bulk grant access")),
  });

  const revokeMutation = useMutation({
    mutationFn: (userId: string) => adminRevokeBookEnrollmentApi(bookId, userId),
    onSuccess: () => {
      setRevokeTarget(null);
      setRevokeError("");
      invalidateBook();
      void queryClient.invalidateQueries({ queryKey: ["lms-admin-book-enrollments", bookId] });
      toast.success("Access revoked");
    },
    onError: (err) => setRevokeError(errorDetail(err, "Failed to revoke access")),
  });

  const handleExportCsv = async () => {
    if (!book || exporting) return;
    setExporting(true);
    try {
      const blob = await adminExportBookCsvApi(bookId, cohortId || undefined);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${book.slug || "book"}-responses.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(errorDetail(err, "Failed to export CSV"));
    } finally {
      setExporting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <Spinner />
      </div>
    );
  }

  if (!book) {
    return (
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <EmptyState icon={<BookOpen size={32} />} title="Book not found" />
      </div>
    );
  }

  const tabs: { id: BookTab; label: string }[] = [
    { id: "details", label: "Details & Access" },
    { id: "bundle", label: "Bundle & Outline" },
    { id: "enrollments", label: "Access & Enrollments" },
    { id: "analytics", label: "Analytics & Responses" },
  ];

  const profileOptions = book.profiles.length > 0
    ? book.profiles
    : [{ key: "all", label_en: "Full Book", label_ar: null, subtitle_en: null, subtitle_ar: null, default_lang: null, groups: [] }];

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
      <div className="mb-4">
        <Link
          to="/lms-authoring/books"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft size={15} />
          Back to Books
        </Link>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              {book.title}
            </h1>
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-[10px] text-xs font-medium border ${
                book.is_published
                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                  : "bg-muted text-muted-foreground border-border"
              }`}
            >
              {book.is_published ? "Published" : "Draft"}
            </span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-[10px] text-xs font-medium border border-border bg-card text-foreground">
              {book.bundle_version > 0 ? `v${book.bundle_version}` : "No bundle"}
            </span>
          </div>
          {book.subtitle && <p className="text-sm text-muted-foreground">{book.subtitle}</p>}
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {book.bundle_version > 0 ? (
            <Link
              to="/learn/books/$bookId/read"
              params={{ bookId: book.id }}
              className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] border border-border bg-card text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              <Eye size={15} />
              Preview Reader
            </Link>
          ) : (
            <button
              type="button"
              disabled
              className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] border border-border bg-card text-sm font-medium text-muted-foreground opacity-50 cursor-not-allowed"
            >
              <Eye size={15} />
              Preview Reader
            </button>
          )}
          <button
            type="button"
            disabled={
              togglePublishMutation.isPending || (!book.is_published && book.bundle_version === 0)
            }
            onClick={() => togglePublishMutation.mutate()}
            className={`h-10 px-4 rounded-[10px] text-sm font-medium border transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
              book.is_published
                ? "border-border bg-card text-foreground hover:bg-muted"
                : "border-primary bg-primary text-primary-foreground hover:bg-primary/90"
            }`}
          >
            {book.is_published ? "Unpublish" : "Publish"}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border pb-3 mb-6">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`h-9 px-4 rounded-[10px] text-sm font-medium transition-colors cursor-pointer ${
              tab === t.id
                ? "bg-primary text-primary-foreground"
                : "bg-card border border-border text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab 1: Details & Access */}
      {tab === "details" && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_240px] gap-8 items-start">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field label="Title">
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="Arabic Title">
                <input
                  type="text"
                  dir="rtl"
                  value={titleAr}
                  onChange={(e) => setTitleAr(e.target.value)}
                  className={inputCls}
                />
              </Field>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field label="Slug">
                <input
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="Author">
                <input
                  type="text"
                  value={authorName}
                  onChange={(e) => setAuthorName(e.target.value)}
                  className={inputCls}
                />
              </Field>
            </div>

            <Field label="Subtitle">
              <input
                type="text"
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                className={inputCls}
              />
            </Field>

            <Field label="Description">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className={textareaCls}
              />
            </Field>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field label="Languages (comma separated)">
                <input
                  type="text"
                  value={languagesText}
                  onChange={(e) => setLanguagesText(e.target.value)}
                  placeholder="en, ar"
                  className={inputCls}
                />
              </Field>
              <Field label="Default Edition / Track">
                <select
                  value={defaultProfile}
                  onChange={(e) => setDefaultProfile(e.target.value)}
                  className={`${inputCls} cursor-pointer`}
                >
                  {profileOptions.map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.label_en}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
              <Field label="Currency">
                <input
                  type="text"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className={inputCls}
                />
              </Field>
            </div>

            {accessMode === "paid" && (
              <div className="max-w-xs">
                <Field label={`Price (${currency || "AED"})`}>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={priceMajor}
                    onChange={(e) => setPriceMajor(e.target.value)}
                    className={inputCls}
                  />
                </Field>
              </div>
            )}

            {formError && (
              <div className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-[10px] px-3 py-2">
                {formError}
              </div>
            )}

            <div className="pt-2">
              <button
                type="button"
                disabled={updateMutation.isPending}
                onClick={handleSaveDetails}
                className="h-10 px-5 rounded-[10px] bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50"
              >
                {updateMutation.isPending ? "Saving..." : "Save changes"}
              </button>
            </div>
          </div>

          {/* Cover Column */}
          <div className="flex flex-col gap-3">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
              Cover
            </span>
            <div className="aspect-[3/4] w-full max-w-[200px] rounded-[10px] border border-border bg-muted overflow-hidden">
              <BookCover
                title={book.title}
                coverUrl={book.cover_url}
                coverPageUrl={book.cover_page_url}
                chapterCount={book.outline.length}
                languages={book.languages}
              />
            </div>
            <input
              ref={coverInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/svg+xml"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) coverMutation.mutate(file);
              }}
            />
            <button
              type="button"
              disabled={coverMutation.isPending}
              onClick={() => coverInputRef.current?.click()}
              className="inline-flex items-center justify-center gap-2 max-w-[200px] h-10 px-4 rounded-[10px] border border-border bg-card text-sm font-medium text-foreground hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
            >
              <ImagePlus size={15} />
              {coverMutation.isPending ? "Uploading..." : "Upload cover"}
            </button>
          </div>
        </div>
      )}

      {/* Tab 2: Bundle & Outline */}
      {tab === "bundle" && (
        <div className="flex flex-col gap-6">
          <div className="border border-border rounded-[10px] bg-card p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold text-foreground">Interactive Bundle</h2>
                <span className="inline-flex items-center px-2 py-0.5 rounded-[10px] text-xs font-medium border border-border bg-background text-foreground">
                  {book.bundle_version > 0 ? `v${book.bundle_version}` : "None uploaded"}
                </span>
              </div>
              {book.bundle_version > 0 && (
                <div className="flex flex-wrap gap-4 text-xs text-muted-foreground mt-1">
                  <span>Entry: {book.bundle_entry}</span>
                  <span>Storage: {book.bundle_storage_backend || "default"}</span>
                  <span>Size: {formatBytes(book.bundle_size_bytes)}</span>
                </div>
              )}
            </div>

            <div>
              <input
                ref={bundleInputRef}
                type="file"
                accept=".zip,application/zip"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) bundleMutation.mutate(file);
                }}
              />
              <button
                type="button"
                disabled={bundleMutation.isPending}
                onClick={() => bundleInputRef.current?.click()}
                className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50"
              >
                <FileArchive size={15} />
                {bundleMutation.isPending ? "Uploading zip..." : "Upload .zip bundle"}
              </button>
            </div>
          </div>

          {/* Editions / Profiles */}
          <div className="border border-border rounded-[10px] bg-card overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">Editions & Tracks</h3>
              <span className="text-xs text-muted-foreground">{book.profiles.length}</span>
            </div>
            {book.profiles.length === 0 ? (
              <div className="p-6 text-sm text-muted-foreground">No editions parsed from bundle manifest yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-border text-xs uppercase text-muted-foreground bg-muted/40">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">Key</th>
                      <th className="px-4 py-2.5 font-medium">Label (EN)</th>
                      <th className="px-4 py-2.5 font-medium">Label (AR)</th>
                      <th className="px-4 py-2.5 font-medium">Default Lang</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {book.profiles.map((p) => (
                      <tr key={p.key}>
                        <td className="px-4 py-2.5 font-mono text-xs">{p.key}</td>
                        <td className="px-4 py-2.5">{p.label_en}</td>
                        <td className="px-4 py-2.5" dir="rtl">{p.label_ar || "-"}</td>
                        <td className="px-4 py-2.5 uppercase text-xs text-muted-foreground">
                          {p.default_lang || "en"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Outline */}
          <div className="border border-border rounded-[10px] bg-card overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">Chapters & Outline</h3>
              <span className="text-xs text-muted-foreground">{book.outline.length} chapters</span>
            </div>
            {book.outline.length === 0 ? (
              <div className="p-6 text-sm text-muted-foreground">Upload a zip bundle containing book.json or index.html to extract chapters.</div>
            ) : (
              <div className="divide-y divide-border">
                {book.outline.map((ch) => {
                  const open = !!expandedChapters[ch.key];
                  return (
                    <div key={ch.key}>
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedChapters((prev) => ({ ...prev, [ch.key]: !prev[ch.key] }))
                        }
                        className="w-full px-4 py-3 flex items-center justify-between gap-4 text-left hover:bg-muted/40 transition-colors cursor-pointer"
                      >
                        <div className="flex items-center gap-2.5">
                          {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                          {ch.code && (
                            <span className="px-2 py-0.5 rounded-[10px] border border-border bg-background text-xs font-mono">
                              {ch.code}
                            </span>
                          )}
                          <span className="text-sm font-medium text-foreground">{ch.title_en}</span>
                          {ch.title_ar && (
                            <span dir="rtl" className="text-sm text-muted-foreground">
                              {ch.title_ar}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 shrink-0 text-xs text-muted-foreground">
                          {ch.part && <span>{ch.part}</span>}
                          <span>{ch.lessons.length} lessons</span>
                        </div>
                      </button>
                      {open && ch.lessons.length > 0 && (
                        <div className="px-10 pb-3 pt-1 flex flex-col gap-1.5 bg-muted/20">
                          {ch.lessons.map((lesson) => (
                            <div
                              key={lesson.spread}
                              className="flex flex-wrap items-center justify-between gap-2 text-xs py-1 border-b border-border/50 last:border-b-0"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="font-mono text-muted-foreground">{lesson.spread}</span>
                                <span className="text-foreground">{lesson.title_en}</span>
                              </div>
                              {lesson.title_ar && (
                                <span dir="rtl" className="text-muted-foreground">
                                  {lesson.title_ar}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Access & Enrollments */}
      {tab === "enrollments" && (
        <div className="flex flex-col gap-5">
          <div className="max-w-2xl">
            <AssignPanel
              includeStudents
              hideRoster
              roster={enrollments.map((e) => ({
                id: e.id,
                userId: e.user_id,
                name: e.full_name,
                email: e.email,
                status: e.status,
              }))}
              isLoading={enrollmentsLoading}
              onGrant={(userId) => grantMutation.mutate(userId)}
              onBulkGrant={(role) => bulkGrantMutation.mutate(role)}
              onRevoke={(enrollmentId) => {
                const target = enrollments.find((e) => e.id === enrollmentId);
                if (target) revokeMutation.mutate(target.user_id);
              }}
              grantPending={grantMutation.isPending}
              bulkPending={bulkGrantMutation.isPending}
              revokePending={revokeMutation.isPending}
              bulkResult={bulkResult}
            />
          </div>

          <div className="border border-border rounded-[10px] bg-card overflow-hidden">
            {enrollmentsLoading ? (
              <Spinner />
            ) : enrollments.length === 0 ? (
              <EmptyState title="No enrollments yet" description="Learners with open, paid, invite, or manual access appear here." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-border text-xs uppercase text-muted-foreground bg-muted/40">
                    <tr>
                      <th className="px-4 py-3 font-medium">Student</th>
                      <th className="px-4 py-3 font-medium">Source</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium">Completion</th>
                      <th className="px-4 py-3 font-medium">Stars</th>
                      <th className="px-4 py-3 font-medium">Last read</th>
                      <th className="px-4 py-3 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {enrollments.map((row) => (
                      <tr key={row.id}>
                        <td className="px-4 py-3">
                          <div className="font-medium text-foreground">{row.full_name}</div>
                          <div className="text-xs text-muted-foreground">{row.email}</div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-[10px] text-xs font-medium border border-border bg-background text-foreground">
                            {row.source}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-[10px] text-xs font-medium border ${
                              row.status === "active"
                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                                : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30"
                            }`}
                          >
                            {row.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">{row.completion_pct}%</td>
                        <td className="px-4 py-3">{row.stars_earned}</td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(row.last_read_at)}</td>
                        <td className="px-4 py-3 text-right">
                          {row.status === "active" && (
                            <button
                              type="button"
                              onClick={() => {
                                setRevokeError("");
                                setRevokeTarget(row);
                              }}
                              className="inline-flex items-center gap-1 h-8 px-2.5 rounded-[10px] border border-border bg-background text-xs font-medium text-muted-foreground hover:text-rose-600 hover:border-rose-500/40 transition-colors cursor-pointer"
                            >
                              <Trash2 size={12} />
                              Revoke
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 4: Analytics & Responses */}
      {tab === "analytics" && (
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={cohortId}
              onChange={(e) => setCohortId(e.target.value)}
              className="w-auto min-w-[220px] max-w-xs h-10 px-3 rounded-[10px] border border-border bg-card text-sm text-foreground cursor-pointer focus:outline-none focus:border-primary"
            >
              <option value="">All learners</option>
              {cohorts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>

            <button
              type="button"
              disabled={exporting}
              onClick={() => void handleExportCsv()}
              className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] border border-border bg-card text-sm font-medium text-foreground hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
            >
              <Download size={15} />
              {exporting ? "Exporting..." : "Export CSV"}
            </button>
          </div>

          {analyticsLoading ? (
            <Spinner />
          ) : !analytics ? (
            <EmptyState title="Analytics unavailable" />
          ) : (
            <>
              {/* 4 Flat KPI Boxes */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="border border-border rounded-[10px] bg-card p-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Enrolled</p>
                  <p className="font-display text-2xl font-bold text-foreground mt-1">{analytics.total_enrolled}</p>
                </div>
                <div className="border border-border rounded-[10px] bg-card p-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Active Readers</p>
                  <p className="font-display text-2xl font-bold text-foreground mt-1">{analytics.active_readers}</p>
                </div>
                <div className="border border-border rounded-[10px] bg-card p-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Avg Completion</p>
                  <p className="font-display text-2xl font-bold text-foreground mt-1">{analytics.avg_completion_pct}%</p>
                </div>
                <div className="border border-border rounded-[10px] bg-card p-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Exercise Accuracy</p>
                  <p className="font-display text-2xl font-bold text-foreground mt-1">
                    {analytics.exercise_accuracy_pct != null ? `${analytics.exercise_accuracy_pct}%` : "N/A"}
                  </p>
                </div>
              </div>

              {/* Learners Progress */}
              <div className="border border-border rounded-[10px] bg-card overflow-hidden">
                <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground">Learners Progress</h3>
                  <span className="text-xs text-muted-foreground">{analytics.learners.length}</span>
                </div>
                {analytics.learners.length === 0 ? (
                  <div className="p-6 text-sm text-muted-foreground">No learner progress recorded yet.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="border-b border-border text-xs uppercase text-muted-foreground bg-muted/40">
                        <tr>
                          <th className="px-4 py-2.5 font-medium">Name</th>
                          <th className="px-4 py-2.5 font-medium">Email</th>
                          <th className="px-4 py-2.5 font-medium">Completion</th>
                          <th className="px-4 py-2.5 font-medium">Stars</th>
                          <th className="px-4 py-2.5 font-medium">Chapter</th>
                          <th className="px-4 py-2.5 font-medium">Exercises</th>
                          <th className="px-4 py-2.5 font-medium">Notes</th>
                          <th className="px-4 py-2.5 font-medium">Last Active</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {analytics.learners.map((l) => (
                          <tr key={l.user_id}>
                            <td className="px-4 py-2.5 font-medium text-foreground">{l.full_name}</td>
                            <td className="px-4 py-2.5 text-xs text-muted-foreground">{l.email}</td>
                            <td className="px-4 py-2.5">{l.completion_pct}%</td>
                            <td className="px-4 py-2.5">
                              {l.stars_earned} / {l.stars_possible}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-xs">{l.current_chapter || "-"}</td>
                            <td className="px-4 py-2.5">
                              {l.exercises_correct} / {l.exercises_answered}
                            </td>
                            <td className="px-4 py-2.5">{l.notebook_count}</td>
                            <td className="px-4 py-2.5 text-xs text-muted-foreground">{formatDate(l.last_read_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Exercises & Quizzes */}
              <div className="border border-border rounded-[10px] bg-card overflow-hidden">
                <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground">Exercises & Quizzes</h3>
                  <span className="text-xs text-muted-foreground">{analytics.exercises.length}</span>
                </div>
                {analytics.exercises.length === 0 ? (
                  <div className="p-6 text-sm text-muted-foreground">No exercise answers captured yet.</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="border-b border-border text-xs uppercase text-muted-foreground bg-muted/40">
                        <tr>
                          <th className="px-4 py-2.5 font-medium">Exercise Key</th>
                          <th className="px-4 py-2.5 font-medium">Chapter</th>
                          <th className="px-4 py-2.5 font-medium">Type</th>
                          <th className="px-4 py-2.5 font-medium">Responses</th>
                          <th className="px-4 py-2.5 font-medium">Accuracy</th>
                          <th className="px-4 py-2.5 font-medium">Avg Stars</th>
                          <th className="px-4 py-2.5 font-medium">Attempts</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {analytics.exercises.map((ex) => {
                          const accClass =
                            ex.accuracy_pct == null
                              ? "text-muted-foreground"
                              : ex.accuracy_pct >= 70
                                ? "text-emerald-600 dark:text-emerald-400 font-medium"
                                : ex.accuracy_pct < 50
                                  ? "text-rose-600 dark:text-rose-400 font-medium"
                                  : "text-foreground";
                          return (
                            <tr key={ex.exercise_key}>
                              <td className="px-4 py-2.5 font-mono text-xs">{ex.exercise_key}</td>
                              <td className="px-4 py-2.5 font-mono text-xs">{ex.chapter_key || "-"}</td>
                              <td className="px-4 py-2.5">
                                <span className="inline-flex items-center px-2 py-0.5 rounded-[10px] text-xs border border-border bg-background">
                                  {ex.exercise_type}
                                </span>
                              </td>
                              <td className="px-4 py-2.5">{ex.responses_count}</td>
                              <td className={`px-4 py-2.5 ${accClass}`}>
                                {ex.accuracy_pct != null ? `${ex.accuracy_pct}%` : "N/A"}
                              </td>
                              <td className="px-4 py-2.5">{ex.avg_stars != null ? ex.avg_stars : "-"}</td>
                              <td className="px-4 py-2.5">{ex.total_attempts}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Notebook Reflections */}
              <div className="border border-border rounded-[10px] bg-card overflow-hidden">
                <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-foreground">Notebook Reflections</h3>
                  <span className="text-xs text-muted-foreground">{analytics.notebooks.length}</span>
                </div>
                {analytics.notebooks.length === 0 ? (
                  <div className="p-6 text-sm text-muted-foreground">No notebook entries submitted yet.</div>
                ) : (
                  <div className="divide-y divide-border">
                    {analytics.notebooks.map((nb) => (
                      <div key={`${nb.user_id}:${nb.exercise_key}`} className="p-4 flex flex-col gap-1.5">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-semibold text-foreground text-sm">{nb.student_name}</span>
                            <span className="text-muted-foreground">{nb.student_email}</span>
                          </div>
                          <div className="flex items-center gap-2 text-muted-foreground">
                            {nb.chapter_key && <span className="font-mono">{nb.chapter_key}</span>}
                            <span className="font-mono">{nb.exercise_key}</span>
                            <span>{formatDate(nb.updated_at)}</span>
                          </div>
                        </div>
                        {nb.prompt_text && (
                          <p className="text-xs text-muted-foreground">{nb.prompt_text}</p>
                        )}
                        <p className="text-sm text-foreground whitespace-pre-wrap">{nb.answer_text}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {revokeTarget && (
        <ConfirmDialog
          title="Revoke book access"
          description={`Revoke book access for ${revokeTarget.full_name} (${revokeTarget.email})?`}
          confirmLabel="Revoke"
          destructive
          pending={revokeMutation.isPending}
          error={revokeError || null}
          onCancel={() => setRevokeTarget(null)}
          onConfirm={() => revokeMutation.mutate(revokeTarget.user_id)}
        />
      )}
    </div>
  );
}
