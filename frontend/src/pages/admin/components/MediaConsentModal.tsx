import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, XCircle, Clock, ShieldAlert, Phone, Mail, User, Calendar, FileText } from "lucide-react"
import type { Registration } from "@/types/sessions"
import { manualOverrideMediaConsentApi } from "@/api/sessions/cohorts"
import { Modal, ModalActions } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

interface MediaConsentModalProps {
  cohortId: string
  registration: Registration
  onClose: () => void
}

export function MediaConsentModal({ cohortId, registration, onClose }: MediaConsentModalProps) {
  const queryClient = useQueryClient()
  const toast = useToast()

  const currentStatus = registration.media_consent_status ?? "pending"

  const [selectedStatus, setSelectedStatus] = useState<"consented" | "declined" | "pending">(
    currentStatus
  )
  const [parentName, setParentName] = useState(
    registration.media_consent_parent_name ?? registration.guardian_name ?? ""
  )
  const [parentPhone, setParentPhone] = useState(
    registration.media_consent_parent_phone ?? registration.guardian_phone ?? ""
  )
  const [parentEmail, setParentEmail] = useState(
    registration.media_consent_parent_email ?? ""
  )
  const [relationship, setRelationship] = useState(
    registration.media_consent_relationship ?? "Parent/Guardian"
  )
  const [notes, setNotes] = useState(registration.media_consent_notes ?? "")

  const overrideMutation = useMutation({
    mutationFn: () =>
      manualOverrideMediaConsentApi(cohortId, {
        registration_id: registration.id,
        consent_choice: selectedStatus,
        parent_name: parentName || undefined,
        parent_phone: parentPhone || undefined,
        parent_email: parentEmail || undefined,
        relationship: relationship || undefined,
        notes: notes || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions-cohort-registrations", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["cohort-media-consents", cohortId] })
      toast?.success(`Consent status set to ${selectedStatus.toUpperCase()} for ${registration.student_name}.`)
      onClose()
    },
    onError: (err) => {
      toast?.error(getErrorMessage(err))
    },
  })

  return (
    <Modal title={`Media Consent — ${registration.student_name}`} onClose={onClose}>
      <div className="space-y-5">
        {/* Status banner */}
        <div
          className={`flex items-center gap-3 p-3 rounded-xl border text-sm ${
            currentStatus === "consented"
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400"
              : currentStatus === "declined"
              ? "bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-400"
              : "bg-muted/60 border-border text-muted-foreground"
          }`}
        >
          {currentStatus === "consented" ? (
            <CheckCircle2 size={18} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
          ) : currentStatus === "declined" ? (
            <XCircle size={18} className="shrink-0 text-red-600 dark:text-red-400" />
          ) : (
            <Clock size={18} className="shrink-0" />
          )}
          <div className="min-w-0">
            <p className="font-semibold text-foreground">
              Current Status: {currentStatus === "consented" ? "Granted (YES)" : currentStatus === "declined" ? "Declined (NO)" : "Pending (No Form Received)"}
            </p>
            {registration.media_consent_signed_date && (
              <p className="text-xs opacity-80">
                Signed on: {registration.media_consent_signed_date}
              </p>
            )}
          </div>
        </div>

        {/* Existing Submission Details (if any) */}
        {registration.media_consent_id && (
          <div className="p-3.5 bg-card border border-border rounded-xl space-y-2 text-xs">
            <p className="font-semibold text-foreground text-xs uppercase tracking-wider mb-1 flex items-center gap-1.5">
              <FileText size={13} className="text-primary" /> Submission Record
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <User size={13} />
                <span className="font-medium text-foreground">{registration.media_consent_parent_name ?? "—"}</span>
                {registration.media_consent_relationship && (
                  <span className="text-muted-foreground">({registration.media_consent_relationship})</span>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <Phone size={13} />
                <span>{registration.media_consent_parent_phone ?? "—"}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Mail size={13} />
                <span className="truncate">{registration.media_consent_parent_email ?? "—"}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Calendar size={13} />
                <span>{registration.media_consent_signed_date ?? "—"}</span>
              </div>
            </div>

            {registration.media_consent_grants && registration.media_consent_grants.length > 0 && (
              <div className="pt-2 border-t border-border/50">
                <p className="font-medium text-foreground mb-1 text-[11px]">Permission Grants:</p>
                <div className="flex flex-wrap gap-1">
                  {registration.media_consent_grants.map((grant, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 bg-muted rounded-md text-[11px] text-muted-foreground"
                    >
                      {grant}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Manual State Override Section */}
        <div className="space-y-3 pt-2 border-t border-border">
          <p className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <ShieldAlert size={14} className="text-primary" /> Change Consent State Manually
          </p>

          {/* Option Pills */}
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => setSelectedStatus("consented")}
              className={`p-2.5 rounded-xl border text-xs font-medium text-center transition-all ${
                selectedStatus === "consented"
                  ? "bg-emerald-500/15 border-emerald-500 text-emerald-700 dark:text-emerald-400 font-semibold ring-2 ring-emerald-500/20"
                  : "border-border text-foreground hover:bg-muted"
              }`}
            >
              Granted (YES)
            </button>
            <button
              type="button"
              onClick={() => setSelectedStatus("declined")}
              className={`p-2.5 rounded-xl border text-xs font-medium text-center transition-all ${
                selectedStatus === "declined"
                  ? "bg-red-500/15 border-red-500 text-red-700 dark:text-red-400 font-semibold ring-2 ring-red-500/20"
                  : "border-border text-foreground hover:bg-muted"
              }`}
            >
              Declined (NO)
            </button>
            <button
              type="button"
              onClick={() => setSelectedStatus("pending")}
              className={`p-2.5 rounded-xl border text-xs font-medium text-center transition-all ${
                selectedStatus === "pending"
                  ? "bg-muted border-foreground/40 text-foreground font-semibold ring-2 ring-muted-foreground/20"
                  : "border-border text-foreground hover:bg-muted"
              }`}
            >
              Reset to Pending
            </button>
          </div>

          {/* Optional Guardian Contact details to update */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                Parent/Guardian Name
              </label>
              <input
                type="text"
                value={parentName}
                onChange={(e) => setParentName(e.target.value)}
                placeholder="Parent Full Name"
                className="w-full h-8 px-2.5 bg-background border border-border rounded-lg text-xs focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                Parent Mobile
              </label>
              <input
                type="text"
                value={parentPhone}
                onChange={(e) => setParentPhone(e.target.value)}
                placeholder="+971 50 ..."
                className="w-full h-8 px-2.5 bg-background border border-border rounded-lg text-xs focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                Parent Email
              </label>
              <input
                type="email"
                value={parentEmail}
                onChange={(e) => setParentEmail(e.target.value)}
                placeholder="parent@example.com"
                className="w-full h-8 px-2.5 bg-background border border-border rounded-lg text-xs focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                Relationship
              </label>
              <input
                type="text"
                value={relationship}
                onChange={(e) => setRelationship(e.target.value)}
                placeholder="Mother, Father, Legal Guardian"
                className="w-full h-8 px-2.5 bg-background border border-border rounded-lg text-xs focus:outline-none focus:border-primary"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-muted-foreground mb-1">
              Internal Notes / Reason
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Physical paper form received, WhatsApp verbal consent..."
              className="w-full h-8 px-2.5 bg-background border border-border rounded-lg text-xs focus:outline-none focus:border-primary"
            />
          </div>
        </div>

        <ModalActions
          onCancel={onClose}
          onConfirm={() => overrideMutation.mutate()}
          loading={overrideMutation.isPending}
          disabled={false}
          label="Save Changes"
        />
      </div>
    </Modal>
  )
}
