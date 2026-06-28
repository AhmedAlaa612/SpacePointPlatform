import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CheckCircle2, Circle, Clock, FileVideo, ListChecks, XCircle } from "lucide-react"
import {
  getApplicationStatusApi,
  listVideosApi,
  listModulesApi,
  reopenApplicationApi,
  submitApplicationApi,
  submitPresentationApi,
} from "@/api/instructors/applicant"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"

function ProgressRow({
  done,
  total,
  label,
  to,
}: {
  done: number
  total: number
  label: string
  to: string
}) {
  const complete = done === total && total > 0
  return (
    <Link to={to as any} className="flex items-center gap-3 group">
      {complete ? (
        <CheckCircle2 size={18} className="text-green-600 shrink-0" />
      ) : (
        <Circle size={18} className="text-muted-foreground shrink-0" />
      )}
      <span className={`text-sm flex-1 group-hover:text-foreground ${complete ? "text-foreground" : "text-muted-foreground"}`}>
        {label}
      </span>
      <span className={`text-xs font-semibold tabular-nums ${complete ? "text-green-600" : "text-muted-foreground"}`}>
        {done}/{total}
      </span>
    </Link>
  )
}

export default function Status() {
  const qc = useQueryClient()
  const [videoLink, setVideoLink] = useState("")

  const { data: status, isLoading, isError } = useQuery({
    queryKey: ["instructor-status"],
    queryFn: getApplicationStatusApi,
  })
  const { data: videos } = useQuery({
    queryKey: ["instructor-videos"],
    queryFn: listVideosApi,
    enabled: status?.status === "in_progress",
  })
  const { data: modules } = useQuery({
    queryKey: ["instructor-modules"],
    queryFn: listModulesApi,
    enabled: status?.status === "in_progress",
  })

  const reopen = useMutation({
    mutationFn: reopenApplicationApi,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  const submitApp = useMutation({
    mutationFn: submitApplicationApi,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  const submitPresentation = useMutation({
    mutationFn: () => submitPresentationApi(videoLink),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  if (isLoading) return <Spinner />
  if (isError || !status) return (
    <div>
      <PageHeader title="Application Status" subtitle="Track your progress through the instructor pipeline." />
      <p className="text-sm text-muted-foreground">No application found. Please apply first.</p>
    </div>
  )

  const videosSubmitted = videos?.filter((v) => v.status === "submitted").length ?? 0
  const videosDone = videosSubmitted === 3
  const modulesUploaded = modules?.filter((m) => m.submission_status && m.submission_status !== "rejected").length ?? 0
  const modulesDone = modules ? modulesUploaded === modules.length && modules.length > 0 : false
  const canSubmit = videosDone && modulesDone

  return (
    <div>
      <PageHeader title="Application Status" subtitle="Track your progress through the instructor pipeline." />

      <Card>
        <CardContent className="p-6 space-y-5">

          {status.status === "in_progress" && (
            <>
              <div className="flex items-center gap-3">
                <Clock className="text-primary shrink-0" size={20} />
                <p className="font-semibold">In progress</p>
              </div>

              <div className="border-t border-border pt-4 flex flex-col gap-3">
                <ProgressRow
                  done={videosSubmitted}
                  total={3}
                  label="Video summaries"
                  to="/instructors/videos"
                />
                <ProgressRow
                  done={modulesUploaded}
                  total={modules?.length ?? 0}
                  label="Checklist modules"
                  to="/instructors/modules"
                />
              </div>

              {canSubmit && (
                <div className="border-t border-border pt-4">
                  {submitApp.isError && (
                    <p className="text-sm text-destructive mb-3">
                      {(submitApp.error as any)?.response?.data?.detail || "Could not submit application."}
                    </p>
                  )}
                  <Button onClick={() => submitApp.mutate()} disabled={submitApp.isPending}>
                    {submitApp.isPending ? "Submitting…" : "Submit application"}
                  </Button>
                </div>
              )}
            </>
          )}

          {status.status === "under_review" && (
            <div className="flex items-start gap-3">
              <ListChecks className="text-primary shrink-0 mt-0.5" size={20} />
              <div>
                <p className="font-semibold">Under review</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Our team is reviewing your submission. We'll notify you once a decision is made.
                </p>
              </div>
            </div>
          )}

          {status.status === "phase_1_approved" && (
            <div>
              <div className="flex items-start gap-3 mb-4">
                <FileVideo className="text-primary shrink-0 mt-0.5" size={20} />
                <div>
                  <p className="font-semibold">Phase 1 approved</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Record and submit a 10–15 minute presentation (max 10 slides) covering CubeSat fundamentals,
                    subsystems, onboard memory, and communications.
                  </p>
                </div>
              </div>
              {status.presentation_video_link ? (
                <p className="text-sm text-muted-foreground">Submitted: {status.presentation_video_link}</p>
              ) : (
                <form
                  onSubmit={(e) => { e.preventDefault(); submitPresentation.mutate() }}
                  className="flex flex-col sm:flex-row gap-2"
                >
                  <div className="flex-1">
                    <input
                      className="input"
                      placeholder="YouTube or Drive link"
                      value={videoLink}
                      onChange={(e) => setVideoLink(e.target.value)}
                      required
                    />
                  </div>
                  <Button type="submit" disabled={submitPresentation.isPending}>
                    {submitPresentation.isPending ? "Submitting…" : "Submit presentation"}
                  </Button>
                </form>
              )}
            </div>
          )}

          {status.status === "approved" && (
            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-green-600 shrink-0 mt-0.5" size={20} />
              <div>
                <p className="font-semibold">Approved!</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Check your email for login credentials and your signed agreement.
                </p>
              </div>
            </div>
          )}

          {status.status === "rejected" && (
            <div>
              <div className="flex items-start gap-3 mb-4">
                <XCircle className="text-destructive shrink-0 mt-0.5" size={20} />
                <div>
                  <p className="font-semibold">Not accepted</p>
                  {status.feedback && (
                    <p className="text-sm text-muted-foreground mt-1">{status.feedback}</p>
                  )}
                </div>
              </div>
              <Button onClick={() => reopen.mutate()} disabled={reopen.isPending} variant="outline">
                {reopen.isPending ? "Reopening…" : "Reopen application"}
              </Button>
            </div>
          )}

        </CardContent>
      </Card>
    </div>
  )
}
