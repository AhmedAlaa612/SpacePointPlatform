import { Link, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, CheckCircle2, ExternalLink } from "lucide-react"
import { getTrainingPdfUrlApi, listTrainingApi, markVideoCompleteApi, streamVideoApi } from "@/api/instructors/training"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"
import { VideoPlayer } from "@/components/video/VideoPlayer"
import { PdfViewer } from "@/components/documents/PdfViewer"
import { isKnownEmbedHost } from "@/lib/embed"

export default function TrainingPlayer() {
  const { videoId } = useParams({ strict: false }) as { videoId: string }
  const qc = useQueryClient()

  const { data: modules, isLoading } = useQuery({ queryKey: ["instructor-training"], queryFn: listTrainingApi })
  const video = (modules ?? []).flatMap((m) => m.videos).find((v) => v.id === videoId)

  const complete = useMutation({
    mutationFn: () => markVideoCompleteApi(videoId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-training"] }),
  })

  const { data: streamUrl } = useQuery({
    queryKey: ["training-video-stream", videoId],
    queryFn: () => streamVideoApi(videoId),
    enabled: !!video?.video_uploaded,
    // Poll while an hls_encrypted upload is still transcoding — this used
    // to be a non-issue when uploads flipped straight to "ready", but now
    // there is a real async gap to bridge without a manual refresh.
    refetchInterval: (q) => {
      const status = q.state.data?.video_info?.status
      return status && status !== "ready" && status !== "failed" ? 4000 : false
    },
  })

  const { data: pdfUrl, isError: pdfError } = useQuery({
    queryKey: ["training-pdf-url", videoId],
    queryFn: () => getTrainingPdfUrlApi(videoId),
    enabled: !!video?.has_pdf,
  })

  if (isLoading || !video) return <Spinner />

  return (
    <div>
      <Link to="/instructors/training" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4">
        <ArrowLeft size={16} /> Back to training
      </Link>
      <PageHeader title={video.title} subtitle={video.description ?? undefined} />

      <Card className="mb-4">
        <CardContent className={video.has_pdf ? "p-4 h-[80vh] flex flex-col" : "p-0"}>
          {video.has_pdf ? (
            pdfError ? (
              <p className="text-sm text-destructive py-6">Couldn't load this PDF.</p>
            ) : !pdfUrl ? (
              <p className="text-sm text-muted-foreground py-6">Loading document...</p>
            ) : (
              <PdfViewer url={pdfUrl} className="flex flex-col gap-3 flex-1 min-h-0" />
            )
          ) : video.video_uploaded ? (
            streamUrl?.video_info ? (
              <VideoPlayer
                info={streamUrl.video_info}
                title={video.title}
                className="aspect-video rounded-xl overflow-hidden bg-black"
              />
            ) : (
              <div className="aspect-video flex items-center justify-center text-sm text-muted-foreground">
                Loading video…
              </div>
            )
          ) : video.video_url && isKnownEmbedHost(video.video_url) ? (
            <VideoPlayer
              info={{ provider: video.video_url.includes("vimeo.com") ? "vimeo" : "youtube", embed_url: video.video_url }}
              title={video.title}
              className="aspect-video rounded-xl overflow-hidden"
            />
          ) : video.video_url ? (
            // Not a recognized embed host (YouTube/Vimeo) — still a real
            // link, just not one that plays inline. Same fallback Library
            // already gives a plain "link" resource.
            <div className="aspect-video flex items-center justify-center">
              <a
                href={video.video_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
              >
                Open link <ExternalLink size={14} />
              </a>
            </div>
          ) : (
            <div className="aspect-video flex items-center justify-center text-sm text-muted-foreground">
              No link configured.
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
