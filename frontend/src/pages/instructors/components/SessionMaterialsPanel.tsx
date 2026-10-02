import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ChevronDown, ExternalLink, FileText, Link2, Paperclip, Video as VideoIcon } from "lucide-react"
import { getSessionMaterialsApi, type Material } from "@/api/sessions/openings"
import { Card, CardContent } from "@/components/ui/card"
import { cn, ensureAbsoluteUrl } from "@/lib/utils"
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal"

/**
 * What this session's instructor should read before teaching (I5-6).
 *
 * Resolved server-side: the session's own materials, else the cohort's, else
 * the program's — override, not merge. Renders nothing when there are none,
 * so sessions without materials look exactly as they did before this existed.
 *
 * `Session.material_url` (the single pre-existing link) is untouched and still
 * shown by the page above; this is the richer list the CEO asked for.
 */
export function SessionMaterialsPanel({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(true)
  const [previewMedia, setPreviewMedia] = useState<{
    title: string
    type: "pdf" | "video"
    url: string
  } | null>(null)

  const { data } = useQuery({
    queryKey: ["session-materials", sessionId],
    queryFn: () => getSessionMaterialsApi(sessionId),
  })

  if (!data || data.materials.length === 0) return null

  const handleOpenMaterial = (e: React.MouseEvent, m: Material) => {
    if (!m.url) return
    const isPdf = Boolean(m.filename?.toLowerCase().endsWith(".pdf") || m.url.toLowerCase().includes(".pdf"))
    const isVideo = Boolean(m.filename?.toLowerCase().match(/\.(mp4|webm|mov)$/) || m.url.toLowerCase().match(/\.(mp4|webm|mov)$/))

    if (isPdf) {
      e.preventDefault()
      setPreviewMedia({ title: m.title, type: "pdf", url: ensureAbsoluteUrl(m.url) })
    } else if (isVideo) {
      e.preventDefault()
      setPreviewMedia({ title: m.title, type: "video", url: ensureAbsoluteUrl(m.url) })
    }
  }

  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-3">
        <div
          onClick={() => setOpen((v) => !v)}
          className="flex items-center justify-between gap-2 cursor-pointer select-none group"
        >
          <div className="flex items-center gap-2">
            <ChevronDown className={cn("size-4 text-muted-foreground transition-transform duration-200 group-hover:text-foreground", !open && "-rotate-90")} />
            <p className="flex items-center gap-2 text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
              <Paperclip size={15} /> Materials
            </p>
          </div>
          {data.level !== "session" && (
            <span className="text-xs text-muted-foreground">
              from the {data.level}
            </span>
          )}
        </div>

        {open && (
          <div className="flex flex-col gap-1.5">
            {data.materials.map((m) => {
              const isPdf = Boolean(m.filename?.toLowerCase().endsWith(".pdf") || m.url?.toLowerCase().includes(".pdf"))
              const isVideo = Boolean(m.filename?.toLowerCase().match(/\.(mp4|webm|mov)$/) || m.url?.toLowerCase().match(/\.(mp4|webm|mov)$/))
              const isMedia = isPdf || isVideo

              return (
                <a
                  key={m.id}
                  href={m.url ? ensureAbsoluteUrl(m.url) : "#"}
                  target={isMedia ? undefined : "_blank"}
                  rel="noreferrer"
                  onClick={(e) => handleOpenMaterial(e, m)}
                  className="flex items-center justify-between gap-2 rounded-xl border border-border bg-background/50 px-3 py-2 hover:bg-muted/60 transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {isVideo ? (
                      <VideoIcon size={14} className="shrink-0 text-muted-foreground" />
                    ) : m.filename || isPdf ? (
                      <FileText size={14} className="shrink-0 text-muted-foreground" />
                    ) : (
                      <Link2 size={14} className="shrink-0 text-muted-foreground" />
                    )}
                    <span className="min-w-0">
                      <span className="block text-sm text-foreground truncate">{m.title}</span>
                      {m.notes && (
                        <span className="block text-xs text-muted-foreground truncate">{m.notes}</span>
                      )}
                    </span>
                  </div>
                  {isMedia ? (
                    <span className="text-[11px] font-medium text-primary shrink-0">View</span>
                  ) : (
                    <ExternalLink size={12} className="text-muted-foreground shrink-0" />
                  )}
                </a>
              )
            })}
          </div>
        )}
      </CardContent>

      <MediaPreviewModal
        open={!!previewMedia}
        onClose={() => setPreviewMedia(null)}
        title={previewMedia?.title ?? "Material preview"}
        type={previewMedia?.type ?? "pdf"}
        url={previewMedia?.url}
      />
    </Card>
  )
}
