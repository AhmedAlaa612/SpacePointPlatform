import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FileText, Plus, Trash2 } from "lucide-react"
import {
  createLibraryModuleApi, deleteLibraryModuleApi, deleteLibraryResourceApi,
  facilitatorListLibraryApi, uploadLibraryResourceApi,
} from "@/api/instructors/facilitator"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function FacilitatorLibrary() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [newModuleOpen, setNewModuleOpen] = useState(false)
  const [newModuleName, setNewModuleName] = useState("")
  const [uploadModuleId, setUploadModuleId] = useState<string | null>(null)
  const [resourceTitle, setResourceTitle] = useState("")

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

  const uploadResource = useMutation({
    mutationFn: (file: File) => uploadLibraryResourceApi({ moduleId: uploadModuleId!, title: resourceTitle, file }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-library"] })
      setUploadModuleId(null)
      setResourceTitle("")
    },
  })

  const deleteResource = useMutation({
    mutationFn: (id: string) => deleteLibraryResourceApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-library"] }),
  })

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
                  <Button size="sm" variant="outline" onClick={() => setUploadModuleId(m.id)}>
                    <Plus size={14} className="mr-1" /> Resource
                  </Button>
                  <button onClick={() => deleteModule.mutate(m.id)} className="p-2 text-muted-foreground hover:text-destructive">
                    <Trash2 size={16} />
                  </button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {m.resources.map((r) => (
                  <div key={r.id} className="flex items-center gap-3 p-3 rounded-lg border bg-background">
                    <FileText className="text-primary shrink-0" size={18} />
                    <p className="text-sm flex-1 truncate">{r.title} <span className="text-muted-foreground">({r.format})</span></p>
                    <button onClick={() => deleteResource.mutate(r.id)} className="p-1 text-muted-foreground hover:text-destructive">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={newModuleOpen} onOpenChange={setNewModuleOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New library module</DialogTitle></DialogHeader>
          <input className="input mb-3" placeholder="Module name" value={newModuleName} onChange={(e) => setNewModuleName(e.target.value)} />
          <Button onClick={() => createModule.mutate()} disabled={!newModuleName || createModule.isPending}>
            {createModule.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!uploadModuleId} onOpenChange={(open) => !open && setUploadModuleId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Upload resource</DialogTitle></DialogHeader>
          <input className="input mb-3" placeholder="Resource title" value={resourceTitle} onChange={(e) => setResourceTitle(e.target.value)} />
          <input ref={fileRef} type="file" className="input mb-3" />
          <Button
            onClick={() => { const f = fileRef.current?.files?.[0]; if (f) uploadResource.mutate(f) }}
            disabled={!resourceTitle || uploadResource.isPending}
          >
            {uploadResource.isPending ? "Uploading…" : "Upload"}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
