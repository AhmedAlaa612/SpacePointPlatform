import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, FileText, Link2, Pencil, Plus, Trash2, Upload } from "lucide-react"
import {
  addLibraryLinkApi, createLibraryModuleApi, deleteLibraryModuleApi, deleteLibraryResourceApi,
  facilitatorListLibraryApi, replaceLibraryFileApi, updateLibraryResourceApi, uploadLibraryResourceApi,
} from "@/api/instructors/facilitator"
import type { LibraryResource } from "@/types/instructors"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

function ResourceRow({ r, onEdit, onDelete }: { r: LibraryResource; onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border bg-background">
      <FileText className="text-primary shrink-0" size={18} />
      <a
        href={r.file_url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-sm flex-1 truncate hover:text-primary flex items-center gap-1.5 min-w-0"
      >
        <span className="truncate">{r.title}</span>
        {r.resource_type !== "link" && (
          <span className="text-muted-foreground shrink-0 text-xs">({r.format})</span>
        )}
        <ExternalLink size={12} className="shrink-0 text-muted-foreground" />
      </a>
      <button onClick={onEdit} className="p-1 text-muted-foreground hover:text-primary">
        <Pencil size={14} />
      </button>
      <button onClick={onDelete} className="p-1 text-muted-foreground hover:text-destructive">
        <Trash2 size={14} />
      </button>
    </div>
  )
}

export default function FacilitatorLibrary() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const editFileRef = useRef<HTMLInputElement>(null)

  const [newModuleOpen, setNewModuleOpen] = useState(false)
  const [newModuleName, setNewModuleName] = useState("")

  const [addResourceModuleId, setAddResourceModuleId] = useState<string | null>(null)
  const [addMode, setAddMode] = useState<"link" | "file">("link")
  const [resourceTitle, setResourceTitle] = useState("")
  const [linkUrl, setLinkUrl] = useState("")

  const [editResource, setEditResource] = useState<LibraryResource | null>(null)
  const [editTitle, setEditTitle] = useState("")
  const [editUrl, setEditUrl] = useState("")

  const { data: modules, isLoading } = useQuery({ queryKey: ["facilitator-library"], queryFn: facilitatorListLibraryApi })

  const createModule = useMutation({
    mutationFn: () => createLibraryModuleApi({ name: newModuleName }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-library"] })
      setNewModuleOpen(false)
      setNewModuleName("")
    },
  })

  const deleteModule = useMutation({
    mutationFn: (id: string) => deleteLibraryModuleApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-library"] }),
  })

  const addLink = useMutation({
    mutationFn: () => addLibraryLinkApi({ moduleId: addResourceModuleId!, title: resourceTitle, url: linkUrl }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["facilitator-library"] }); closeAddDialog() },
  })

  const uploadFile = useMutation({
    mutationFn: (file: File) => uploadLibraryResourceApi({ moduleId: addResourceModuleId!, title: resourceTitle, file }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["facilitator-library"] }); closeAddDialog() },
  })

  const updateResource = useMutation({
    mutationFn: () => {
      if (editResource!.resource_type === "file") {
        const newFile = editFileRef.current?.files?.[0]
        if (newFile) return replaceLibraryFileApi(editResource!.id, newFile, editTitle)
        return updateLibraryResourceApi(editResource!.id, { title: editTitle })
      }
      return updateLibraryResourceApi(editResource!.id, { title: editTitle, url: editUrl })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-library"] })
      setEditResource(null)
    },
  })

  const deleteResource = useMutation({
    mutationFn: (id: string) => deleteLibraryResourceApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-library"] }),
  })

  function openAddDialog(moduleId: string) {
    setAddResourceModuleId(moduleId)
    setAddMode("link")
    setResourceTitle("")
    setLinkUrl("")
  }

  function closeAddDialog() {
    setAddResourceModuleId(null)
    setResourceTitle("")
    setLinkUrl("")
  }

  function openEditDialog(r: LibraryResource) {
    setEditResource(r)
    setEditTitle(r.title)
    setEditUrl(r.file_url)
  }

  const isPending = addLink.isPending || uploadFile.isPending

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader
        title="Manage Library"
        subtitle="Upload shared workshop materials for instructors."
        action={<Button onClick={() => setNewModuleOpen(true)}><Plus size={16} className="mr-1.5" /> New module</Button>}
      />

      {(modules ?? []).length === 0 ? (
        <EmptyState title="No library modules yet" />
      ) : (
        <div className="space-y-4">
          {modules!.map((m) => (
            <Card key={m.id}>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>{m.name}</CardTitle>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => openAddDialog(m.id)}>
                    <Plus size={14} className="mr-1" /> Resource
                  </Button>
                  <button onClick={() => deleteModule.mutate(m.id)} className="p-2 text-muted-foreground hover:text-destructive">
                    <Trash2 size={16} />
                  </button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {m.resources.map((r) => (
                  <ResourceRow
                    key={r.id}
                    r={r}
                    onEdit={() => openEditDialog(r)}
                    onDelete={() => deleteResource.mutate(r.id)}
                  />
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* New module dialog */}
      <Dialog open={newModuleOpen} onOpenChange={setNewModuleOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New library module</DialogTitle></DialogHeader>
          <input className="input mb-3" placeholder="Module name" value={newModuleName} onChange={(e) => setNewModuleName(e.target.value)} />
          <Button onClick={() => createModule.mutate()} disabled={!newModuleName || createModule.isPending}>
            {createModule.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogContent>
      </Dialog>

      {/* Add resource dialog */}
      <Dialog open={!!addResourceModuleId} onOpenChange={(open) => !open && closeAddDialog()}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add resource</DialogTitle></DialogHeader>

          <div className="flex gap-2 mb-1">
            <button
              onClick={() => setAddMode("link")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                addMode === "link"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-muted"
              }`}
            >
              <Link2 size={14} /> Link
            </button>
            <button
              onClick={() => setAddMode("file")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                addMode === "file"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-muted"
              }`}
            >
              <Upload size={14} /> File upload
            </button>
          </div>

          <input
            className="input mb-3"
            placeholder="Title"
            value={resourceTitle}
            onChange={(e) => setResourceTitle(e.target.value)}
          />

          {addMode === "link" ? (
            <input
              className="input mb-3"
              placeholder="URL (https://…)"
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
            />
          ) : (
            <input ref={fileRef} type="file" className="input mb-3" />
          )}

          <Button
            onClick={() => {
              if (addMode === "link") { addLink.mutate() }
              else { const f = fileRef.current?.files?.[0]; if (f) uploadFile.mutate(f) }
            }}
            disabled={!resourceTitle || (addMode === "link" ? !linkUrl : false) || isPending}
          >
            {isPending ? "Adding…" : addMode === "link" ? "Add link" : "Upload file"}
          </Button>
        </DialogContent>
      </Dialog>

      {/* Edit resource dialog */}
      <Dialog open={!!editResource} onOpenChange={(open) => !open && setEditResource(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit resource</DialogTitle></DialogHeader>

          <input
            className="input mb-3"
            placeholder="Title"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
          />

          {editResource?.resource_type === "link" ? (
            <input
              className="input mb-3"
              placeholder="URL (https://…)"
              value={editUrl}
              onChange={(e) => setEditUrl(e.target.value)}
            />
          ) : (
            <div className="mb-3">
              <p className="text-xs text-muted-foreground mb-1.5">Replace file (leave empty to keep current)</p>
              <input ref={editFileRef} type="file" className="input" />
            </div>
          )}

          <Button
            onClick={() => updateResource.mutate()}
            disabled={!editTitle || updateResource.isPending}
          >
            {updateResource.isPending ? "Saving…" : "Save changes"}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
