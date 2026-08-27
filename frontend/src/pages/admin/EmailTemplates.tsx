import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eye, Loader2, Mail, Paperclip, Pause, Play, Send } from "lucide-react"
import {
  listEmailTemplatesApi,
  pauseEmailTemplateApi,
  previewEmailTemplateApi,
  sendTestEmailTemplateApi,
  updateEmailTemplateApi,
} from "@/api/emailTemplates"
import type { EmailTemplate } from "@/types/emailTemplates"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { cn } from "@/lib/utils"

export default function EmailTemplates() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<EmailTemplate | null>(null)

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ["admin-email-templates"],
    queryFn: listEmailTemplatesApi,
  })

  const pauseMutation = useMutation({
    mutationFn: ({ id, is_paused }: { id: string; is_paused: boolean }) => pauseEmailTemplateApi(id, is_paused),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-email-templates"] }),
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to update"),
  })

  const grouped = templates.reduce<Record<string, EmailTemplate[]>>((acc, t) => {
    ;(acc[t.category] ??= []).push(t)
    return acc
  }, {})

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Email Templates"
        subtitle="Every system email in one place — what triggers it, its placeholders and attachments, and whether it's currently sending. Edit the subject/body or pause a send without a code change."
      />

      {templates.length === 0 ? (
        <EmptyState
          title="No email templates yet"
          hint="Run alembic upgrade head (or the seed script) to create the 27 system templates."
        />
      ) : (
        <div className="flex flex-col gap-8">
          {Object.entries(grouped).map(([category, items]) => (
            <div key={category}>
              <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground border-b border-border pb-2 mb-1 flex items-center gap-2">
                {category}
                <span className="font-normal text-muted-foreground/60 normal-case tracking-normal">({items.length})</span>
              </h2>
              <div className="divide-y divide-border">
                {items.map((t) => (
                  <EmailTemplateRow
                    key={t.id}
                    template={t}
                    onEdit={() => setEditing(t)}
                    onTogglePause={() => pauseMutation.mutate({ id: t.id, is_paused: !t.is_paused })}
                    pausing={pauseMutation.isPending && pauseMutation.variables?.id === t.id}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <EditTemplateModal
          template={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ["admin-email-templates"] })
            setEditing(null)
          }}
        />
      )}
    </div>
  )
}

function EmailTemplateRow({
  template, onEdit, onTogglePause, pausing,
}: {
  template: EmailTemplate
  onEdit: () => void
  onTogglePause: () => void
  pausing: boolean
}) {
  return (
    <div className="py-4 flex flex-col md:flex-row gap-4 md:items-start justify-between">
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs font-semibold text-foreground">{template.key}</span>
          {template.is_internal && (
            <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
              Internal ping
            </span>
          )}
          <span
            className={cn(
              "text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded",
              template.is_paused
                ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
            )}
          >
            {template.is_paused ? "Paused" : "Sending"}
          </span>
        </div>
        <p className="text-sm text-foreground mt-1">{template.description}</p>
        <div className="flex flex-wrap gap-3 mt-2 text-xs">
          {template.placeholders.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-muted-foreground">Placeholders:</span>
              {template.placeholders.map((p) => (
                <code key={p} className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">{`{${p}}`}</code>
              ))}
            </div>
          )}
          {template.attachment_labels.length > 0 && (
            <div className="flex items-center gap-1 text-muted-foreground">
              <Paperclip size={11} />
              {template.attachment_labels.join("; ")}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={onTogglePause}
          disabled={pausing}
          className={cn(
            "h-8 px-3 rounded-lg text-xs font-medium flex items-center gap-1.5 border transition-colors disabled:opacity-50",
            template.is_paused
              ? "border-emerald-500/30 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10"
              : "border-amber-500/30 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10",
          )}
        >
          {pausing ? <Loader2 size={13} className="animate-spin" /> : template.is_paused ? <Play size={13} /> : <Pause size={13} />}
          {template.is_paused ? "Resume" : "Pause"}
        </button>
        <button
          onClick={onEdit}
          className="h-8 px-3 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors flex items-center gap-1.5"
        >
          <Mail size={13} /> Edit
        </button>
      </div>
    </div>
  )
}

function EditTemplateModal({
  template, onClose, onSaved,
}: {
  template: EmailTemplate
  onClose: () => void
  onSaved: () => void
}) {
  const [subject, setSubject] = useState(template.subject)
  const [bodyHtml, setBodyHtml] = useState(template.body_html)
  const [preview, setPreview] = useState<{ subject: string; body_html: string } | null>(null)
  const [testSentTo, setTestSentTo] = useState<string | null>(null)

  const previewMutation = useMutation({
    mutationFn: () => previewEmailTemplateApi(template.id, { subject, body_html: bodyHtml }),
    onSuccess: (data) => setPreview(data),
    onError: (err: any) => alert(err?.response?.data?.detail || "Could not render the preview"),
  })

  const sendTestMutation = useMutation({
    mutationFn: () => sendTestEmailTemplateApi(template.id, { subject, body_html: bodyHtml }),
    onSuccess: (data) => setTestSentTo(data.sent ? data.to : null),
    onError: (err: any) => alert(err?.response?.data?.detail || "Test send failed"),
  })

  const saveMutation = useMutation({
    mutationFn: () => updateEmailTemplateApi(template.id, { subject, body_html: bodyHtml }),
    onSuccess: onSaved,
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to save"),
  })

  // Render an initial preview as soon as the editor opens.
  useEffect(() => {
    previewMutation.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const dirty = subject !== template.subject || bodyHtml !== template.body_html

  return (
    <Modal title={template.name} onClose={onClose} maxWidth="sm:max-w-5xl max-w-5xl">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground -mt-1">{template.description}</p>

        {template.placeholders.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs bg-muted/50 border border-border rounded-xl px-3 py-2">
            <span className="text-muted-foreground font-medium">Available placeholders:</span>
            {template.placeholders.map((p) => (
              <code key={p} className="px-1.5 py-0.5 rounded bg-card border border-border font-mono text-foreground">{`{${p}}`}</code>
            ))}
            <span className="text-muted-foreground ml-1">— removing one of these leaves that spot blank in the real email.</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="flex flex-col gap-3">
            <Field label="Subject">
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="w-full h-10 px-3 rounded-xl border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </Field>
            <Field label="Body (HTML)">
              <textarea
                value={bodyHtml}
                onChange={(e) => setBodyHtml(e.target.value)}
                rows={16}
                spellCheck={false}
                className="w-full px-3 py-2 rounded-xl border border-border bg-background text-xs font-mono text-foreground leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/40 resize-y"
              />
            </Field>
            <div className="flex items-center gap-2">
              <button
                onClick={() => previewMutation.mutate()}
                disabled={previewMutation.isPending}
                className="h-9 px-3 rounded-xl text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors flex items-center gap-1.5 disabled:opacity-50"
              >
                {previewMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Eye size={13} />}
                Refresh preview
              </button>
              <button
                onClick={() => { setTestSentTo(null); sendTestMutation.mutate() }}
                disabled={sendTestMutation.isPending}
                className="h-9 px-3 rounded-xl text-xs font-medium border border-border text-foreground hover:bg-muted transition-colors flex items-center gap-1.5 disabled:opacity-50"
              >
                {sendTestMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                Send test to myself
              </button>
              {testSentTo && <span className="text-xs text-emerald-600 dark:text-emerald-400">Sent to {testSentTo}</span>}
            </div>
          </div>

          <div className="flex flex-col gap-1.5 min-h-[420px]">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Preview (sample data)</span>
            <div className="flex-1 border border-border rounded-xl overflow-hidden bg-white flex flex-col">
              <div className="px-3 py-2 border-b border-border bg-muted/40 text-xs text-foreground/80 truncate">
                <span className="text-muted-foreground">Subject: </span>{preview?.subject ?? "…"}
              </div>
              {preview ? (
                <iframe
                  title="Email preview"
                  srcDoc={preview.body_html}
                  sandbox=""
                  className="flex-1 w-full bg-white"
                />
              ) : (
                <div className="flex-1 flex items-center justify-center text-muted-foreground text-xs">Rendering…</div>
              )}
            </div>
          </div>
        </div>

        <ModalActions
          onCancel={onClose}
          onConfirm={() => saveMutation.mutate()}
          loading={saveMutation.isPending}
          disabled={!dirty}
          label="Save changes"
        />
      </div>
    </Modal>
  )
}
