import React from "react";
import { X, Mail, Phone, Building, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { WebsiteLead, WebsiteLeadStatus } from "@/types/cms";

interface LeadDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  lead: WebsiteLead | null;
  onStatusChange: (status: WebsiteLeadStatus) => Promise<void>;
  isUpdating: boolean;
}

export const LeadDetailModal: React.FC<LeadDetailModalProps> = ({
  isOpen,
  onClose,
  lead,
  onStatusChange,
  isUpdating,
}) => {
  if (!isOpen || !lead) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in-0 duration-200">
      <div className="relative w-full max-w-lg bg-card border border-border/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <Mail className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold font-display text-foreground">Website Inquiry Details</h2>
              <p className="text-xs text-muted-foreground">
                Inquiry received via website lead capture forms.
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
        <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
          {/* Status Bar */}
          <div className="flex items-center justify-between p-3 rounded-xl bg-muted/20 border border-border">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Lead Workflow Status
            </span>
            <select
              value={lead.status}
              onChange={(e) => onStatusChange(e.target.value as WebsiteLeadStatus)}
              disabled={isUpdating}
              className="text-xs px-2.5 py-1 rounded-lg border border-border bg-background text-foreground font-semibold focus:outline-none focus:ring-2 focus:ring-primary/40"
            >
              <option value="new">New Inquiry</option>
              <option value="contacted">Contacted</option>
              <option value="converted">Converted</option>
              <option value="archived">Archived</option>
            </select>
          </div>

          {/* Contact Details */}
          <div className="space-y-2 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 rounded-xl bg-muted/10 border border-border/60">
                <span className="text-[11px] text-muted-foreground block uppercase font-semibold">Contact Name</span>
                <span className="text-foreground font-medium mt-0.5 block">
                  {lead.contact_name || "Anonymous Subscriber"}
                </span>
              </div>
              <div className="p-3 rounded-xl bg-muted/10 border border-border/60">
                <span className="text-[11px] text-muted-foreground block uppercase font-semibold">Inquiry Type</span>
                <span className="text-primary font-bold uppercase mt-0.5 block">{lead.lead_type.replace("_", " ")}</span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-muted/10 border border-border/60 space-y-1">
              <div className="flex items-center gap-2 text-foreground font-medium">
                <Mail className="w-3.5 h-3.5 text-primary" />
                <a href={`mailto:${lead.email}`} className="hover:underline">
                  {lead.email}
                </a>
              </div>
              {lead.phone && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Phone className="w-3.5 h-3.5 text-primary" />
                  <a href={`tel:${lead.phone}`} className="hover:underline">
                    {lead.phone}
                  </a>
                </div>
              )}
              {lead.organization_name && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Building className="w-3.5 h-3.5 text-primary" />
                  <span>{lead.organization_name}</span>
                </div>
              )}
            </div>

            {lead.program_interest && (
              <div className="p-3 rounded-xl bg-muted/10 border border-border/60">
                <span className="text-[11px] text-muted-foreground block uppercase font-semibold">Program of Interest</span>
                <span className="text-foreground font-medium mt-0.5 block">{lead.program_interest}</span>
              </div>
            )}

            {/* Submission Date */}
            <div className="flex items-center gap-1.5 text-muted-foreground pt-1">
              <Calendar className="w-3.5 h-3.5" />
              <span>Received {new Date(lead.created_at).toLocaleString()}</span>
            </div>

            {/* JSON Metadata Details */}
            {lead.details && Object.keys(lead.details).length > 0 && (
              <div className="space-y-1.5 pt-2">
                <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  Additional Details & Payload
                </span>
                <div className="p-3 rounded-xl bg-muted/30 border border-border overflow-x-auto font-mono text-[11px] text-foreground">
                  <pre>{JSON.stringify(lead.details, null, 2)}</pre>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end px-6 py-3 border-t border-border bg-card/50">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
};
