import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CheckCircle2, Clock, FileVideo, ListChecks, XCircle } from "lucide-react"
import { getApplicationStatusApi, reopenApplicationApi, submitPresentationApi } from "@/api/instructors/applicant"
import { STATUS_LABEL } from "@/types/instructors"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function Status() {
  const qc = useQueryClient()
  const [videoLink, setVideoLink] = useState("")

  const { data: status, isLoading } = useQuery({ queryKey: ["instructor-status"], queryFn: getApplicationStatusApi })

  const reopen = useMutation({
    mutationFn: reopenApplicationApi,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  const submitPresentation = useMutation({
    mutationFn: () => submitPresentationApi(videoLink),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  if (isLoading || !status) return <Spinner />

  return (
    <div>
      <PageHeader title="Application Status" subtitle="Track your progress through the instructor pipeline." />

      <Card>
        <CardContent className="p-6">
          {status.status === "in_progress" && (
            <div className="flex items-start gap-3">
              <Clock className="text-primary shrink-0 mt-0.5" size={22} />
              <div>
                <p className="font-semibold">In progress</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Submit your{" "}
                  <Link to="/instructors/videos" className="text-primary underline">video summaries</Link>{" "}
                  and{" "}
                  <Link to="/instructors/modules" className="text-primary underline">checklist modules</Link>{" "}
                  to move to review.
                </p>
              </div>
            </div>
          )}

          {status.status === "under_review" && (
            <div className="flex items-start gap-3">
              <ListChecks className="text-primary shrink-0 mt-0.5" size={22} />
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
                <FileVideo className="text-primary shrink-0 mt-0.5" size={22} />
                <div>
                  <p className="font-semibold">Phase 1 approved</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Record and submit a 10-15 minute presentation (max 10 slides) covering CubeSat fundamentals,
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
                  <input
                    className="input flex-1" placeholder="YouTube or Drive link" value={videoLink}
                    onChange={(e) => setVideoLink(e.target.value)} required
                  />
                  <Button type="submit" disabled={submitPresentation.isPending}>
                    {submitPresentation.isPending ? "Submitting…" : "Submit presentation"}
                  </Button>
                </form>
              )}
            </div>
          )}

          {status.status === "approved" && (
            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-green-600 shrink-0 mt-0.5" size={22} />
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
                <XCircle className="text-destructive shrink-0 mt-0.5" size={22} />
                <div>
                  <p className="font-semibold">{STATUS_LABEL.rejected}</p>
                  {status.feedback && <p className="text-sm text-muted-foreground mt-1">{status.feedback}</p>}
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
