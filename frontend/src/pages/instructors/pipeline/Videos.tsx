import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { ChevronRight } from "lucide-react"
import { listVideosApi } from "@/api/instructors/applicant"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function Videos() {
  const { data: videos, isLoading } = useQuery({ queryKey: ["instructor-videos"], queryFn: listVideosApi })

  if (isLoading || !videos) return <Spinner />

  return (
    <div>
      <PageHeader
        title="Phase 1 — Videos"
        subtitle="Watch each video and write a summary of at least 200 words."
      />
      <div className="flex flex-col gap-3">
        {videos.map((v) => (
          <Link key={v.id} to="/instructors/videos/$videoNo" params={{ videoNo: String(v.video_no) }}>
            <Card className="hover:border-primary transition-colors">
              <CardContent className="p-4 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-foreground">Video {v.video_no}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {v.word_count} / 200 words written
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <StatusPill status={v.status} />
                  <ChevronRight className="text-muted-foreground" size={18} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
