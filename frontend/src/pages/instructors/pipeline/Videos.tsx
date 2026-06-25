import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { listVideosApi, updateVideoApi } from "@/api/instructors/applicant"
import type { VideoSubmission } from "@/types/instructors"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

const MIN_WORDS = 200

function VideoCard({ video }: { video: VideoSubmission }) {
  const qc = useQueryClient()
  const [url, setUrl] = useState(video.youtube_url ?? "")
  const [summary, setSummary] = useState(video.summary_text ?? "")
  const wordCount = summary.trim() ? summary.trim().split(/\s+/).length : 0
  const locked = video.status === "submitted"

  const save = useMutation({
    mutationFn: (submit: boolean) => updateVideoApi(video.video_no, { youtube_url: url, summary_text: summary, submit }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-videos"] }),
  })

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Video {video.video_no}</CardTitle>
        <StatusPill status={video.status} />
      </CardHeader>
      <CardContent className="space-y-3">
        <input
          className="input" placeholder="YouTube URL" value={url} disabled={locked}
          onChange={(e) => setUrl(e.target.value)}
        />
        <textarea
          className="input min-h-32" placeholder={`Summary (min. ${MIN_WORDS} words)`} value={summary} disabled={locked}
          onChange={(e) => setSummary(e.target.value)}
        />
        <div className="flex items-center justify-between">
          <p className={`text-xs ${wordCount < MIN_WORDS ? "text-muted-foreground" : "text-green-600"}`}>
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
      </CardContent>
    </Card>
  )
}

export default function Videos() {
  const navigate = useNavigate()
  const { data: videos, isLoading } = useQuery({ queryKey: ["instructor-videos"], queryFn: listVideosApi })

  const allSubmitted = videos?.length === 3 && videos.every((v) => v.status === "submitted")

  if (isLoading || !videos) return <Spinner />

  return (
    <div>
      <PageHeader
        title="Phase 1 — Videos"
        subtitle="Watch each video and write a summary of at least 200 words."
        action={allSubmitted ? <Button onClick={() => void navigate({ to: "/instructors/modules" })}>Continue to modules</Button> : undefined}
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {videos.map((v) => <VideoCard key={v.id} video={v} />)}
      </div>
    </div>
  )
}
