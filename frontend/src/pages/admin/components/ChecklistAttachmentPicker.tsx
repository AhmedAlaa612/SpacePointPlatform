import { useState, useRef } from "react"
import { FileText, Globe, Link2, Lock, Plus, Upload, Loader2, ExternalLink } from "lucide-react"
import type { ChecklistAttachment } from "@/types/sessions"
import { type Material, type MaterialOwner, addMaterialFileApi } from "@/api/sessions/openings"
import { cn, ensureAbsoluteUrl } from "@/lib/utils"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useToast } from "@/components/ui/toast"

export function ChecklistAttachmentPicker({
  availableMaterials = [],
  owner,
  onAdd,
  onMaterialUploaded,
}: {
  availableMaterials: Material[]
  owner?: MaterialOwner
  onAdd: (att: ChecklistAttachment) => void
  onMaterialUploaded?: (mat: Material) => void
}) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<"materials" | "upload" | "link">("materials")

  // Link state
  const [linkUrl, setLinkUrl] = useState("")
  const [linkTitle, setLinkTitle] = useState("")

  // Direct file upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadTitle, setUploadTitle] = useState("")
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const handleAddLink = () => {
    const trimmedUrl = linkUrl.trim()
    if (!trimmedUrl) return
    const absoluteUrl = ensureAbsoluteUrl(trimmedUrl)
    onAdd({
      id: `link-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      type: "link",
      title: linkTitle.trim() || trimmedUrl,
      url: absoluteUrl,
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

  const handleFileUpload = async () => {
    if (!uploadFile) return
    if (!owner) {
      toast.error("No cohort or program context available to upload file")
      return
    }

    try {
      setIsUploading(true)
      const title = uploadTitle.trim() || uploadFile.name
      const created = await addMaterialFileApi({
        owner,
        title,
        file: uploadFile,
        is_published: true,
      })
      toast.success("File uploaded successfully")
      onMaterialUploaded?.(created)
      onAdd({
        id: `mat-${created.id}-${Date.now()}`,
        type: "material",
        material_id: created.id,
        title: created.title,
        url: created.url || undefined,
        is_file: Boolean(created.filename),
        is_published: created.is_published,
      })
      setUploadFile(null)
      setUploadTitle("")
      setOpen(false)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to upload file")
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium text-primary hover:text-primary/80 bg-primary/5 hover:bg-primary/10 border border-primary/20 transition-colors cursor-pointer"
          title="Attach material from portal, upload a document, or add external link"
        >
          <Plus size={11} />
          <span>Attach reference</span>
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="start"
        side="bottom"
        sideOffset={6}
        className="w-[min(calc(100vw-2rem),24rem)] max-w-[calc(100vw-2rem)] p-3 bg-popover text-popover-foreground border border-border rounded-xl shadow-2xl z-50 flex flex-col gap-2.5"
      >
        {/* Tabs */}
        <div className="flex border-b border-border pb-1.5 gap-2 overflow-x-auto">
          <button
            type="button"
            onClick={() => setTab("materials")}
            className={cn(
              "text-xs font-semibold pb-1 transition-colors border-b-2 -mb-[7px] cursor-pointer whitespace-nowrap",
              tab === "materials"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            Materials ({availableMaterials.length})
          </button>
          {owner && (
            <button
              type="button"
              onClick={() => setTab("upload")}
              className={cn(
                "text-xs font-semibold pb-1 transition-colors border-b-2 -mb-[7px] cursor-pointer whitespace-nowrap",
                tab === "upload"
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              Upload file
            </button>
          )}
          <button
            type="button"
            onClick={() => setTab("link")}
            className={cn(
              "text-xs font-semibold pb-1 transition-colors border-b-2 -mb-[7px] cursor-pointer whitespace-nowrap",
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
          <div className="flex flex-col gap-1 max-h-56 overflow-y-auto pt-1">
            {availableMaterials.length === 0 ? (
              <div className="py-4 text-center text-xs text-muted-foreground">
                No materials uploaded yet.
                <p className="text-[11px] text-muted-foreground/80 mt-1">
                  Upload documents or slides directly using the Upload tab or add an External link.
                </p>
              </div>
            ) : (
              availableMaterials.map((m) => (
                <div
                  key={m.id}
                  className="flex items-center justify-between gap-2 p-1.5 rounded-lg hover:bg-muted transition-colors text-xs group"
                >
                  <button
                    type="button"
                    onClick={() => handlePickMaterial(m)}
                    className="flex items-center gap-1.5 min-w-0 flex-1 text-left cursor-pointer"
                    title={`Attach: ${m.title}`}
                  >
                    {m.filename ? (
                      <FileText size={13} className="shrink-0 text-primary" />
                    ) : (
                      <Link2 size={13} className="shrink-0 text-primary" />
                    )}
                    <span className="truncate font-medium group-hover:text-primary transition-colors">
                      {m.title}
                    </span>
                  </button>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {m.url && (
                      <a
                        href={ensureAbsoluteUrl(m.url)}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="text-[10px] text-muted-foreground hover:text-primary p-0.5 rounded transition-colors"
                        title="Open preview in new tab"
                      >
                        <ExternalLink size={11} />
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={() => handlePickMaterial(m)}
                      className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded flex items-center gap-0.5 font-medium border cursor-pointer",
                        m.is_published
                          ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 hover:bg-emerald-500/20"
                          : "bg-muted text-muted-foreground border-border hover:bg-muted/80"
                      )}
                      title="Click to attach"
                    >
                      {m.is_published ? <Globe size={9} /> : <Lock size={9} />}
                      <span>Attach</span>
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab 2: Upload file directly */}
        {tab === "upload" && (
          <div className="flex flex-col gap-2.5 pt-1">
            <input
              type="file"
              ref={fileInputRef}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) {
                  setUploadFile(f)
                  if (!uploadTitle) {
                    setUploadTitle(f.name.replace(/\.[^/.]+$/, ""))
                  }
                }
              }}
              className="hidden"
            />

            <div
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "flex flex-col items-center justify-center p-4 border border-dashed rounded-lg cursor-pointer transition-colors text-center",
                uploadFile
                  ? "border-primary bg-primary/5 text-primary"
                  : "border-border hover:border-primary/50 text-muted-foreground hover:text-foreground"
              )}
            >
              <Upload size={18} className="mb-1" />
              {uploadFile ? (
                <div className="text-xs font-semibold truncate max-w-[240px]">
                  {uploadFile.name}
                  <span className="block text-[10px] font-normal text-muted-foreground">
                    ({(uploadFile.size / 1024).toFixed(0)} KB) — Click to change
                  </span>
                </div>
              ) : (
                <div className="text-xs">
                  <span className="font-semibold text-primary">Click to choose a file</span> (PDF, slides, doc)
                </div>
              )}
            </div>

            <input
              value={uploadTitle}
              onChange={(e) => setUploadTitle(e.target.value)}
              placeholder="Title / Label (e.g. Workshop Presentation)"
              className="w-full h-8 px-2.5 text-xs border border-border bg-background rounded-md focus:outline-none focus:border-primary"
            />

            <button
              type="button"
              onClick={handleFileUpload}
              disabled={!uploadFile || isUploading}
              className="w-full h-8 text-xs font-semibold bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
            >
              {isUploading ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>Uploading…</span>
                </>
              ) : (
                <>
                  <Upload size={12} />
                  <span>Upload & Attach</span>
                </>
              )}
            </button>
          </div>
        )}

        {/* Tab 3: Custom External Link */}
        {tab === "link" && (
          <div className="flex flex-col gap-2 pt-1">
            <input
              value={linkTitle}
              onChange={(e) => setLinkTitle(e.target.value)}
              placeholder="Title / Label (e.g. Canva Intro Slides)"
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
