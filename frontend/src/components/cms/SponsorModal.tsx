import React, { useState, useEffect } from "react";
import { X, Building2, Globe, Image as ImageIcon, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Sponsor, SponsorCreateInput, SponsorUpdateInput, SponsorTier } from "@/types/cms";

interface SponsorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: SponsorCreateInput | SponsorUpdateInput) => Promise<void>;
  sponsorToEdit?: Sponsor | null;
  isSaving: boolean;
}

const TIERS: { value: SponsorTier; label: string }[] = [
  { value: "partner", label: "Strategic Partner" },
  { value: "client", label: "Client / Sponsor" },
  { value: "supporter", label: "Government & Ecosystem Supporter" },
  { value: "academic", label: "Academic / University" },
];

export const SponsorModal: React.FC<SponsorModalProps> = ({
  isOpen,
  onClose,
  onSave,
  sponsorToEdit,
  isSaving,
}) => {
  const [name, setName] = useState("");
  const [tier, setTier] = useState<SponsorTier>("partner");
  const [logoUrl, setLogoUrl] = useState("");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [displayOrder, setDisplayOrder] = useState<number>(0);
  const [isActive, setIsActive] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (sponsorToEdit) {
      setName(sponsorToEdit.name);
      setTier(sponsorToEdit.tier);
      setLogoUrl(sponsorToEdit.logo_url);
      setWebsiteUrl(sponsorToEdit.website_url || "");
      setDisplayOrder(sponsorToEdit.display_order);
      setIsActive(sponsorToEdit.is_active);
    } else {
      setName("");
      setTier("partner");
      setLogoUrl("");
      setWebsiteUrl("");
      setDisplayOrder(0);
      setIsActive(true);
    }
    setErrorMsg(null);
  }, [sponsorToEdit, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setErrorMsg("Please enter sponsor name.");
      return;
    }
    if (!logoUrl.trim()) {
      setErrorMsg("Please provide logo URL or file path.");
      return;
    }

    try {
      await onSave({
        name: name.trim(),
        tier,
        logo_url: logoUrl.trim(),
        website_url: websiteUrl.trim() || null,
        display_order: displayOrder,
        is_active: isActive,
      });
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || "Failed to save sponsor.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in-0 duration-200">
      <div className="relative w-full max-w-lg bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold font-display text-foreground">
                {sponsorToEdit ? "Edit Sponsor" : "Add Brand Sponsor"}
              </h2>
              <p className="text-xs text-muted-foreground">
                Configure sponsor logo for the marquee and partnerships showcase.
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
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {errorMsg && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-destructive text-xs">
              {errorMsg}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Sponsor / Organization Name <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              placeholder="e.g. Dubai Future Foundation"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Partnership Tier
            </label>
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value as SponsorTier)}
              className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            >
              {TIERS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Logo URL or Path <span className="text-destructive">*</span>
            </label>
            <div className="relative">
              <input
                type="text"
                placeholder="/assets/sponsors/dff.png or https://..."
                value={logoUrl}
                onChange={(e) => setLogoUrl(e.target.value)}
                className="w-full pl-9 pr-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 font-mono"
                required
              />
              <ImageIcon className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
            </div>
            {logoUrl && (
              <div className="mt-2 h-16 w-32 rounded-lg border border-border bg-muted/30 flex items-center justify-center p-2">
                <img
                  src={logoUrl}
                  alt="Logo preview"
                  className="max-h-full max-w-full object-contain"
                  onError={(e) => {
                    (e.target as HTMLElement).style.display = "none";
                  }}
                />
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Website URL (Optional)
            </label>
            <div className="relative">
              <input
                type="url"
                placeholder="https://..."
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                className="w-full pl-9 pr-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
              <Globe className="w-4 h-4 text-muted-foreground absolute left-3 top-2.5" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 pt-1">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Display Order
              </label>
              <input
                type="number"
                min={0}
                value={displayOrder}
                onChange={(e) => setDisplayOrder(parseInt(e.target.value, 10) || 0)}
                className="w-full px-3.5 py-2 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>

            <div className="flex items-center gap-2 pt-6">
              <input
                type="checkbox"
                id="is_active_sponsor"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
              />
              <label htmlFor="is_active_sponsor" className="text-xs font-medium text-foreground cursor-pointer">
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
              Save Sponsor
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
