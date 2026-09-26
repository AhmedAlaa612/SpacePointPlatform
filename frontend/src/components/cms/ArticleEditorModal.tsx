import React, { useState, useEffect } from "react";
import {
  X,
  Send,
  Save,
  AlertTriangle,
  Eye,
  Edit3,
  Image as ImageIcon,
  CheckCircle2,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { MarkdownRenderer } from "@/components/cms/MarkdownRenderer";
import type { Article, ArticleCreateInput, ArticleUpdateInput } from "@/types/cms";

interface ArticleEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: ArticleCreateInput | ArticleUpdateInput, submitForReview: boolean) => Promise<void>;
  articleToEdit?: Article | null;
  isSaving: boolean;
}

const CATEGORIES = [
  "TECHNOLOGY",
  "AEROSPACE",
  "SATELLITES & AI",
  "MISSION UPDATES",
  "EDUCATION",
  "CAREERS",
];

export const ArticleEditorModal: React.FC<ArticleEditorModalProps> = ({
  isOpen,
  onClose,
  onSave,
  articleToEdit,
  isSaving,
}) => {
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("TECHNOLOGY");
  const [summary, setSummary] = useState("");
  const [coverImageUrl, setCoverImageUrl] = useState("");
  const [contentMarkdown, setContentMarkdown] = useState("");
  const [activeTab, setActiveTab] = useState<"write" | "preview">("write");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (articleToEdit) {
      setTitle(articleToEdit.title);
      setCategory(articleToEdit.category);
      setSummary(articleToEdit.summary || "");
      setCoverImageUrl(articleToEdit.cover_image_url || "");
      setContentMarkdown(articleToEdit.content_markdown || "");
    } else {
      setTitle("");
      setCategory("TECHNOLOGY");
      setSummary("");
      setCoverImageUrl("");
      setContentMarkdown("");
    }
    setActiveTab("write");
    setErrorMsg(null);
  }, [articleToEdit, isOpen]);

  if (!isOpen) return null;

  const isResubmission = articleToEdit?.status === "changes_requested";

  const handleSubmit = async (submitForReview: boolean) => {
    if (!title.trim()) {
      setErrorMsg("Please provide an article title.");
      return;
    }
    if (!contentMarkdown.trim()) {
      setErrorMsg("Please write your article content.");
      return;
    }

    setErrorMsg(null);

    const payload = {
      title: title.trim(),
      category: category.trim(),
      summary: summary.trim() || null,
      cover_image_url: coverImageUrl.trim() || null,
      content_markdown: contentMarkdown,
      submit_for_review: submitForReview,
    };

    try {
      await onSave(payload, submitForReview);
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to save article. Please try again.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in-0 duration-200">
      <div className="relative w-full max-w-4xl max-h-[92vh] flex flex-col bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold font-display text-foreground">
                {articleToEdit ? (isResubmission ? "Address Feedback & Resubmit" : "Edit Article") : "Write New Article"}
              </h2>
              <p className="text-xs text-muted-foreground">
                {isResubmission
                  ? "Update your draft addressing the reviewer's notes below and resubmit for publishing."
                  : "Draft your article using Markdown. Submit when ready for editorial review."}
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

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Reviewer Feedback Banner if changes requested */}
          {isResubmission && articleToEdit.reviewer_feedback && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 space-y-1.5 text-amber-300">
              <div className="flex items-center gap-2 font-semibold text-sm">
                <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
                <span>Editorial Review Feedback:</span>
              </div>
              <p className="text-xs text-amber-200/90 pl-6 leading-relaxed bg-amber-500/10 p-2.5 rounded-lg border border-amber-500/20 font-mono">
                "{articleToEdit.reviewer_feedback}"
              </p>
              <p className="text-[11px] text-amber-300/80 pl-6">
                Make your revisions in the editor below. When finished, click <strong>"Resubmit for Review"</strong>.
              </p>
            </div>
          )}

          {errorMsg && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-destructive text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Title & Category Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2 space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Article Title <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Next-Gen Cubesat Communication Architectures"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all placeholder:text-muted-foreground/60"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all"
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Cover Image & Summary */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Cover Image URL
              </label>
              <div className="relative">
                <input
                  type="url"
                  placeholder="https://images.unsplash.com/..."
                  value={coverImageUrl}
                  onChange={(e) => setCoverImageUrl(e.target.value)}
                  className="w-full pl-9 pr-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all placeholder:text-muted-foreground/60"
                />
                <ImageIcon className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
              </div>
              {coverImageUrl && (
                <div className="mt-2 h-20 w-full rounded-lg overflow-hidden border border-border bg-muted/20 relative">
                  <img
                    src={coverImageUrl}
                    alt="Cover preview"
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLElement).style.display = "none";
                    }}
                  />
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Summary / Abstract
              </label>
              <textarea
                rows={3}
                placeholder="Brief 1-2 sentence overview for cards and social previews..."
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all placeholder:text-muted-foreground/60 resize-none"
              />
            </div>
          </div>

          {/* Markdown Content with Write / Preview Tabs */}
          <div className="space-y-2">
            <div className="flex items-center justify-between border-b border-border pb-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Article Body (Markdown) <span className="text-destructive">*</span>
              </label>
              <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-lg border border-border">
                <button
                  type="button"
                  onClick={() => setActiveTab("write")}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all ${
                    activeTab === "write"
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  Write
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("preview")}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium transition-all ${
                    activeTab === "preview"
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Eye className="w-3.5 h-3.5" />
                  Preview
                </button>
              </div>
            </div>

            {activeTab === "write" ? (
              <textarea
                rows={14}
                placeholder="Write your article in Markdown here...&#10;&#10;## Introduction&#10;Your insights...&#10;&#10;- Key finding 1&#10;- Key finding 2"
                value={contentMarkdown}
                onChange={(e) => setContentMarkdown(e.target.value)}
                className="w-full p-4 rounded-xl border border-border bg-background font-mono text-xs/relaxed text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition-all placeholder:text-muted-foreground/50 resize-y"
              />
            ) : (
              <div className="min-h-[280px] p-5 rounded-xl border border-border bg-card/60 overflow-y-auto max-h-[350px]">
                <MarkdownRenderer content={contentMarkdown} />
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-card/50">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={isSaving}>
            Cancel
          </Button>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleSubmit(false)}
              disabled={isSaving}
              className="gap-1.5"
            >
              <Save className="w-3.5 h-3.5" />
              Save as Draft
            </Button>

            <Button
              variant="default"
              size="sm"
              onClick={() => handleSubmit(true)}
              disabled={isSaving}
              className={`gap-1.5 ${
                isResubmission ? "bg-amber-600 hover:bg-amber-500 text-white" : ""
              }`}
            >
              {isResubmission ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Resubmit for Review
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  Submit for Editorial Review
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
