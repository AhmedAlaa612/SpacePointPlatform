import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import { ArrowLeft } from "lucide-react"
import { listVideosApi, updateVideoApi } from "@/api/instructors/applicant"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

const MIN_WORDS = 200

function extractYouTubeId(url: string): string {
  if (!url) return ""
  try {
    if (url.includes("youtu.be/")) return url.split("youtu.be/")[1].split(/[?&]/)[0]
    const m = url.match(/[?&]v=([^&]+)/)
    if (m) return m[1]
  } catch { /* ignore */ }
  return ""
}

export default function VideoDetail() {
  const { videoNo } = useParams({ strict: false }) as { videoNo: string }
  const no = parseInt(videoNo, 10)
  const qc = useQueryClient()

  const { data: videos, isLoading } = useQuery({ queryKey: ["instructor-videos"], queryFn: listVideosApi })
  const video = videos?.find((v) => v.video_no === no)

  const [summary, setSummary] = useState<string | null>(null)
  const text = summary ?? video?.summary_text ?? ""
  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0
  const locked = video?.status === "submitted"

  const save = useMutation({
    mutationFn: (submit: boolean) =>
      updateVideoApi(no, { youtube_url: video?.youtube_url ?? undefined, summary_text: text, submit }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-videos"] })
      setSummary(null)
    },
  })

  if (isLoading || !videos) return <Spinner />
  if (!video) return <p className="text-sm text-muted-foreground">Video not found.</p>

  const embedId = extractYouTubeId(video.youtube_url ?? "")
  const embedSrc = embedId ? `https://www.youtube.com/embed/${embedId}` : null

  return (
    <div>
      <Link to="/instructors/videos" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4">
        <ArrowLeft size={16} /> Back to videos
      </Link>

      <PageHeader
        title={`Video ${no}`}
        subtitle="Watch the video then write a summary of at least 200 words."
        action={<StatusPill status={video.status} />}
      />

      <div className="flex flex-col gap-4">
        {/* Embedded player */}
        <Card>
          <CardContent className="p-4">
            {embedSrc ? (
              <div className="aspect-video rounded-lg overflow-hidden">
                <iframe
                  src={embedSrc}
                  title={`Video ${no}`}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                  className="w-full h-full"
                />
              </div>
            ) : (
              <div className="aspect-video rounded-lg border border-dashed border-border flex items-center justify-center text-sm text-muted-foreground bg-muted/20">
                Video not configured yet.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Summary */}
        <Card>
          <CardContent className="p-4 space-y-3">
            <p className="text-sm font-semibold text-foreground">Your summary</p>
            <textarea
              className="input min-h-40 w-full"
              placeholder={`Write at least ${MIN_WORDS} words…`}
              value={text}
              disabled={locked}
              onChange={(e) => setSummary(e.target.value)}
            />
            <div className="flex items-center justify-between">
              <p className={`text-xs ${wordCount >= MIN_WORDS ? "text-green-600" : "text-muted-foreground"}`}>
                {wordCount} / {MIN_WORDS} words
              </p>
              {!locked && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => save.mutate(false)} disabled={save.isPending}>
                    Save draft
                  </Button>
                  <Button size="sm" onClick={() => save.mutate(true)} disabled={save.isPending || wordCount < MIN_WORDS}>
                    Submit
                  </Button>
                </div>
              )}
            </div>
            {save.isError && (
              <p className="text-sm text-destructive">{(save.error as any)?.response?.data?.detail || "Save failed."}</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
