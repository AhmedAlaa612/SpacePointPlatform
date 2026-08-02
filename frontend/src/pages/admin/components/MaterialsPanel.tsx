import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FileText, Link2, Plus, Trash2, Upload } from "lucide-react"
import {
  addMaterialFileApi,
  addMaterialLinkApi,
  deleteMaterialApi,
  getMaterialsApi,
  type MaterialOwner,
} from "@/api/sessions/openings"
import { useToast } from "@/components/ui/toast"
import { InheritedBadge } from "@/pages/admin/components/InheritedFrom"

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
  const [error, setError] = useState("")

  const key = ["materials", JSON.stringify(owner)]
  const { data: materials = [] } = useQuery({ queryKey: key, queryFn: () => getMaterialsApi(owner) })

  const invalidate = () => qc.invalidateQueries({ queryKey: key })
  const onError = (e: any) => setError(e?.response?.data?.detail ?? "Could not save that")

  const addLink = useMutation({
    mutationFn: () => addMaterialLinkApi({ owner, title: title || url, url }),
    onSuccess: () => { toast.success("Link added"); setError(""); setTitle(""); setUrl(""); invalidate() },
    onError,
  })
  const addFile = useMutation({
    mutationFn: (file: File) => addMaterialFileApi({ owner, title: title || file.name, file }),
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
        {materials.map((m) => (
          <div
            key={m.id}
            className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/50 px-3 py-2"
          >
            <span className="flex items-center gap-2 min-w-0">
              {m.filename ? <FileText size={14} className="shrink-0 text-muted-foreground" />
                          : <Link2 size={14} className="shrink-0 text-muted-foreground" />}
              {m.url ? (
                <a href={m.url} target="_blank" rel="noreferrer"
                   className="text-sm text-foreground truncate hover:underline">{m.title}</a>
              ) : (
                <span className="text-sm text-foreground truncate">{m.title}</span>
              )}
            </span>
            <button
              onClick={() => remove.mutate(m.id)}
              className="p-1 text-muted-foreground hover:text-red-600 shrink-0"
              aria-label={`Remove ${m.title}`}
            ><Trash2 size={14} /></button>
          </div>
        ))}
        {materials.length === 0 && (
          <p className="text-sm text-muted-foreground">Nothing here yet.</p>
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <input
          placeholder="Title (optional)" value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="flex-1 min-w-[8rem] h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
        />
        <input
          placeholder="https://…" value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1 min-w-[10rem] h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
        />
        <button
          onClick={() => { setError(""); addLink.mutate() }}
          disabled={!url || addLink.isPending}
          className="h-9 px-3 border border-border text-foreground text-sm rounded-lg hover:bg-muted disabled:opacity-40"
        ><Plus size={14} className="inline mr-1" /> Link</button>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={addFile.isPending}
          className="h-9 px-3 border border-border text-foreground text-sm rounded-lg hover:bg-muted disabled:opacity-40"
        ><Upload size={14} className="inline mr-1" /> {addFile.isPending ? "Uploading…" : "File"}</button>
        <input
          ref={fileRef} type="file" className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) { setError(""); addFile.mutate(f) }
            e.target.value = ""
          }}
        />
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
