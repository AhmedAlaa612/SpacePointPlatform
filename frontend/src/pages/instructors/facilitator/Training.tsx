import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, FileText, Link2, Pencil, PlayCircle, Plus, Trash2, Upload } from "lucide-react"
import {
  createTrainingModuleApi, deleteTrainingModuleApi, deleteTrainingVideoApi,
  facilitatorListTrainingApi, addTrainingVideoApi, updateTrainingVideoApi, uploadTrainingVideoApi,
  uploadTrainingPdfApi, getTrainingPdfUrlApi,
} from "@/api/instructors/facilitator"
import type { TrainingVideo } from "@/types/instructors"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { PdfViewer } from "@/components/documents/PdfViewer"

function PdfPreview({ videoId }: { videoId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["training-pdf-url", videoId],
    queryFn: () => getTrainingPdfUrlApi(videoId),
  })
  if (isLoading) return <p className="text-sm text-muted-foreground py-6">Loading document...</p>
  if (isError || !data) return <p className="text-sm text-destructive py-6">Couldn't load this PDF.</p>
  return <PdfViewer url={data} className="flex flex-col gap-3 flex-1 min-h-0" />
}

export default function FacilitatorTraining() {
  const qc = useQueryClient()
  const uploadFileRef = useRef<HTMLInputElement>(null)
  const uploadPdfRef = useRef<HTMLInputElement>(null)
  const addFileRef = useRef<HTMLInputElement>(null)
  const [newModuleOpen, setNewModuleOpen] = useState(false)
  const [newModuleTitle, setNewModuleTitle] = useState("")
  const [addVideoModuleId, setAddVideoModuleId] = useState<string | null>(null)
  // Mirrors the Library "Add resource" toggle — a training item is exactly
  // one of a pasted link, an uploaded video, or an uploaded PDF.
  const [addMode, setAddMode] = useState<"link" | "video" | "pdf">("link")
  const [videoTitle, setVideoTitle] = useState("")
  const [videoUrl, setVideoUrl] = useState("")

  const [editVideo, setEditVideo] = useState<TrainingVideo | null>(null)
  const [editTitle, setEditTitle] = useState("")
  const [editUrl, setEditUrl] = useState("")

  const [previewVideo, setPreviewVideo] = useState<TrainingVideo | null>(null)

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

  // One action regardless of addMode: create the bare row, then — for
  // video/pdf — immediately upload the picked file against the id just
  // created. A single click for the facilitator even though it's two API
  // calls, instead of "save, then go find the upload button elsewhere."
  const addVideo = useMutation({
    mutationFn: async () => {
      const created = await addTrainingVideoApi({
        moduleId: addVideoModuleId!, title: videoTitle, url: addMode === "link" ? videoUrl : undefined,
      })
      if (addMode === "video") {
        const file = addFileRef.current?.files?.[0]
        if (file) await uploadTrainingVideoApi(created.id, file)
      } else if (addMode === "pdf") {
        const file = addFileRef.current?.files?.[0]
        if (file) await uploadTrainingPdfApi(created.id, file)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      closeAddDialog()
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

  const uploadVideo = useMutation({
    mutationFn: (file: File) => uploadTrainingVideoApi(editVideo!.id, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      setEditVideo(null)
    },
  })

  const uploadPdf = useMutation({
    mutationFn: (file: File) => uploadTrainingPdfApi(editVideo!.id, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      setEditVideo(null)
    },
  })

  function openAddVideo(moduleId: string) {
    setAddVideoModuleId(moduleId)
    setAddMode("link")
    setVideoTitle("")
    setVideoUrl("")
  }

  function closeAddDialog() {
    setAddVideoModuleId(null)
    setAddMode("link")
    setVideoTitle("")
    setVideoUrl("")
  }

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
                  <Button size="sm" variant="outline" onClick={() => openAddVideo(m.id)}>
                    <Plus size={14} className="mr-1" /> Resource
                  </Button>
                  <button onClick={() => deleteModule.mutate(m.id)} className="p-2 text-muted-foreground hover:text-destructive">
                    <Trash2 size={16} />
                  </button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {m.videos.map((v) => (
                  <div key={v.id} className="flex items-center gap-3 p-3 rounded-lg border bg-background">
                    {v.has_pdf ? <FileText className="text-primary shrink-0" size={18} /> : <PlayCircle className="text-primary shrink-0" size={18} />}
                    {v.has_pdf ? (
                      <button
                        type="button"
                        onClick={() => setPreviewVideo(v)}
                        className="text-sm flex-1 truncate hover:text-primary flex items-center gap-1.5 min-w-0 text-left cursor-pointer"
                      >
                        <span className="truncate">{v.title}</span>
                        <span className="text-muted-foreground shrink-0 text-xs">(PDF)</span>
                      </button>
                    ) : v.video_uploaded ? (
                      <span className="text-sm flex-1 truncate flex items-center gap-1.5 min-w-0">
                        <span className="truncate">{v.title}</span>
                        <span className="text-muted-foreground shrink-0 text-xs">(uploaded)</span>
                      </span>
                    ) : (
                      <a
                        href={v.video_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm flex-1 truncate hover:text-primary flex items-center gap-1.5 min-w-0"
                      >
                        <span className="truncate">{v.title}</span>
                        <ExternalLink size={12} className="shrink-0 text-muted-foreground" />
                      </a>
                    )}
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

      <Dialog open={!!addVideoModuleId} onOpenChange={(open) => !open && closeAddDialog()}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add training resource</DialogTitle></DialogHeader>

          <div className="flex gap-2 mb-3">
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
              onClick={() => setAddMode("video")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                addMode === "video"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-muted"
              }`}
            >
              <Upload size={14} /> Upload video
            </button>
            <button
              onClick={() => setAddMode("pdf")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                addMode === "pdf"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-muted"
              }`}
            >
              <FileText size={14} /> Upload PDF
            </button>
          </div>

          <input
            className="input mb-3"
            placeholder="Title"
            value={videoTitle}
            onChange={(e) => setVideoTitle(e.target.value)}
          />

          {addMode === "link" ? (
            <input
              key="url-input"
              className="input mb-3"
              placeholder="Link — YouTube/Vimeo plays inline, anything else opens as a link (https://…)"
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
            />
          ) : (
            <input
              key="file-input"
              ref={addFileRef} type="file" accept={addMode === "video" ? "video/*" : "application/pdf"} className="input mb-3"
            />
          )}

          <Button
            onClick={() => addVideo.mutate()}
            disabled={!videoTitle || (addMode === "link" && !videoUrl) || addVideo.isPending}
          >
            {addVideo.isPending ? "Adding…" : addMode === "link" ? "Add link" : addMode === "video" ? "Upload video" : "Upload PDF"}
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

          <div className="flex items-center gap-2 my-3">
            <div className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground">or</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <input ref={uploadFileRef} type="file" accept="video/*" className="input mb-3" />
          <Button
            variant="outline"
            onClick={() => { const f = uploadFileRef.current?.files?.[0]; if (f) uploadVideo.mutate(f) }}
            disabled={uploadVideo.isPending}
          >
            <Upload size={14} className="mr-1.5" />
            {uploadVideo.isPending ? "Uploading…" : "Upload a video file instead"}
          </Button>

          <input ref={uploadPdfRef} type="file" accept="application/pdf" className="input mb-3 mt-3" />
          <Button
            variant="outline"
            onClick={() => { const f = uploadPdfRef.current?.files?.[0]; if (f) uploadPdf.mutate(f) }}
            disabled={uploadPdf.isPending}
          >
            <FileText size={14} className="mr-1.5" />
            {uploadPdf.isPending ? "Uploading…" : "Upload a PDF instead"}
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!previewVideo} onOpenChange={(open) => !open && setPreviewVideo(null)}>
        <DialogContent className="sm:max-w-[95vw] max-w-[95vw] w-[95vw] h-[92vh] max-h-[92vh] flex flex-col">
          <DialogHeader><DialogTitle>{previewVideo?.title}</DialogTitle></DialogHeader>
          {previewVideo && <PdfPreview videoId={previewVideo.id} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
