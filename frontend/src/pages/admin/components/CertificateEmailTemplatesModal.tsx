import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, Mail, Plus, Send, Trash2 } from "lucide-react"

import {
  createCertificateEmailTemplateApi,
  deleteCertificateEmailTemplateApi,
  listCertificateEmailTemplatesApi,
  sendTestEmailTemplateApi,
  updateCertificateEmailTemplateApi,
} from "@/api/sessions/certificateEmailTemplates"
import { Modal } from "@/pages/admin/components/common"
import type { CertificateEmailTemplate, CertificateEmailTemplateKind } from "@/types/sessions"

function errText(e: unknown, fallback: string): string {
  if (e && typeof e === "object") {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    if (err.response?.data?.detail) return err.response.data.detail
    if (err.message) return err.message
  }
  return fallback
}

interface CertificateEmailTemplatesModalProps {
  open: boolean
  onClose: () => void
  cohortId?: string
  initialTemplateId?: string | null
  onUpdated?: () => void
}

const PLACEHOLDERS = [
  "{student_name}",
  "{program_name}",
  "{cohort_name}",
  "{dates}",
  "{team_name}",
  "{rank}",
  "{certificate_list}",
  "{profile_link}",
]

const KIND_OPTIONS: Array<{ value: CertificateEmailTemplateKind; label: string }> = [
  { value: "individual", label: "Student" },
  { value: "team", label: "Team" },
  { value: "combined", label: "Combined" },
  { value: "profile", label: "Profile" },
]

export function CertificateEmailTemplatesModal(props: CertificateEmailTemplatesModalProps) {
  if (!props.open) return null
  return <CertificateEmailTemplatesModalContent key={props.initialTemplateId ?? "default"} {...props} />
}

function CertificateEmailTemplatesModalContent({
  onClose,
  cohortId,
  initialTemplateId,
  onUpdated,
}: CertificateEmailTemplatesModalProps) {
  const queryClient = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ["certificate-email-templates"],
    queryFn: listCertificateEmailTemplatesApi,
  })

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null)

  const activeSelectedId =
    selectedId !== null
      ? selectedId
      : initialTemplateId && templates.some((t) => t.id === initialTemplateId)
        ? initialTemplateId
        : templates.length > 0
          ? templates[0].id
          : "new"

  const activeTemplate =
    activeSelectedId === "new" ? undefined : templates.find((t) => t.id === activeSelectedId)

  return (
    <Modal onClose={onClose} title="Email Templates" maxWidth="max-w-4xl">
      <div className="space-y-5">
        {feedback && (
          <div
            className={`px-3 py-2 rounded-[10px] text-xs font-medium border ${
              feedback.type === "success"
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                : "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
            }`}
          >
            {feedback.text}
          </div>
        )}
        {/* Template selector bar */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setFeedback(null)
              setSelectedId("new")
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[10px] text-xs font-medium border transition-colors ${
              activeSelectedId === "new"
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-foreground hover:bg-muted/50"
            }`}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New</span>
          </button>

          {!isLoading &&
            templates.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => {
                  setFeedback(null)
                  setSelectedId(t.id)
                }}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[10px] text-xs font-medium border transition-colors ${
                  activeSelectedId === t.id
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border text-foreground hover:bg-muted/50"
                }`}
              >
                <Mail className="w-3.5 h-3.5" />
                <span>{t.name}</span>
              </button>
            ))}
        </div>

        {isLoading ? (
          <div className="py-8 text-center text-xs text-muted-foreground">Loading templates...</div>
        ) : (
          <TemplateEditorBody
            key={`${activeSelectedId}:${activeTemplate?.updated_at ?? (activeTemplate ? "loaded" : "new")}`}
            selectedId={activeSelectedId}
            template={activeTemplate}
            cohortId={cohortId}
            onSaved={(savedId) => {
              setFeedback({ type: "success", text: "Email template saved" })
              queryClient.invalidateQueries({ queryKey: ["certificate-email-templates"] })
              setSelectedId(savedId)
              onUpdated?.()
            }}
            onDeleted={() => {
              setFeedback({ type: "success", text: "Email template deleted" })
              queryClient.invalidateQueries({ queryKey: ["certificate-email-templates"] })
              setSelectedId("new")
              onUpdated?.()
            }}
            onFeedback={setFeedback}
          />
        )}
      </div>
    </Modal>
  )
}

