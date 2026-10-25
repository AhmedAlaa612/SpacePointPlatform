import { useState } from "react"
import { FileText, Globe, Link2, Lock, Plus } from "lucide-react"
import type { ChecklistAttachment } from "@/types/sessions"
import type { Material } from "@/api/sessions/openings"
import { cn } from "@/lib/utils"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"

export function ChecklistAttachmentPicker({
  availableMaterials,
  onAdd,
}: {
  availableMaterials: Material[]
  onAdd: (att: ChecklistAttachment) => void
}) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<"materials" | "link">("materials")
  const [linkUrl, setLinkUrl] = useState("")
  const [linkTitle, setLinkTitle] = useState("")

  const handleAddLink = () => {
    const trimmedUrl = linkUrl.trim()
    if (!trimmedUrl) return
    onAdd({
      id: `link-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      type: "link",
      title: linkTitle.trim() || trimmedUrl,
      url: trimmedUrl,
    })
    setLinkUrl("")
    setLinkTitle("")
    setOpen(false)
  }

  const handlePickMaterial = (m: Material) => {
    onAdd({
      id: `mat-${m.id}-${Date.now()}`,
      type: "material",
      material_id: m.id,
      title: m.title,
      url: m.url || undefined,
      is_file: Boolean(m.filename),
      is_published: m.is_published,
    })
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium text-primary hover:text-primary/80 bg-primary/5 hover:bg-primary/10 border border-primary/20 transition-colors cursor-pointer"
          title="Attach material from portal or external link"
        >
          <Plus size={11} />
          <span>Attach reference</span>
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="start"
        side="bottom"
        sideOffset={6}
        className="w-72 sm:w-80 p-3 bg-popover text-popover-foreground border border-border rounded-xl shadow-2xl z-50 flex flex-col gap-2.5"
      >
        {/* Tabs */}
        <div className="flex border-b border-border pb-1.5 gap-2">
          <button
            type="button"
            onClick={() => setTab("materials")}
            className={cn(
              "text-xs font-semibold pb-1 transition-colors border-b-2 -mb-[7px] cursor-pointer",
              tab === "materials"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            Materials ({availableMaterials.length})
          </button>
          <button
            type="button"
            onClick={() => setTab("link")}
            className={cn(
              "text-xs font-semibold pb-1 transition-colors border-b-2 -mb-[7px] cursor-pointer",
              tab === "link"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            External link (Canva / Doc)
          </button>
        </div>

        {/* Tab 1: Materials from portal */}
        {tab === "materials" && (
          <div className="flex flex-col gap-1 max-h-52 overflow-y-auto pt-1">
            {availableMaterials.length === 0 ? (
              <div className="py-4 text-center text-xs text-muted-foreground">
                No materials uploaded yet.
                <p className="text-[11px] text-muted-foreground/80 mt-1">
                  Upload documents or datasheets in the Materials tab first.
                </p>
              </div>
            ) : (
              availableMaterials.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => handlePickMaterial(m)}
                  className="flex items-center justify-between gap-2 p-1.5 rounded-lg text-left hover:bg-muted transition-colors cursor-pointer text-xs"
                >
                  <div className="flex items-center gap-1.5 min-w-0 flex-1">
                    {m.filename ? (
                      <FileText size={13} className="shrink-0 text-primary" />
                    ) : (
                      <Link2 size={13} className="shrink-0 text-primary" />
                    )}
                    <span className="truncate font-medium">{m.title}</span>
                  </div>
                  <span
                    className={cn(
                      "text-[10px] px-1.5 py-0.2 rounded shrink-0 flex items-center gap-0.5 font-medium border",
                      m.is_published
                        ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
                        : "bg-muted text-muted-foreground border-border"
                    )}
                    title={m.is_published ? "Published to instructors" : "Internal only"}
                  >
                    {m.is_published ? <Globe size={9} /> : <Lock size={9} />}
                    {m.is_published ? "Published" : "Internal"}
                  </span>
                </button>
              ))
            )}
          </div>
        )}

        {/* Tab 2: Custom External Link */}
        {tab === "link" && (
          <div className="flex flex-col gap-2 pt-1">
            <input
              value={linkTitle}
              onChange={(e) => setLinkTitle(e.target.value)}
              placeholder="Title / Label (optional, e.g. Canva Slides)"
              className="w-full h-8 px-2.5 text-xs border border-border bg-background rounded-md focus:outline-none focus:border-primary"
            />
            <input
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
              placeholder="https://… (Canva, Google Doc, etc.)"
              className="w-full h-8 px-2.5 text-xs border border-border bg-background rounded-md focus:outline-none focus:border-primary"
            />
            <button
              type="button"
              onClick={handleAddLink}
              disabled={!linkUrl.trim()}
              className="w-full h-8 text-xs font-semibold bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer"
            >
              Add Link Reference
            </button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
