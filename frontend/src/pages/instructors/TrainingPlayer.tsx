import { Link, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, CheckCircle2 } from "lucide-react"
import { listTrainingApi, markVideoCompleteApi } from "@/api/instructors/training"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"

function toEmbedUrl(url: string): string {
  if (!url) return ""
  try {
    if (url.includes("youtu.be/")) {
      const id = url.split("youtu.be/")[1].split(/[?&]/)[0]
      return `https://www.youtube.com/embed/${id}`
    }
    const m = url.match(/[?&]v=([^&]+)/)
    if (m) return `https://www.youtube.com/embed/${m[1]}`
  } catch { /* ignore */ }
  return url
}

export default function TrainingPlayer() {
  const { videoId } = useParams({ strict: false }) as { videoId: string }
  const qc = useQueryClient()

  const { data: modules, isLoading } = useQuery({ queryKey: ["instructor-training"], queryFn: listTrainingApi })
  const video = (modules ?? []).flatMap((m) => m.videos).find((v) => v.id === videoId)

  const complete = useMutation({
    mutationFn: () => markVideoCompleteApi(videoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-training"] }),
  })

  if (isLoading || !video) return <Spinner />

  const embedSrc = toEmbedUrl(video.video_url)

  return (
    <div>
      <Link to="/instructors/training" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4">
        <ArrowLeft size={16} /> Back to training
      </Link>
      <PageHeader title={video.title} subtitle={video.description ?? undefined} />

      <Card className="mb-4">
        <CardContent className="p-0">
          {embedSrc ? (
            <div className="aspect-video rounded-xl overflow-hidden">
              <iframe
                src={embedSrc}
                title={video.title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="w-full h-full"
              />
            </div>
          ) : (
            <div className="aspect-video flex items-center justify-center text-sm text-muted-foreground">
              No video link configured.
            </div>
          )}
        </CardContent>
      </Card>

      {video.notes && (
        <Card className="mb-4">
          <CardContent className="p-5">
            <p className="text-sm font-semibold mb-1">Notes</p>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{video.notes}</p>
          </CardContent>
        </Card>
      )}

      {video.is_completed ? (
        <div className="flex items-center gap-2 text-green-600 text-sm font-medium">
          <CheckCircle2 size={18} /> Completed
        </div>
      ) : (
        <Button onClick={() => complete.mutate()} disabled={complete.isPending}>
          {complete.isPending ? "Marking…" : "Mark as complete"}
        </Button>
      )}
    </div>
  )
}
