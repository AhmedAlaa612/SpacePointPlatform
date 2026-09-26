import React, { useState, useEffect } from "react";
import { X, Newspaper, Globe, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { MediaClipping, MediaClippingCreateInput, MediaClippingUpdateInput } from "@/types/cms";

interface MediaClippingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: MediaClippingCreateInput | MediaClippingUpdateInput) => Promise<void>;
  clippingToEdit?: MediaClipping | null;
  isSaving: boolean;
}

export const MediaClippingModal: React.FC<MediaClippingModalProps> = ({
  isOpen,
  onClose,
  onSave,
  clippingToEdit,
  isSaving,
}) => {
  const [publisherName, setPublisherName] = useState("");
  const [articleTitle, setArticleTitle] = useState("");
  const [articleUrl, setArticleUrl] = useState("");
  const [publishedDate, setPublishedDate] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [isArabic, setIsArabic] = useState<boolean>(false);
  const [snippet, setSnippet] = useState("");
  const [displayOrder, setDisplayOrder] = useState<number>(0);
  const [isActive, setIsActive] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (clippingToEdit) {
      setPublisherName(clippingToEdit.publisher_name);
      setArticleTitle(clippingToEdit.article_title);
      setArticleUrl(clippingToEdit.article_url);
      setPublishedDate(clippingToEdit.published_date.slice(0, 10));
      setLogoUrl(clippingToEdit.logo_url || "");
      setIsArabic(clippingToEdit.is_arabic);
      setSnippet(clippingToEdit.snippet || "");
      setDisplayOrder(clippingToEdit.display_order);
      setIsActive(clippingToEdit.is_active);
    } else {
      setPublisherName("");
      setArticleTitle("");
      setArticleUrl("");
      setPublishedDate(new Date().toISOString().slice(0, 10));
      setLogoUrl("");
      setIsArabic(false);
      setSnippet("");
      setDisplayOrder(0);
      setIsActive(true);
    }
    setErrorMsg(null);
  }, [clippingToEdit, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!publisherName.trim()) {
      setErrorMsg("Please enter publisher name.");
      return;
    }
    if (!articleTitle.trim()) {
      setErrorMsg("Please enter article title.");
      return;
    }
    if (!articleUrl.trim()) {
      setErrorMsg("Please enter article URL.");
      return;
    }

    try {
      await onSave({
        publisher_name: publisherName.trim(),
        article_title: articleTitle.trim(),
        article_url: articleUrl.trim(),
        published_date: new Date(publishedDate).toISOString(),
        logo_url: logoUrl.trim() || null,
        is_arabic: isArabic,
        snippet: snippet.trim() || null,
        display_order: displayOrder,
        is_active: isActive,
      });
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to save media clipping.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in-0 duration-200">
      <div className="relative w-full max-w-xl max-h-[92vh] flex flex-col bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <Newspaper className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold font-display text-foreground">
                {clippingToEdit ? "Edit Media Coverage" : "Add Press Coverage"}
              </h2>
              <p className="text-xs text-muted-foreground">
                Feature news articles and publications about SpacePoint.
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

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {errorMsg && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-destructive text-xs">
              {errorMsg}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Publisher / News Outlet <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Gulf News, Khaleej Times, Wam"
                value={publisherName}
                onChange={(e) => setPublisherName(e.target.value)}
                className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Publication Date <span className="text-destructive">*</span>
              </label>
              <input
                type="date"
                value={publishedDate}
                onChange={(e) => setPublishedDate(e.target.value)}
                className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                required
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Article Headline / Title <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              placeholder="e.g. SpacePoint launches revolutionary space kits for schools across UAE"
              value={articleTitle}
              onChange={(e) => setArticleTitle(e.target.value)}
              dir={isArabic ? "rtl" : "ltr"}
              className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Article Source URL <span className="text-destructive">*</span>
            </label>
            <div className="relative">
              <input
                type="url"
                placeholder="https://..."
                value={articleUrl}
                onChange={(e) => setArticleUrl(e.target.value)}
                className="w-full pl-9 pr-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                required
              />
              <Globe className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Publisher Logo URL
            </label>
            <input
              type="text"
              placeholder="/assets/press/gulfnews.png or https://..."
              value={logoUrl}
              onChange={(e) => setLogoUrl(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Excerpt / Snippet
            </label>
            <textarea
              rows={3}
              placeholder="Key quote or summary excerpt from the published piece..."
              value={snippet}
              onChange={(e) => setSnippet(e.target.value)}
              dir={isArabic ? "rtl" : "ltr"}
              className="w-full p-3 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-4 pt-1">
            <div className="flex items-center gap-2 pt-2">
              <input
                type="checkbox"
                id="is_arabic_clipping"
                checked={isArabic}
                onChange={(e) => setIsArabic(e.target.checked)}
                className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
              />
              <label htmlFor="is_arabic_clipping" className="text-xs font-medium text-foreground cursor-pointer">
                Arabic Press (RTL)
              </label>
            </div>

            <div className="flex items-center gap-2 pt-2">
              <input
                type="checkbox"
                id="is_active_clipping"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
              />
              <label htmlFor="is_active_clipping" className="text-xs font-medium text-foreground cursor-pointer">
                Active on Website
              </label>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-4 border-t border-border">
            <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={isSaving}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={isSaving} className="gap-1.5">
              <Save className="w-3.5 h-3.5" />
              Save Clipping
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