function TemplateEditorBody({
  selectedId,
  template,
  cohortId,
  onSaved,
  onDeleted,
  onFeedback,
}: {
  selectedId: string
  template: CertificateEmailTemplate | undefined
  cohortId?: string
  onSaved: (savedId: string) => void
  onDeleted: () => void
  onFeedback: (feedback: { type: "success" | "error"; text: string } | null) => void
}) {
  const [name, setName] = useState(template?.name ?? "")
  const [kind, setKind] = useState<CertificateEmailTemplateKind>(template?.kind ?? "individual")
  const [subject, setSubject] = useState(
    template?.subject ?? "Your SpacePoint certificate — {program_name}"
  )
  const [bodyHtml, setBodyHtml] = useState(
    template?.body_html ??
      "<p>Hi {student_name},</p>\n<p>Congratulations on completing <strong>{program_name}</strong> ({dates})!</p>\n<p>— SpacePoint</p>"
  )
  const [isDefault, setIsDefault] = useState(template?.is_default ?? false)
  const [testEmail, setTestEmail] = useState("")

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!name.trim() || !subject.trim() || !bodyHtml.trim()) {
        throw new Error("Name, subject, and body are required")
      }
      if (selectedId === "new") {
        return createCertificateEmailTemplateApi({
          name: name.trim(),
          kind,
          subject: subject.trim(),
          body_html: bodyHtml,
          is_default: isDefault,
        })
      }
      return updateCertificateEmailTemplateApi(selectedId, {
        name: name.trim(),
        kind,
        subject: subject.trim(),
        body_html: bodyHtml,
        is_default: isDefault,
      })
    },
    onSuccess: (saved) => onSaved(saved.id),
    onError: (e: unknown) => onFeedback({ type: "error", text: errText(e, "Failed to save email template") }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCertificateEmailTemplateApi(id),
    onSuccess: () => onDeleted(),
    onError: (e: unknown) => onFeedback({ type: "error", text: errText(e, "Failed to delete email template") }),
  })

  const testMutation = useMutation({
    mutationFn: () => {
      if (!testEmail.trim()) throw new Error("Enter a test email address")
      return sendTestEmailTemplateApi({
        to_email: testEmail.trim(),
        subject,
        body_html: bodyHtml,
        kind,
        cohort_id: cohortId,
      })
    },
    onSuccess: (res) => onFeedback({ type: "success", text: `Test email sent to ${res.to}` }),
    onError: (e: unknown) => onFeedback({ type: "error", text: errText(e, "Failed to send test email") }),
  })

  return (
    <>
      {/* Direct-on-background form */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
        <div className="md:col-span-8 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground block">Template Name</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Student Certificate"
                className="w-full h-9 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </label>

            <label className="space-y-1.5">
              <span className="text-xs font-medium text-muted-foreground block">Type</span>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as CertificateEmailTemplateKind)}
                className="w-full h-9 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {KIND_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="space-y-1.5 block">
            <span className="text-xs font-medium text-muted-foreground block">Subject</span>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full h-9 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>

          <label className="space-y-1.5 block">
            <span className="text-xs font-medium text-muted-foreground block">Body (HTML)</span>
            <textarea
              rows={7}
              value={bodyHtml}
              onChange={(e) => setBodyHtml(e.target.value)}
              className="w-full p-3 rounded-[10px] border border-border bg-background text-sm font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>

          <label className="inline-flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              className="accent-primary"
            />
            <span>Default for this type</span>
          </label>
        </div>

        {/* Placeholders */}
        <div className="md:col-span-4 space-y-2">
          <span className="text-xs font-medium text-muted-foreground block">Placeholders</span>
          <div className="flex flex-wrap gap-1.5">
            {PLACEHOLDERS.map((token) => (
              <button
                key={token}
                type="button"
                onClick={() => setBodyHtml((prev) => (prev ? `${prev} ${token}` : token))}
                className="px-2.5 py-1 rounded-[10px] border border-border bg-background hover:bg-muted/60 text-xs font-mono text-foreground transition-colors"
              >
                {token}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Send test + Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-border">
        <div className="flex items-center gap-2">
          <input
            type="email"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            placeholder="test@example.com"
            className="h-9 px-3 rounded-[10px] border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <button
            type="button"
            onClick={() => testMutation.mutate()}
            disabled={testMutation.isPending}
            className="inline-flex items-center gap-1.5 h-9 px-3 rounded-[10px] border border-border text-sm font-medium text-foreground hover:bg-muted/50 disabled:opacity-50"
          >
            <Send className="w-3.5 h-3.5" />
            <span>{testMutation.isPending ? "Sending..." : "Send test"}</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          {selectedId !== "new" && (
            <button
              type="button"
              onClick={() => deleteMutation.mutate(selectedId)}
              disabled={deleteMutation.isPending}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-[10px] border border-rose-500/40 text-rose-500 text-sm font-medium hover:bg-rose-500/10 disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Delete</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 disabled:opacity-50"
          >
            <Check className="w-4 h-4" />
            <span>{saveMutation.isPending ? "Saving..." : "Save"}</span>
          </button>
        </div>
      </div>
    </>
  )
}
