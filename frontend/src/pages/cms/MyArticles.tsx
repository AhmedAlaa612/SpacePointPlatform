import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Plus,
  Search,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Edit,
  Trash2,
  ExternalLink,
  Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader, StatCard, EmptyState, Spinner } from "@/components/ui/primitives";
import { ArticleEditorModal } from "@/components/cms/ArticleEditorModal";
import { useToast } from "@/components/ui/toast";
import {
  getMyArticles,
  createArticle,
  updateArticle,
  deleteArticle,
} from "@/api/cms";
import type { Article, ArticleCreateInput, ArticleUpdateInput, ArticleStatus } from "@/types/cms";

export default function MyArticles() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);

  // Load articles
  const { data: articles = [], isLoading } = useQuery({
    queryKey: ["my-articles"],
    queryFn: getMyArticles,
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (payload: ArticleCreateInput) => createArticle(payload),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["my-articles"] });
      toast?.success(
        vars.submit_for_review
          ? "Article submitted for editorial review!"
          : "Draft saved successfully."
      );
    },
    onError: (err: any) => {
      toast?.error(err?.response?.data?.detail || "Failed to create article.");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ArticleUpdateInput }) =>
      updateArticle(id, payload),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["my-articles"] });
      toast?.success(
        vars.payload.submit_for_review
          ? "Article submitted for editorial review!"
          : "Article updated successfully."
      );
    },
    onError: (err: any) => {
      toast?.error(err?.response?.data?.detail || "Failed to update article.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteArticle(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["my-articles"] });
      toast?.success("Draft deleted.");
    },
    onError: (err: any) => {
      toast?.error(err?.response?.data?.detail || "Failed to delete article.");
    },
  });

  // Filtered list
  const filteredArticles = useMemo(() => {
    return articles.filter((art) => {
      const matchesFilter =
        activeFilter === "all" ||
        (activeFilter === "changes_requested" && art.status === "changes_requested") ||
        (activeFilter === "in_review" && art.status === "in_review") ||
        (activeFilter === "published" && art.status === "published") ||
        (activeFilter === "draft" && art.status === "draft");

      const matchesSearch =
        searchQuery.trim() === "" ||
        art.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (art.summary && art.summary.toLowerCase().includes(searchQuery.toLowerCase())) ||
        art.category.toLowerCase().includes(searchQuery.toLowerCase());

      return matchesFilter && matchesSearch;
    });
  }, [articles, activeFilter, searchQuery]);

  // Counts
  const counts = useMemo(() => {
    const published = articles.filter((a) => a.status === "published").length;
    const inReview = articles.filter((a) => a.status === "in_review").length;
    const changes = articles.filter((a) => a.status === "changes_requested").length;
    const drafts = articles.filter((a) => a.status === "draft").length;
    return { total: articles.length, published, inReview, changes, drafts };
  }, [articles]);

  const handleOpenCreate = () => {
    setSelectedArticle(null);
    setEditorOpen(true);
  };

  const handleOpenEdit = (article: Article) => {
    setSelectedArticle(article);
    setEditorOpen(true);
  };

  const handleDelete = async (article: Article) => {
    if (confirm(`Are you sure you want to delete draft "${article.title}"?`)) {
      await deleteMutation.mutateAsync(article.id);
    }
  };

  const handleSaveArticle = async (
    payload: ArticleCreateInput | ArticleUpdateInput,
    submitForReview: boolean
  ) => {
    if (selectedArticle) {
      await updateMutation.mutateAsync({
        id: selectedArticle.id,
        payload: {
          ...payload,
          submit_for_review: submitForReview,
        },
      });
    } else {
      await createMutation.mutateAsync({
        ...(payload as ArticleCreateInput),
        submit_for_review: submitForReview,
      });
    }
  };

  const getStatusBadge = (status: ArticleStatus) => {
    switch (status) {
      case "published":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" />
            Published
          </span>
        );
      case "in_review":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Clock className="w-3 h-3" />
            In Review
          </span>
        );
      case "changes_requested":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse">
            <AlertTriangle className="w-3 h-3" />
            Changes Requested
          </span>
        );
      case "draft":
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-muted text-muted-foreground border border-border">
            <FileText className="w-3 h-3" />
            Draft
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Articles & Insights"
        subtitle="Author technical articles, mission logs, and aerospace perspectives for the SpacePoint platform."
        action={
          <Button onClick={handleOpenCreate} size="sm" className="gap-1.5 shadow-sm">
            <Plus className="w-4 h-4" />
            Write Article
          </Button>
        }
      />

      {/* Stats Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          icon={<FileText className="w-5 h-5 text-primary" />}
          label="Total Articles"
          value={counts.total}
          sub="All authored pieces"
        />
        <StatCard
          icon={<Clock className="w-5 h-5 text-blue-400" />}
          label="In Editorial Review"
          value={counts.inReview}
          sub="Pending review"
        />
        <StatCard
          icon={<AlertTriangle className="w-5 h-5 text-amber-400" />}
          label="Needs Feedback Edit"
          value={counts.changes}
          sub={counts.changes > 0 ? "Action required" : "All clear"}
        />
        <StatCard
          icon={<CheckCircle2 className="w-5 h-5 text-emerald-400" />}
          label="Published Online"
          value={counts.published}
          sub="Live on SpacePoint"
        />
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {[
            { id: "all", label: "All", count: counts.total },
            { id: "changes_requested", label: "Changes Requested", count: counts.changes, highlight: counts.changes > 0 },
            { id: "in_review", label: "In Review", count: counts.inReview },
            { id: "draft", label: "Drafts", count: counts.drafts },
            { id: "published", label: "Published", count: counts.published },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveFilter(tab.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all whitespace-nowrap flex items-center gap-1.5 ${
                activeFilter === tab.id
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : tab.highlight
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/30 hover:bg-amber-500/20"
                  : "bg-muted/40 text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <span>{tab.label}</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                  activeFilter === tab.id
                    ? "bg-primary-foreground/20 text-primary-foreground"
                    : "bg-background/80 text-muted-foreground"
                }`}
              >
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <input
            type="text"
            placeholder="Search my articles..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-xl border border-border bg-card/60 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-2.5" />
        </div>
      </div>

      {/* Articles List / Grid */}
      {isLoading ? (
        <Spinner size="lg" />
      ) : filteredArticles.length === 0 ? (
        <EmptyState
          title="No articles found"
          hint={
            activeFilter === "changes_requested"
              ? "Great job! None of your articles currently require revisions."
              : "Start sharing your knowledge by writing your first technical article."
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredArticles.map((article) => {
            const hasRequestedChanges = article.status === "changes_requested";

            return (
              <div
                key={article.id}
                className={`rounded-2xl border transition-all p-5 flex flex-col justify-between gap-4 ${
                  hasRequestedChanges
                    ? "bg-amber-500/[0.04] border-amber-500/40 shadow-lg shadow-amber-500/5 ring-1 ring-amber-500/20"
                    : "bg-card/70 border-border hover:border-primary/40"
                }`}
              >
                {/* Changes Requested Banner */}
                {hasRequestedChanges && article.reviewer_feedback && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 space-y-1.5 text-amber-300">
                    <div className="flex items-center gap-2 font-semibold text-xs text-amber-400">
                      <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
                      <span>Action Required: Reviewer Requested Changes</span>
                    </div>
                    <p className="text-xs text-amber-200/90 pl-6 leading-relaxed font-mono">
                      "{article.reviewer_feedback}"
                    </p>
                    <div className="pl-6 pt-1">
                      <Button
                        size="xs"
                        onClick={() => handleOpenEdit(article)}
                        className="bg-amber-600 hover:bg-amber-500 text-white gap-1.5"
                      >
                        <Edit className="w-3 h-3" />
                        Address Feedback & Edit Article
                      </Button>
                    </div>
                  </div>
                )}

                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  {/* Left: Thumbnail & Content */}
                  <div className="flex items-start gap-4">
                    {article.cover_image_url ? (
                      <div className="w-20 h-20 rounded-xl overflow-hidden border border-border bg-muted/20 shrink-0 hidden sm:block">
                        <img
                          src={article.cover_image_url}
                          alt={article.title}
                          className="w-full h-full object-cover"
                        />
                      </div>
                    ) : (
                      <div className="w-20 h-20 rounded-xl border border-dashed border-border bg-muted/10 shrink-0 hidden sm:flex items-center justify-center text-muted-foreground">
                        <FileText className="w-6 h-6 opacity-40" />
                      </div>
                    )}

                    <div className="space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-primary px-2 py-0.5 rounded-md bg-primary/10">
                          {article.category}
                        </span>
                        {getStatusBadge(article.status)}
                        <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          Updated {new Date(article.updated_at).toLocaleDateString()}
                        </span>
                      </div>

                      <h3 className="text-base sm:text-lg font-bold font-display text-foreground leading-snug">
                        {article.title}
                      </h3>

                      {article.summary && (
                        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                          {article.summary}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Right: Actions */}
                  <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                    {article.status === "draft" && (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(article)}
                          className="text-destructive hover:bg-destructive/10"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleOpenEdit(article)}
                          className="gap-1.5"
                        >
                          <Edit className="w-3.5 h-3.5" />
                          Edit Draft
                        </Button>
                        <Button
                          variant="default"
                          size="sm"
                          onClick={async () => {
                            await updateMutation.mutateAsync({
                              id: article.id,
                              payload: { submit_for_review: true },
                            });
                          }}
                          className="gap-1.5"
                        >
                          <Send className="w-3.5 h-3.5" />
                          Submit for Review
                        </Button>
                      </>
                    )}

                    {article.status === "changes_requested" && (
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => handleOpenEdit(article)}
                        className="bg-amber-600 hover:bg-amber-500 text-white gap-1.5"
                      >
                        <Edit className="w-3.5 h-3.5" />
                        Edit & Resubmit
                      </Button>
                    )}

                    {article.status === "in_review" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleOpenEdit(article)}
                        className="gap-1.5"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        View Submitted
                      </Button>
                    )}

                    {article.status === "published" && (
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleOpenEdit(article)}
                          className="gap-1.5"
                        >
                          <FileText className="w-3.5 h-3.5" />
                          View
                        </Button>
                        <a
                          href={`http://localhost:4321/insights/${article.slug}`}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1.5 text-muted-foreground hover:text-primary rounded-lg border border-border bg-card/60 transition-colors"
                          title="View on public website"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Editor Modal */}
      <ArticleEditorModal
        isOpen={editorOpen}
        onClose={() => setEditorOpen(false)}
        onSave={handleSaveArticle}
        articleToEdit={selectedArticle}
        isSaving={createMutation.isPending || updateMutation.isPending}
      />
    </div>
  );
}
