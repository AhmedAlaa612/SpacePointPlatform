import { useState } from "react"
import { Check, Copy, ExternalLink, Link2, RefreshCw, Share2 } from "lucide-react"
import { WEBSITE_BASE_URL } from "@/components/operations/OrgManagementModals"
import { useToast } from "@/components/ui/toast"

export function SharePagePopover({
  publicUrl,
  previewToken,
  isPublished,
  onRegenerate,
  regenerating = false,
}: {
  publicUrl: string
  previewToken?: string | null
  isPublished: boolean
  onRegenerate?: () => void
  regenerating?: boolean
}) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState<"public" | "preview" | null>(null)

  const previewUrl = previewToken ? `${WEBSITE_BASE_URL}/preview?t=${previewToken}` : ""

  const copy = async (kind: "public" | "preview", value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(kind)
      toast.success(kind === "public" ? "Public URL copied" : "Private preview link copied")
      setTimeout(() => setCopied((cur) => (cur === kind ? null : cur)), 2000)
    } catch {
      toast.error("Could not copy link")
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer"
      >
        <Share2 size={13} /> Share / Preview
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-80 rounded-[10px] border border-border bg-card p-4 shadow-xl z-50 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-foreground">Share &amp; Preview</span>
              <span
                className={
                  isPublished
                    ? "text-[10px] font-bold px-2 py-0.5 rounded-[10px] bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                    : "text-[10px] font-bold px-2 py-0.5 rounded-[10px] bg-muted text-muted-foreground"
                }
              >
                {isPublished ? "Published" : "Draft"}
              </span>
            </div>

            {isPublished && (
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1">
                  <Link2 size={11} /> Public URL
                </span>
                <div className="flex items-center gap-1.5">
                  <input
                    readOnly
                    value={publicUrl}
                    className="flex-1 h-8 px-2.5 text-[11px] font-mono rounded-[10px] border border-border bg-background text-foreground"
                  />
                  <button
                    type="button"
                    onClick={() => copy("public", publicUrl)}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-[10px] border border-border bg-background hover:bg-muted cursor-pointer"
                    title="Copy Public URL"
                  >
                    {copied === "public" ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                  </button>
                  <a
                    href={publicUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="h-8 w-8 inline-flex items-center justify-center rounded-[10px] border border-border bg-background hover:bg-muted"
                    title="Open Public Page"
                  >
                    <ExternalLink size={13} />
                  </a>
                </div>
              </div>
            )}

            {previewUrl && (
              <div className="space-y-1">
                <span className="text-[11px] font-semibold text-muted-foreground">
                  Private Preview Link
                </span>
                <div className="flex items-center gap-1.5">
                  <input
                    readOnly
                    value={previewUrl}
                    className="flex-1 h-8 px-2.5 text-[11px] font-mono rounded-[10px] border border-border bg-background text-foreground"
                  />
                  <button
                    type="button"
                    onClick={() => copy("preview", previewUrl)}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-[10px] border border-border bg-background hover:bg-muted cursor-pointer"
                    title="Copy Private Preview Link"
                  >
                    {copied === "preview" ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                  </button>
                  <a
                    href={previewUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="h-8 w-8 inline-flex items-center justify-center rounded-[10px] border border-border bg-background hover:bg-muted"
                    title="Open Private Preview"
                  >
                    <ExternalLink size={13} />
                  </a>
                </div>
                {onRegenerate && (
                  <button
                    type="button"
                    disabled={regenerating}
                    onClick={() => {
                      if (window.confirm("Regenerate private preview link? Any previously shared preview link will stop working.")) {
                        onRegenerate()
                      }
                    }}
                    className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
                  >
                    <RefreshCw size={11} className={regenerating ? "animate-spin" : ""} />
                    {regenerating ? "Regenerating…" : "Revoke & regenerate link"}
                  </button>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
