import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, Pencil, PlayCircle, Plus, Trash2 } from "lucide-react"
import {
  createTrainingModuleApi, deleteTrainingModuleApi, deleteTrainingVideoApi,
  facilitatorListTrainingApi, addTrainingVideoApi, updateTrainingVideoApi,
} from "@/api/instructors/facilitator"
import type { TrainingVideo } from "@/types/instructors"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function FacilitatorTraining() {
  const qc = useQueryClient()
  const [newModuleOpen, setNewModuleOpen] = useState(false)
  const [newModuleTitle, setNewModuleTitle] = useState("")
  const [addVideoModuleId, setAddVideoModuleId] = useState<string | null>(null)
  const [videoTitle, setVideoTitle] = useState("")
  const [videoUrl, setVideoUrl] = useState("")

  const [editVideo, setEditVideo] = useState<TrainingVideo | null>(null)
  const [editTitle, setEditTitle] = useState("")
  const [editUrl, setEditUrl] = useState("")

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

  const addVideo = useMutation({
    mutationFn: () => addTrainingVideoApi({ moduleId: addVideoModuleId!, title: videoTitle, url: videoUrl }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      setAddVideoModuleId(null)
      setVideoTitle("")
      setVideoUrl("")
    },
  })

  const updateVideo = useMutation({
    mutationFn: () => updateTrainingVideoApi(editVideo!.id, { title: editTitle, url: editUrl }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      setEditVideo(null)
    },
  })

  const deleteVideo = useMutation({
    mutationFn: (id: string) => deleteTrainingVideoApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facilitator-training"] }),
  })

  function openEditVideo(v: TrainingVideo) {
    setEditVideo(v)
    setEditTitle(v.title)
    setEditUrl(v.video_url)
  }

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader
        title="Manage Training"
        subtitle="Organize SatKit training content for instructors."
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
                  <Button size="sm" variant="outline" onClick={() => setAddVideoModuleId(m.id)}>
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
                    <a
                      href={v.video_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm flex-1 truncate hover:text-primary flex items-center gap-1.5 min-w-0"
                    >
                      <span className="truncate">{v.title}</span>
                      <ExternalLink size={12} className="shrink-0 text-muted-foreground" />
                    </a>
                    <button onClick={() => openEditVideo(v)} className="p-1 text-muted-foreground hover:text-primary">
                      <Pencil size={14} />
                    </button>
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

      <Dialog open={!!addVideoModuleId} onOpenChange={(open) => !open && setAddVideoModuleId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add training video</DialogTitle></DialogHeader>
          <input
            className="input mb-3"
            placeholder="Video title"
            value={videoTitle}
            onChange={(e) => setVideoTitle(e.target.value)}
          />
          <input
            className="input mb-3"
            placeholder="YouTube or video link (https://…)"
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
          />
          <Button
            onClick={() => addVideo.mutate()}
            disabled={!videoTitle || !videoUrl || addVideo.isPending}
          >
            {addVideo.isPending ? "Adding…" : "Add video"}
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editVideo} onOpenChange={(open) => !open && setEditVideo(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit video</DialogTitle></DialogHeader>
          <input
            className="input mb-3"
            placeholder="Video title"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
          />
          <input
            className="input mb-3"
            placeholder="Video URL (https://…)"
            value={editUrl}
            onChange={(e) => setEditUrl(e.target.value)}
          />
          <Button
            onClick={() => updateVideo.mutate()}
            disabled={!editTitle || !editUrl || updateVideo.isPending}
          >
            {updateVideo.isPending ? "Saving…" : "Save changes"}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
