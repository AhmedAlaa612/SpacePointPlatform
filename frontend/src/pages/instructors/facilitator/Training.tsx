import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { PlayCircle, Plus, Trash2 } from "lucide-react"
import {
  createTrainingModuleApi, deleteTrainingModuleApi, deleteTrainingVideoApi,
  facilitatorListTrainingApi, uploadTrainingVideoApi,
} from "@/api/instructors/facilitator"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function FacilitatorTraining() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [newModuleOpen, setNewModuleOpen] = useState(false)
  const [newModuleTitle, setNewModuleTitle] = useState("")
  const [uploadModuleId, setUploadModuleId] = useState<string | null>(null)
  const [videoTitle, setVideoTitle] = useState("")

  const { data: modules, isLoading } = useQuery({ queryKey: ["facilitator-training"], queryFn: facilitatorListTrainingApi })

  const createModule = useMutation({
    mutationFn: () => createTrainingModuleApi({ title: newModuleTitle }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      setNewModuleOpen(false)
      setNewModuleTitle("")
    },
  })

  const deleteModule = useMutation({
    mutationFn: (id: string) => deleteTrainingModuleApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-training"] }),
  })

  const uploadVideo = useMutation({
    mutationFn: (file: File) => uploadTrainingVideoApi({ moduleId: uploadModuleId!, title: videoTitle, file }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      setUploadModuleId(null)
      setVideoTitle("")
    },
  })

  const deleteVideo = useMutation({
    mutationFn: (id: string) => deleteTrainingVideoApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-training"] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader
        title="Manage Training"
        subtitle="Upload and organize SatKit training content for instructors."
        action={<Button onClick={() => setNewModuleOpen(true)}><Plus size={16} className="mr-1.5" /> New module</Button>}
      />

      {(modules ?? []).length === 0 ? (
        <EmptyState title="No training modules yet" />
      ) : (
        <div className="space-y-4">
          {modules!.map((m) => (
            <Card key={m.id}>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>{m.title}</CardTitle>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setUploadModuleId(m.id)}>
                    <Plus size={14} className="mr-1" /> Video
                  </Button>
                  <button onClick={() => deleteModule.mutate(m.id)} className="p-2 text-muted-foreground hover:text-destructive">
                    <Trash2 size={16} />
                  </button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {m.videos.map((v) => (
                  <div key={v.id} className="flex items-center gap-3 p-3 rounded-lg border bg-background">
                    <PlayCircle className="text-primary shrink-0" size={18} />
                    <p className="text-sm flex-1 truncate">{v.title}</p>
                    <button onClick={() => deleteVideo.mutate(v.id)} className="p-1 text-muted-foreground hover:text-destructive">
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
          <DialogHeader><DialogTitle>New training module</DialogTitle></DialogHeader>
          <input className="input mb-3" placeholder="Module title" value={newModuleTitle} onChange={(e) => setNewModuleTitle(e.target.value)} />
          <Button onClick={() => createModule.mutate()} disabled={!newModuleTitle || createModule.isPending}>
            {createModule.isPending ? "Creating…" : "Create"}
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!uploadModuleId} onOpenChange={(open) => !open && setUploadModuleId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Upload training video</DialogTitle></DialogHeader>
          <input className="input mb-3" placeholder="Video title" value={videoTitle} onChange={(e) => setVideoTitle(e.target.value)} />
          <input ref={fileRef} type="file" accept="video/*" className="input mb-3" />
          <Button
            onClick={() => { const f = fileRef.current?.files?.[0]; if (f) uploadVideo.mutate(f) }}
            disabled={!videoTitle || uploadVideo.isPending}
          >
            {uploadVideo.isPending ? "Uploading…" : "Upload"}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
