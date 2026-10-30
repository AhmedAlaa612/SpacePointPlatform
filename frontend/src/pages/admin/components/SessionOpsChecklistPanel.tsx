import type React from "react"
import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CheckCircle2,
  Circle,
  ExternalLink,
  FileText,
  ImageIcon,
  Link2,
  Lock,
  Upload,
} from "lucide-react"
import { getInternalChecklistApi, setInternalChecklistProgressApi } from "@/api/sessions/day"
import { uploadSessionReportApi } from "@/api/sessions/delivery"
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal"
import { useToast } from "@/components/ui/toast"
import { cn, ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"
import type { ChecklistAttachment, OpsChecklistItem } from "@/types/sessions"

/** Renders markdown hyperlinks like [Label](url) or raw URLs as clickable links */
function FormattedText({ text }: { text: string }) {
  if (!text) return null

  // Regex to match markdown links [label](url) or bare urls https?://...
  const parts: (string | React.ReactNode)[] = []
  const mdRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s]+)/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = mdRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    if (match[1] && match[2]) {
      // Markdown link [label](url)
      parts.push(
        <a
          key={match.index}
          href={ensureAbsoluteUrl(match[2])}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline hover:opacity-80 inline-flex items-center gap-0.5 font-medium"
          onClick={(e) => e.stopPropagation()}
        >
          {match[1]}
          <ExternalLink size={11} className="inline ml-0.5" />
        </a>
      )
    } else if (match[3]) {
      // Bare URL
      parts.push(
        <a
          key={match.index}
          href={ensureAbsoluteUrl(match[3])}
          target="_blank"
          rel="noreferrer"
          className="text-primary underline hover:opacity-80 inline-flex items-center gap-0.5 font-medium"
          onClick={(e) => e.stopPropagation()}
        >
          {match[3]}
          <ExternalLink size={11} className="inline ml-0.5" />
        </a>
      )
    }
    lastIndex = mdRegex.lastIndex
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return <span>{parts}</span>
}

export function SessionOpsChecklistPanel({
  sessionId,
  cohortId,
}: {
  sessionId: string
  cohortId: string
}) {
  const qc = useQueryClient()
  const [previewMedia, setPreviewMedia] = useState<{
    title: string
    type: "pdf" | "video" | "image"
    url: string
  } | null>(null)

  const queryKey = ["session-internal-checklist", sessionId]
  const { data: items = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => getInternalChecklistApi(sessionId),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey })

  const doneCount = items.filter((i) => i.is_done).length
  const totalCount = items.length

  if (isLoading) {
    return (
      <div className="p-4 flex items-center justify-center text-sm text-muted-foreground">
        Loading checklist…
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="p-6 text-center border border-dashed border-border rounded-xl">
        <p className="text-sm font-medium text-foreground">No checklist items configured</p>
        <p className="text-xs text-muted-foreground mt-1">
          Items configured in the Program or Cohort template automatically resolve here.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Header with progress */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-border">
        <div>
          <p className="text-sm font-semibold text-foreground">Internal Checklist</p>
          <p className="text-xs text-muted-foreground">
            Complete preparations, print documents, and review operations for this session.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-center shrink-0">
          <span className="text-xs font-semibold tabular-nums text-foreground bg-muted px-2.5 py-1 rounded-full">
            {doneCount} / {totalCount} completed
          </span>
        </div>
      </div>

      {/* Checklist items */}
      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <ChecklistRow
            key={item.item_id}
            item={item}
            sessionId={sessionId}
            cohortId={cohortId}
            onChanged={invalidate}
            onPreview={(preview) => setPreviewMedia(preview)}
          />
        ))}
      </div>

      <MediaPreviewModal
        open={!!previewMedia}
        onClose={() => setPreviewMedia(null)}
        title={previewMedia?.title ?? "Document preview"}
        type={previewMedia?.type === "video" ? "video" : "pdf"}
        url={previewMedia?.url}
      />
    </div>
  )
}

