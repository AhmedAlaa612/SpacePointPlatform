import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, FileText, Link2, Pencil, PlayCircle, Plus, Trash2, Upload, Video } from "lucide-react"
import {
  createTrainingModuleApi, deleteTrainingModuleApi, deleteTrainingVideoApi,
  facilitatorListTrainingApi, addTrainingVideoApi, updateTrainingVideoApi, uploadTrainingVideoApi,
  uploadTrainingFileApi, getTrainingFileUrlApi, updateTrainingModuleApi,
} from "@/api/instructors/facilitator"
import type { TrainingModule, TrainingVideo } from "@/types/instructors"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { PdfViewer } from "@/components/documents/PdfViewer"

const isPdf = (v: TrainingVideo) => (v.format ?? "").toUpperCase() === "PDF"

function PdfPreview({ videoId }: { videoId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["training-file-url", videoId],
    queryFn: () => getTrainingFileUrlApi(videoId),
  })
  if (isLoading) return <p className="text-sm text-muted-foreground py-6">Loading document...</p>
  if (isError || !data) return <p className="text-sm text-destructive py-6">Couldn't load this PDF.</p>
  return <PdfViewer url={data} className="flex flex-col gap-3 flex-1 min-h-0" />
}

export default function FacilitatorTraining() {
  const qc = useQueryClient()
  const uploadFileRef = useRef<HTMLInputElement>(null)
  const editFileRef = useRef<HTMLInputElement>(null)
  const addFileRef = useRef<HTMLInputElement>(null)
  const [newModuleOpen, setNewModuleOpen] = useState(false)
  const [newModuleTitle, setNewModuleTitle] = useState("")
  const [addVideoModuleId, setAddVideoModuleId] = useState<string | null>(null)
  // Mirrors the Library "Add resource" toggle exactly — a training item is
  // exactly one of a link, an uploaded file (PDF or anything else), or a
  // video (itself either an upload or a pasted embed link).
  const [addMode, setAddMode] = useState<"link" | "file" | "video">("link")
  const [videoSource, setVideoSource] = useState<"upload" | "embed">("upload")
  const [videoTitle, setVideoTitle] = useState("")
  const [videoUrl, setVideoUrl] = useState("")

  const [editVideo, setEditVideo] = useState<TrainingVideo | null>(null)
  const [editTitle, setEditTitle] = useState("")
  const [editUrl, setEditUrl] = useState("")

  const [previewVideo, setPreviewVideo] = useState<TrainingVideo | null>(null)
  const [openingFileId, setOpeningFileId] = useState<string | null>(null)

  const [editModule, setEditModule] = useState<TrainingModule | null>(null)
  const [editModuleTitle, setEditModuleTitle] = useState("")

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

  const updateModule = useMutation({
    mutationFn: () => updateTrainingModuleApi(editModule!.id, { title: editModuleTitle }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      setEditModule(null)
    },
  })

  // One action regardless of addMode: create the bare row, then — for an
  // upload (file, or video+upload) — immediately upload the picked file
  // against the id just created. A single click even though it's two API
  // calls, instead of "save, then go find the upload button elsewhere."
  const addVideo = useMutation({
    mutationFn: async () => {
      const isEmbed = addMode === "link" || (addMode === "video" && videoSource === "embed")
      const created = await addTrainingVideoApi({
        moduleId: addVideoModuleId!, title: videoTitle, url: isEmbed ? videoUrl : undefined,
      })
      if (!isEmbed) {
        const file = addFileRef.current?.files?.[0]
        if (file) {
          if (addMode === "video") await uploadTrainingVideoApi(created.id, file)
          else await uploadTrainingFileApi(created.id, file)
        }
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

  const uploadFile = useMutation({
    mutationFn: (file: File) => uploadTrainingFileApi(editVideo!.id, file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["facilitator-training"] })
      setEditVideo(null)
    },
  })

  function openAddVideo(moduleId: string) {
    setAddVideoModuleId(moduleId)
    setAddMode("link")
    setVideoSource("upload")
    setVideoTitle("")
    setVideoUrl("")
  }

  function closeAddDialog() {
    setAddVideoModuleId(null)
    setVideoSource("upload")
    setVideoTitle("")
    setVideoUrl("")
  }

  function openEditVideo(v: TrainingVideo) {
    setEditVideo(v)
    setEditTitle(v.title)
    setEditUrl(v.video_url)
  }

  function openEditModule(m: TrainingModule) {
    setEditModule(m)
    setEditModuleTitle(m.title)
  }

  async function openFile(v: TrainingVideo) {
    setOpeningFileId(v.id)
    try {
      const url = await getTrainingFileUrlApi(v.id)
      window.open(url, "_blank", "noopener,noreferrer")
    } finally {
      setOpeningFileId(null)
    }
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
                  <button onClick={() => openEditModule(m)} className="p-2 text-muted-foreground hover:text-primary">
                    <Pencil size={16} />
                  </button>
                  <button onClick={() => deleteModule.mutate(m.id)} className="p-2 text-muted-foreground hover:text-destructive">
                    <Trash2 size={16} />
                  </button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {m.videos.map((v) => (
                  <div key={v.id} className="flex items-center gap-3 p-3 rounded-lg border bg-background">
                    {v.format ? <FileText className="text-primary shrink-0" size={18} /> : <PlayCircle className="text-primary shrink-0" size={18} />}
                    {isPdf(v) ? (
                      <button
                        type="button"
                        onClick={() => setPreviewVideo(v)}
                        className="text-sm flex-1 truncate hover:text-primary flex items-center gap-1.5 min-w-0 text-left cursor-pointer"
                      >
                        <span className="truncate">{v.title}</span>
                        <span className="text-muted-foreground shrink-0 text-xs">(PDF)</span>
                      </button>
                    ) : v.format ? (
                      <button
                        type="button"
                        onClick={() => openFile(v)}
                        disabled={openingFileId === v.id}
                        className="text-sm flex-1 truncate hover:text-primary flex items-center gap-1.5 min-w-0 text-left cursor-pointer disabled:opacity-50"
                      >
                        <span className="truncate">{v.title}</span>
                        <span className="text-muted-foreground shrink-0 text-xs">({v.format})</span>
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

      <Dialog open={!!editModule} onOpenChange={(open) => !open && setEditModule(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit training module</DialogTitle></DialogHeader>
          <input className="input mb-3" placeholder="Module title" value={editModuleTitle} onChange={(e) => setEditModuleTitle(e.target.value)} />
          <Button onClick={() => updateModule.mutate()} disabled={!editModuleTitle || updateModule.isPending}>
            {updateModule.isPending ? "Saving…" : "Save changes"}
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
              onClick={() => setAddMode("file")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                addMode === "file"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-muted"
              }`}
            >
              <Upload size={14} /> File upload
            </button>
            <button
              onClick={() => setAddMode("video")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                addMode === "video"
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border text-muted-foreground hover:bg-muted"
              }`}
            >
              <Video size={14} /> Video
            </button>
          </div>

          <input
            className="input mb-3"
            placeholder="Title"
            value={videoTitle}
            onChange={(e) => setVideoTitle(e.target.value)}
          />

          {addMode === "video" && (
            <div className="flex gap-2 mb-3">
              <button
                onClick={() => setVideoSource("upload")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  videoSource === "upload"
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border text-muted-foreground hover:bg-muted"
                }`}
              >
                <Upload size={12} /> Upload file
              </button>
              <button
                onClick={() => setVideoSource("embed")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  videoSource === "embed"
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border text-muted-foreground hover:bg-muted"
                }`}
              >
                <Link2 size={12} /> Embed link
              </button>
            </div>
          )}

          {addMode === "link" || (addMode === "video" && videoSource === "embed") ? (
            <input
              key="url-input"
              className="input mb-3"
              placeholder={addMode === "video" ? "YouTube or Vimeo URL" : "Link — YouTube/Vimeo plays inline, anything else opens as a link (https://…)"}
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
            />
          ) : (
            <input
              key="file-input"
              ref={addFileRef} type="file" accept={addMode === "video" ? "video/*" : undefined} className="input mb-3"
            />
          )}

          <Button
            onClick={() => addVideo.mutate()}
            disabled={
              !videoTitle
              || ((addMode === "link" || (addMode === "video" && videoSource === "embed")) && !videoUrl)
              || addVideo.isPending
            }
          >
            {addVideo.isPending
              ? "Adding…"
              : addMode === "link"
              ? "Add link"
              : addMode === "video"
              ? (videoSource === "embed" ? "Add embedded video" : "Upload video")
              : "Upload file"}
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editVideo} onOpenChange={(open) => !open && setEditVideo(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit resource</DialogTitle></DialogHeader>
          <input
            className="input mb-3"
            placeholder="Title"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
          />
          <input
            className="input mb-3"
            placeholder="Link (https://…)"
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

          <input ref={editFileRef} type="file" className="input mb-3 mt-3" />
          <Button
            variant="outline"
            onClick={() => { const f = editFileRef.current?.files?.[0]; if (f) uploadFile.mutate(f) }}
            disabled={uploadFile.isPending}
          >
            <FileText size={14} className="mr-1.5" />
            {uploadFile.isPending ? "Uploading…" : "Upload a file instead (PDF, etc.)"}
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
