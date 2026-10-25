import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, FileText, Globe, Link2, Lock, Plus, Trash2, Upload, Video as VideoIcon } from "lucide-react"
import {
  addMaterialFileApi,
  addMaterialLinkApi,
  deleteMaterialApi,
  getMaterialsApi,
  updateMaterialApi,
  type MaterialOwner,
} from "@/api/sessions/openings"
import { useToast } from "@/components/ui/toast"
import { InheritedBadge } from "@/pages/admin/components/InheritedFrom"
import { cn, ensureAbsoluteUrl } from "@/lib/utils"
import { MediaPreviewModal } from "@/components/media/MediaPreviewModal"

/**
 * Teaching materials at one level of program → cohort → session (I5-6).
 *
 * One component, mounted three times with a different owner — the levels
 * differ only in which id they carry, so three near-identical screens would
 * be three places to fix the next bug.
 *
 * **Override, not merge**, which the caption says out loud: adding anything
 * at this level replaces what would otherwise be inherited, rather than
 * appending to it. That is what makes it possible to *remove* a program file
 * for one cohort, and it is the part people get wrong when reading the word
 * "override".
 */
export function MaterialsPanel({ owner, inheritedNote, level }: {
  owner: MaterialOwner
  /** e.g. "Sessions inherit these unless the cohort has its own." */
  inheritedNote?: string
  /** Where this level inherits FROM, for the shared badge. Omit at the
   *  program level — nothing sits above it to inherit from. */
  level?: "program" | "cohort"
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [title, setTitle] = useState("")
  const [url, setUrl] = useState("")
  const [publishNew, setPublishNew] = useState(false)
  const [error, setError] = useState("")
  const [previewMedia, setPreviewMedia] = useState<{
    title: string
    type: "pdf" | "video"
    url: string
  } | null>(null)

  const key = ["materials", JSON.stringify(owner)]
  const { data: materials = [] } = useQuery({ queryKey: key, queryFn: () => getMaterialsApi(owner) })

  const invalidate = () => qc.invalidateQueries({ queryKey: key })
  const onError = (e: any) => setError(e?.response?.data?.detail ?? "Could not save that")

  const togglePublish = useMutation({
    mutationFn: ({ id, is_published }: { id: string; is_published: boolean }) =>
      updateMaterialApi(id, { is_published }),
    onSuccess: (_, vars) => {
      toast.success(vars.is_published ? "Published to instructors" : "Set to internal only")
      invalidate()
    },
    onError,
  })

  const addLink = useMutation({
    mutationFn: () => addMaterialLinkApi({ owner, title: title || url, url, is_published: publishNew }),
    onSuccess: () => { toast.success("Link added"); setError(""); setTitle(""); setUrl(""); invalidate() },
    onError,
  })
  const addFile = useMutation({
    mutationFn: (file: File) => addMaterialFileApi({ owner, title: title || file.name, file, is_published: publishNew }),
    onSuccess: () => { toast.success("File added"); setError(""); setTitle(""); invalidate() },
    onError,
  })
  const remove = useMutation({
    mutationFn: deleteMaterialApi,
    onSuccess: () => { toast.success("Material removed"); invalidate() },
    onError,
  })

  return (
    <div className="flex flex-col gap-3">
      <div>
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-foreground">Materials</p>
          {/* Same pill the other three inheritance surfaces use — this panel
              used to say it in prose only (2026-08-02). Only shown at the
              levels that actually inherit; the program is the root. */}
          {level && <InheritedBadge level={level} overridden={materials.length > 0} />}
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          Files and links. {inheritedNote}{" "}
          Anything here <strong>replaces</strong> what would otherwise apply, rather than adding to it.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        {materials.map((m) => {
          const isPdf = Boolean(m.filename?.toLowerCase().endsWith(".pdf") || m.url?.toLowerCase().includes(".pdf"))
          const isVideo = Boolean(m.filename?.toLowerCase().match(/\.(mp4|webm|mov)$/) || m.url?.toLowerCase().match(/\.(mp4|webm|mov)$/))
          const isMedia = isPdf || isVideo

          return (
            <div
              key={m.id}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-3 rounded-xl border border-border bg-background/50 p-2.5 sm:px-3 sm:py-2"
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                {isVideo ? (
                  <VideoIcon size={14} className="shrink-0 text-muted-foreground" />
                ) : m.filename || isPdf ? (
                  <FileText size={14} className="shrink-0 text-muted-foreground" />
                ) : (
                  <Link2 size={14} className="shrink-0 text-muted-foreground" />
                )}
                {m.url ? (
                  isMedia ? (
                    <button
                      type="button"
                      onClick={() => setPreviewMedia({ title: m.title, type: isPdf ? "pdf" : "video", url: ensureAbsoluteUrl(m.url!) })}
                      className="text-sm text-foreground truncate hover:underline hover:text-primary transition-colors text-left"
                    >
                      {m.title}
                    </button>
                  ) : (
                    <a href={ensureAbsoluteUrl(m.url)} target="_blank" rel="noreferrer"
                       className="text-sm text-foreground truncate hover:underline">{m.title}</a>
                  )
                ) : (
                  <span className="text-sm text-foreground truncate">{m.title}</span>
                )}
              </div>
              <div className="flex items-center justify-between sm:justify-end gap-2 shrink-0 w-full sm:w-auto pt-1.5 sm:pt-0 border-t sm:border-t-0 border-border/40">
                {/* Publish to instructors toggle */}
                <button
                  type="button"
                  onClick={() => togglePublish.mutate({ id: m.id, is_published: !m.is_published })}
                  disabled={togglePublish.isPending}
                  title={m.is_published ? "Click to set to internal only" : "Click to publish to instructors"}
                  className={cn(
                    "flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors border",
                    m.is_published
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20"
                      : "bg-muted/80 text-muted-foreground border-border hover:bg-muted hover:text-foreground"
                  )}
                >
                  {m.is_published ? (
                    <>
                      <Globe size={11} className="text-emerald-600 dark:text-emerald-400" />
                      <span>Published to instructors</span>
                    </>
                  ) : (
                    <>
                      <Lock size={11} />
                      <span>Internal only</span>
                    </>
                  )}
                </button>

                <div className="flex items-center gap-1.5">
                  {m.url && (
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(ensureAbsoluteUrl(m.url!))
                        toast.success("Link copied to clipboard")
                      }}
                      className="p-1 text-muted-foreground hover:text-foreground shrink-0 cursor-pointer"
                      title="Copy link to clipboard"
                    >
                      <Copy size={13} />
                    </button>
                  )}
                  {m.url && isMedia && (
                    <button
                      type="button"
                      onClick={() => setPreviewMedia({ title: m.title, type: isPdf ? "pdf" : "video", url: ensureAbsoluteUrl(m.url!) })}
                      className="text-xs text-primary font-medium hover:underline px-1.5 py-1"
                    >
                      View
                    </button>
                  )}
                  <button
                    onClick={() => remove.mutate(m.id)}
                    className="p-1 text-muted-foreground hover:text-red-600 shrink-0"
                    aria-label={`Remove ${m.title}`}
                  ><Trash2 size={14} /></button>
                </div>
              </div>
            </div>
          )
        })}
        {materials.length === 0 && (
          <p className="text-sm text-muted-foreground">Nothing here yet.</p>
        )}
      </div>

      <div className="flex flex-col gap-2 pt-1">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <input
            placeholder="Title (optional)" value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="flex-1 min-w-0 h-9 px-2.5 border border-border bg-background text-foreground rounded-lg text-sm"
          />
          <input
            placeholder="https://… (e.g. Canva, document link)" value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="flex-1 min-w-0 h-9 px-2.5 border border-border bg-background text-foreground rounded-lg text-sm"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setError(""); addLink.mutate() }}
              disabled={!url || addLink.isPending}
              className="flex-1 sm:flex-none h-9 px-3 border border-border text-foreground text-sm rounded-lg hover:bg-muted disabled:opacity-40"
            ><Plus size={14} className="inline mr-1" /> Link</button>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={addFile.isPending}
              className="flex-1 sm:flex-none h-9 px-3 border border-border text-foreground text-sm rounded-lg hover:bg-muted disabled:opacity-40"
            ><Upload size={14} className="inline mr-1" /> {addFile.isPending ? "Uploading…" : "File"}</button>
          </div>
          <input
            ref={fileRef} type="file" className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) { setError(""); addFile.mutate(f) }
              e.target.value = ""
            }}
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={publishNew}
              onChange={(e) => setPublishNew(e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary size-3.5"
            />
            <span>Publish to instructors upon upload</span>
          </label>
        </div>
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <MediaPreviewModal
        open={!!previewMedia}
        onClose={() => setPreviewMedia(null)}
        title={previewMedia?.title ?? "Material preview"}
        type={previewMedia?.type ?? "pdf"}
        url={previewMedia?.url}
      />
    </div>
  )
}
