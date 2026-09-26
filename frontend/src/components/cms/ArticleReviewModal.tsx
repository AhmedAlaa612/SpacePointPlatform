import React, { useState } from "react";
import {
  X,
  CheckCircle,
  AlertTriangle,
  FileText,
  Clock,
  User,
  RotateCcw,
  Archive,
  Star,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarkdownRenderer } from "@/components/cms/MarkdownRenderer";
import type { Article, ArticleReviewInput } from "@/types/cms";

interface ArticleReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  article: Article | null;
  onReviewAction: (articleId: string, payload: ArticleReviewInput) => Promise<void>;
  isProcessing: boolean;
}

export const ArticleReviewModal: React.FC<ArticleReviewModalProps> = ({
  isOpen,
  onClose,
  article,
  onReviewAction,
  isProcessing,
}) => {
  const [feedback, setFeedback] = useState("");
  const [showFeedbackBox, setShowFeedbackBox] = useState(false);
  const [featuredOrder, setFeaturedOrder] = useState<number>(article?.featured_order ?? 0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen || !article) return null;

  const handleApprove = async () => {
    setErrorMsg(null);
    try {
      await onReviewAction(article.id, {
        action: "approve",
        featured_order: featuredOrder,
      });
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to approve article.");
    }
  };

  const handleRequestChanges = async () => {
    if (!feedback.trim()) {
      setErrorMsg("Please provide feedback notes explaining the requested revisions.");
      return;
    }
    setErrorMsg(null);
    try {
      await onReviewAction(article.id, {
        action: "request_changes",
        reviewer_feedback: feedback.trim(),
      });
      setShowFeedbackBox(false);
      setFeedback("");
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to submit change request.");
    }
  };

  const handleUnpublish = async () => {
    setErrorMsg(null);
    try {
      await onReviewAction(article.id, { action: "unpublish" });
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to unpublish article.");
    }
  };

  const handleArchive = async () => {
    setErrorMsg(null);
    try {
      await onReviewAction(article.id, { action: "archive" });
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to archive article.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in-0 duration-200">
      <div className="relative w-full max-w-4xl max-h-[92vh] flex flex-col bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold font-display text-foreground">Editorial Article Review</h2>
                <span
                  className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${
                    article.status === "in_review"
                      ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                      : article.status === "changes_requested"
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      : article.status === "published"
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {article.status.replace("_", " ")}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Review submitted draft and decide whether to publish or request revisions.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {errorMsg && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-destructive text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Article Metadata Bar */}
          <div className="rounded-xl bg-muted/20 border border-border p-4 grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
            <div>
              <span className="text-muted-foreground block text-[11px] uppercase tracking-wider font-semibold">Author</span>
              <div className="flex items-center gap-1.5 mt-1 font-medium text-foreground">
                <User className="w-3.5 h-3.5 text-primary" />
                <span>{article.author_display_name}</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-muted text-muted-foreground">
                  {article.author_role || "Contributor"}
                </span>
              </div>
            </div>

            <div>
              <span className="text-muted-foreground block text-[11px] uppercase tracking-wider font-semibold">Category</span>
              <span className="inline-block mt-1 font-semibold text-primary">{article.category}</span>
            </div>

            <div>
              <span className="text-muted-foreground block text-[11px] uppercase tracking-wider font-semibold">Submitted / Updated</span>
              <div className="flex items-center gap-1 mt-1 text-muted-foreground">
                <Clock className="w-3.5 h-3.5" />
                <span>{new Date(article.updated_at).toLocaleDateString()}</span>
              </div>
            </div>

            <div>
              <span className="text-muted-foreground block text-[11px] uppercase tracking-wider font-semibold">Website Slug</span>
              <span className="block mt-1 font-mono text-muted-foreground truncate">/insights/{article.slug}</span>
            </div>
          </div>

          {/* Existing Reviewer Feedback if already rejected */}
          {article.reviewer_feedback && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 space-y-1 text-amber-300">
              <div className="flex items-center gap-2 font-semibold text-xs">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                <span>Current Feedback Given to Author:</span>
              </div>
              <p className="text-xs text-amber-200/90 font-mono pl-5">"{article.reviewer_feedback}"</p>
            </div>
          )}

          {/* Cover & Summary */}
          {article.cover_image_url && (
            <div className="rounded-xl overflow-hidden border border-border h-48 bg-muted/20 relative">
              <img
                src={article.cover_image_url}
                alt={article.title}
                className="w-full h-full object-cover"
              />
            </div>
          )}

          <div className="space-y-2">
            <h1 className="text-2xl font-bold font-display text-foreground">{article.title}</h1>
            {article.summary && (
              <p className="text-sm text-muted-foreground italic border-l-2 border-primary/40 pl-3">
                {article.summary}
              </p>
            )}
          </div>

          {/* Article Full Body */}
          <div className="p-5 rounded-xl border border-border bg-card/60">
            <MarkdownRenderer content={article.content_markdown} />
          </div>

          {/* Request Changes Feedback Form if opened */}
          {showFeedbackBox && (
            <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 space-y-3 animate-in fade-in-0">
              <div className="flex items-center gap-2 text-xs font-semibold text-amber-400 uppercase tracking-wider">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <span>Feedback for Author (Required)</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Explain specifically what changes or additions the author needs to make before this article can be published.
              </p>
              <textarea
                rows={3}
                placeholder="e.g. Please clarify paragraph 3 regarding telemetry bandwidth, and format the citations list using bullet points."
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                className="w-full p-3 rounded-xl border border-amber-500/30 bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-amber-500/40 resize-none"
              />
              <div className="flex justify-end gap-2">
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => setShowFeedbackBox(false)}
                  disabled={isProcessing}
                >
                  Cancel
                </Button>
                <Button
                  variant="default"
                  size="xs"
                  onClick={handleRequestChanges}
                  disabled={isProcessing}
                  className="bg-amber-600 hover:bg-amber-500 text-white"
                >
                  Send Feedback & Request Changes
                </Button>
              </div>
            </div>
          )}

          {/* Featured Order input for approval */}
          {article.status !== "published" && !showFeedbackBox && (
            <div className="flex items-center gap-3 pt-2 text-xs text-muted-foreground">
              <Star className="w-4 h-4 text-amber-400" />
              <span>Featured Display Priority (0 = standard, higher = shown earlier):</span>
              <input
                type="number"
                min={0}
                max={99}
                value={featuredOrder}
                onChange={(e) => setFeaturedOrder(parseInt(e.target.value, 10) || 0)}
                className="w-16 px-2 py-1 rounded-lg border border-border bg-background text-foreground text-center"
              />
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-card/50">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={isProcessing}>
            Close
          </Button>

          <div className="flex items-center gap-2">
            {article.status === "published" ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleUnpublish}
                  disabled={isProcessing}
                  className="gap-1.5"
                >
                  <RotateCcw className="w-3.5 h-3.5 text-muted-foreground" />
                  Unpublish to Draft
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleArchive}
                  disabled={isProcessing}
                  className="gap-1.5"
                >
                  <Archive className="w-3.5 h-3.5" />
                  Archive
                </Button>
              </>
            ) : (
              <>
                {!showFeedbackBox && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowFeedbackBox(true)}
                    disabled={isProcessing}
                    className="gap-1.5 border-amber-500/40 text-amber-400 hover:bg-amber-500/10 hover:text-amber-300"
                  >
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Request Changes
                  </Button>
                )}

                <Button
                  variant="default"
                  size="sm"
                  onClick={handleApprove}
                  disabled={isProcessing}
                  className="gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  Approve & Publish to Website
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
