import { useEffect, useState } from "react"
import { Link, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertCircle, ArrowLeft, CheckCircle2 } from "lucide-react"
import { listTrainingApi, markVideoCompleteApi, streamVideoApi } from "@/api/instructors/training"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function TrainingPlayer() {
  const { videoId } = useParams({ strict: false }) as { videoId: string }
  const qc = useQueryClient()
  const [streamUrl, setStreamUrl] = useState<string | null>(null)
  const [streamError, setStreamError] = useState(false)

  const { data: modules, isLoading } = useQuery({ queryKey: ["instructor-training"], queryFn: listTrainingApi })
  const video = (modules ?? []).flatMap((m) => m.videos).find((v) => v.id === videoId)

  useEffect(() => {
    let active = true
    setStreamUrl(null)
    setStreamError(false)
    streamVideoApi(videoId)
      .then((url) => { if (active) setStreamUrl(url) })
      .catch(() => { if (active) setStreamError(true) })
    return () => { active = false }
  }, [videoId])

  const complete = useMutation({
    mutationFn: () => markVideoCompleteApi(videoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-training"] }),
  })

  if (isLoading || !video) return <Spinner />

  return (
    <div>
      <Link to="/instructors/training" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4">
        <ArrowLeft size={16} /> Back to training
      </Link>
      <PageHeader title={video.title} subtitle={video.description ?? undefined} />

      <Card className="mb-4">
        <CardContent className="p-0">
          {streamError ? (
            <div className="aspect-video flex flex-col items-center justify-center gap-2 text-muted-foreground">
              <AlertCircle size={28} />
              <p className="text-sm">This video isn't available right now.</p>
            </div>
          ) : streamUrl ? (
            <video src={streamUrl} controls className="w-full rounded-t-xl aspect-video bg-black" />
          ) : (
            <div className="aspect-video flex items-center justify-center"><Spinner /></div>
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