function ChecklistRow({
  item,
  sessionId,
  cohortId,
  onChanged,
  onPreview,
}: {
  item: OpsChecklistItem
  sessionId: string
  cohortId: string
  onChanged: () => void
  onPreview: (preview: { title: string; type: "pdf" | "video" | "image"; url: string }) => void
}) {
  const toast = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const toggleMutation = useMutation({
    mutationFn: (newDone: boolean) => {
      const nextSubsDone = newDone ? (item.sub_items || []).map((s) => s.id) : []
      return setInternalChecklistProgressApi(sessionId, item.item_id, {
        is_done: newDone,
        proof_report_id: item.proof_report_id,
        note: item.note,
        completed_sub_items: (item.sub_items && item.sub_items.length > 0) ? nextSubsDone : item.completed_sub_items,
      })
    },
    onSuccess: onChanged,
    onError: (e) => toast.error(getErrorMessage(e, "Could not update status")),
  })

  const toggleSubItemMutation = useMutation({
    mutationFn: (subId: string) => {
      const currentDone = item.completed_sub_items || []
      const nextDone = currentDone.includes(subId)
        ? currentDone.filter((id) => id !== subId)
        : [...currentDone, subId]

      const allRequired = (item.sub_items || []).filter((s) => s.is_required !== false)
      const allRequiredDone = allRequired.length > 0 && allRequired.every((s) => nextDone.includes(s.id))
      const autoIsDone = allRequired.length > 0 ? allRequiredDone : item.is_done

      return setInternalChecklistProgressApi(sessionId, item.item_id, {
        is_done: autoIsDone,
        proof_report_id: item.proof_report_id,
        note: item.note,
        completed_sub_items: nextDone,
      })
    },
    onSuccess: onChanged,
    onError: (e) => toast.error(getErrorMessage(e, "Could not update sub-topic status")),
  })

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const report = await uploadSessionReportApi(cohortId, {
        file,
        sessionId,
        notes: `Proof for: ${item.title}`,
      })
      await setInternalChecklistProgressApi(sessionId, item.item_id, {
        is_done: true,
        proof_report_id: report.id,
        note: item.note,
      })
      toast.success("Proof uploaded and item completed")
      onChanged()
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to upload proof"))
    } finally {
      setUploading(false)
      e.target.value = ""
    }
  }

  const attachments: ChecklistAttachment[] =
    item.attachments && item.attachments.length > 0
      ? item.attachments
      : item.material_url || item.link_url
      ? [
          {
            id: "legacy",
            type: item.material_url ? "material" : "link",
            title: item.material_title || (item.material_url ? "Document" : "Link"),
            url: item.material_url || item.link_url,
            is_file: Boolean(item.material_url),
            is_published: true,
            has_access: true,
          },
        ]
      : []

  const handleOpenAttachment = (att: ChecklistAttachment, e: React.MouseEvent) => {
    if (att.has_access === false) {
      e.preventDefault()
      toast.error(att.access_denied_message || "You don't have access to this document, please contact the operations team.")
      return
    }
    if (!att.url) return
    const isPdf = Boolean(
      att.url.toLowerCase().endsWith(".pdf") ||
        att.url.toLowerCase().includes(".pdf") ||
        (att.title && att.title.toLowerCase().endsWith(".pdf"))
    )
    if (isPdf) {
      e.preventDefault()
      onPreview({ title: att.title || "Document", type: "pdf", url: ensureAbsoluteUrl(att.url) })
    }
  }

  return (
    <div
      className={cn(
        "flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-xl border transition-all",
        item.is_done
          ? "bg-muted/30 border-border/60 opacity-90"
          : "bg-card border-border hover:border-border/80 shadow-xs"
      )}
    >
      {/* Left section: checkbox + text + attachment pill */}
      <div className="flex items-start gap-3 min-w-0 flex-1">
        <button
          type="button"
          onClick={() => toggleMutation.mutate(!item.is_done)}
          disabled={toggleMutation.isPending}
          className="mt-0.5 text-muted-foreground hover:text-foreground shrink-0 cursor-pointer transition-colors"
          title={item.is_done ? "Mark as incomplete" : "Mark as completed"}
        >
          {item.is_done ? (
            <CheckCircle2 size={19} className="text-emerald-600 dark:text-emerald-400" />
          ) : (
            <Circle size={19} className="text-muted-foreground hover:text-primary" />
          )}
        </button>

        <div className="min-w-0 flex-1 flex flex-col gap-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={cn(
                "text-sm font-medium transition-colors",
                item.is_done ? "line-through text-muted-foreground" : "text-foreground"
              )}
            >
              <FormattedText text={item.title} />
            </span>

            {item.requires_proof && (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 px-2 py-0.5 rounded-full border border-amber-200 dark:border-amber-500/20">
                <ImageIcon size={11} /> Photo proof required
              </span>
            )}
          </div>

          {item.description && (
            <p className="text-xs text-muted-foreground">
              <FormattedText text={item.description} />
            </p>
          )}

          {/* Attached Materials / External Links Pills */}
          {attachments.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
              {attachments.map((att, attIdx) => {
                const isPdf = Boolean(
                  att.url &&
                    (att.url.toLowerCase().endsWith(".pdf") ||
                      att.url.toLowerCase().includes(".pdf") ||
                      (att.title && att.title.toLowerCase().endsWith(".pdf")))
                )
                const isFile = Boolean(att.is_file || isPdf)
                const isRestricted = att.has_access === false

                return (
                  <a
                    key={att.id || attIdx}
                    href={att.url ? ensureAbsoluteUrl(att.url) : "#"}
                    target={att.url ? "_blank" : undefined}
                    rel="noreferrer"
                    onClick={(e) => handleOpenAttachment(att, e)}
                    className={cn(
                      "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors border cursor-pointer max-w-full",
                      isRestricted
                        ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 hover:bg-amber-500/15"
                        : isFile
                        ? "bg-primary/10 text-primary hover:bg-primary/15 border-primary/20"
                        : "bg-muted text-foreground hover:bg-muted/80 border-border"
                    )}
                    title={isRestricted ? (att.access_denied_message || "Restricted document") : undefined}
                  >
                    {isRestricted ? (
                      <Lock size={12} className="shrink-0 text-amber-500" />
                    ) : isFile ? (
                      <FileText size={12} className="shrink-0 text-primary" />
                    ) : (
                      <Link2 size={12} className="shrink-0 text-muted-foreground" />
                    )}
                    <span className="truncate max-w-[180px] sm:max-w-xs md:max-w-md">
                      {att.title || (isFile ? "Document" : "Open Link")}
                    </span>
                    {att.is_published === false && (
                      <span className="text-[10px] uppercase tracking-wider font-bold px-1 py-0.2 bg-amber-500/15 text-amber-600 dark:text-amber-400 rounded">
                        Internal
                      </span>
                    )}
                  </a>
                )
              })}
            </div>
          )}

          {/* Sub-topics / Checklist steps */}
          {item.sub_items && item.sub_items.length > 0 && (
            <div className="flex flex-col gap-1.5 pt-2 pl-2 border-l-2 border-border/70 ml-0.5 mt-1">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                <span className="text-primary font-bold">↳</span> Sub-topics (
                {(item.completed_sub_items || []).filter((id) => (item.sub_items || []).some((s) => s.id === id)).length} / {item.sub_items.length})
              </span>
              {item.sub_items.map((sub, sIdx) => {
                const isSubDone = (item.completed_sub_items || []).includes(sub.id)
                return (
                  <div key={sub.id || sIdx} className="flex items-start gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => toggleSubItemMutation.mutate(sub.id)}
                      disabled={toggleSubItemMutation.isPending}
                      className="text-muted-foreground hover:text-foreground shrink-0 cursor-pointer transition-colors mt-0.5"
                      title={isSubDone ? "Mark incomplete" : "Mark completed"}
                    >
                      {isSubDone ? (
                        <CheckCircle2 size={15} className="text-emerald-600 dark:text-emerald-400" />
                      ) : (
                        <Circle size={15} className="text-muted-foreground hover:text-primary" />
                      )}
                    </button>
                    <span className={cn("transition-colors min-w-0 break-words", isSubDone && "line-through text-muted-foreground")}>
                      <FormattedText text={sub.title} />
                      {sub.is_required === false && <span className="text-[10px] text-muted-foreground"> · optional</span>}
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Completed by footer */}
          {item.is_done && item.completed_by_name && (
            <p className="text-[11px] text-muted-foreground/80 mt-0.5">
              Completed by {item.completed_by_name}
              {item.updated_at && ` · ${new Date(item.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
            </p>
          )}
        </div>
      </div>

      {/* Right section: Proof upload / View proof button */}
      <div className="flex items-center gap-2 shrink-0 self-start sm:self-center pl-8 sm:pl-0 pt-1 sm:pt-0 border-t sm:border-t-0 border-border/30 w-full sm:w-auto justify-end">
        {item.proof_url ? (
          <button
            type="button"
            onClick={() =>
              onPreview({
                title: `Proof: ${item.title}`,
                type: "image",
                url: ensureAbsoluteUrl(item.proof_url!),
              })
            }
            className="flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 hover:bg-emerald-100 border border-emerald-200 dark:border-emerald-500/20 px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
          >
            <ImageIcon size={12} /> View Proof
          </button>
        ) : (
          item.requires_proof && (
            <div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="flex items-center gap-1.5 text-xs font-medium text-foreground bg-muted hover:bg-muted/80 border border-border px-2.5 py-1 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
              >
                <Upload size={12} /> {uploading ? "Uploading…" : "Upload Proof"}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,.pdf"
                className="hidden"
                onChange={handleFileUpload}
              />
            </div>
          )
        )}
      </div>
    </div>
  )
}
