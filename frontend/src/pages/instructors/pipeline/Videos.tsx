import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { ArrowRight } from "lucide-react"
import { listVideosApi, updateVideoApi } from "@/api/instructors/applicant"
import type { VideoSubmission } from "@/types/instructors"
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

function VideoCard({ video }: { video: VideoSubmission }) {
  const qc = useQueryClient()
  const [summary, setSummary] = useState<string | null>(null)
  const text = summary ?? video.summary_text ?? ""
  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0
  const locked = video.status === "submitted"

  const save = useMutation({
    mutationFn: (submit: boolean) =>
      updateVideoApi(video.video_no, { youtube_url: video.youtube_url ?? undefined, summary_text: text, submit }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-videos"] })
      setSummary(null)
    },
  })

  const embedId = extractYouTubeId(video.youtube_url ?? "")
  const embedSrc = embedId ? `https://www.youtube.com/embed/${embedId}` : null

  return (
    <Card className={locked ? "border-l-4 border-l-green-500" : ""}>
      <CardContent className="p-4 flex flex-col md:flex-row gap-6">
        <div className="w-full md:w-1/2 shrink-0">
          {embedSrc ? (
            <div className="aspect-video rounded-lg overflow-hidden">
              <iframe
                src={embedSrc}
                title={`Video ${video.video_no}`}
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
        </div>

        <div className="w-full md:w-1/2 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <p className="font-semibold text-foreground">Video {video.video_no} Summary</p>
            <StatusPill status={video.status} />
          </div>
          <textarea
            className="input flex-1 min-h-40 w-full resize-none"
            placeholder={`Write at least ${MIN_WORDS} words…`}
            value={text}
            disabled={locked}
            onChange={(e) => setSummary(e.target.value)}
          />
          <div className="flex items-center justify-between mt-2">
            <p className={`text-xs font-medium ${wordCount >= MIN_WORDS ? "text-green-600" : "text-muted-foreground"}`}>
              {wordCount} words
            </p>
          </div>
          {!locked && (
            <div className="flex gap-2 mt-3">
              <Button size="sm" variant="outline" className="flex-1" onClick={() => save.mutate(false)} disabled={save.isPending}>
                Save draft
              </Button>
              <Button size="sm" className="flex-1" onClick={() => save.mutate(true)} disabled={save.isPending || wordCount < MIN_WORDS}>
                Submit
              </Button>
            </div>
          )}
          {save.isError && (
            <p className="text-sm text-destructive mt-2">{(save.error as any)?.response?.data?.detail || "Save failed."}</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default function Videos() {
  const { data: videos, isLoading } = useQuery({ queryKey: ["instructor-videos"], queryFn: listVideosApi })

  if (isLoading || !videos) return <Spinner />

  const allSubmitted = videos.length === 3 && videos.every((v) => v.status === "submitted")

  return (
    <div>
      <PageHeader
        title="Phase 1 — Video Summaries"
        subtitle="Watch the following foundational videos and provide a detailed summary (minimum 200 words each) demonstrating your understanding. You can save your progress as a draft and submit when ready."
      />
      <div className="flex flex-col gap-6">
        {videos.map((v) => (
          <VideoCard key={v.id} video={v} />
        ))}
      </div>

      {allSubmitted && (
        <div className="mt-10 flex justify-center">
          <Link to="/instructors/modules">
            <Button size="lg" className="gap-2">
              Continue to Phase 2 (Modules & Checklists)
              <ArrowRight size={18} />
            </Button>
          </Link>
        </div>
      )}
    </div>
  )
}
