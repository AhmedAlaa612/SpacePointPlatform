import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CheckCircle2, Circle, Clock, FileVideo, FlaskConical, ListChecks, XCircle } from "lucide-react"
import {
  getApplicationStatusApi,
  getAssessmentQuestionsApi,
  listVideosApi,
  listModulesApi,
  reopenApplicationApi,
  submitAssessmentApi,
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
  const [assessmentFile, setAssessmentFile] = useState<File | null>(null)
  const [assessmentDriveLink, setAssessmentDriveLink] = useState("")
  const [assessmentComments, setAssessmentComments] = useState("")
  const [assessmentError, setAssessmentError] = useState<string | null>(null)

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
  const { data: assessmentQuestions } = useQuery({
    queryKey: ["instructor-assessment-questions"],
    queryFn: getAssessmentQuestionsApi,
    enabled: status?.status === "research_approved",
  })

  const reopen = useMutation({
    mutationFn: reopenApplicationApi,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  const submitPresentation = useMutation({
    mutationFn: () => submitPresentationApi(videoLink),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  const submitAssessment = useMutation({
    mutationFn: () => {
      const form = new FormData()
      if (assessmentFile) form.append("file", assessmentFile)
      if (assessmentDriveLink) form.append("google_drive_link", assessmentDriveLink)
      if (assessmentComments) form.append("comments", assessmentComments)
      return submitAssessmentApi(form)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  const handleAssessmentSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!assessmentFile && !assessmentDriveLink.trim()) {
      setAssessmentError("Please upload a PDF file or provide a Google Drive link.")
      return
    }
    setAssessmentError(null)
    submitAssessment.mutate()
  }

  if (isLoading) return <Spinner />
  if (isError || !status) return (
    <div>
      <PageHeader title="Application Status" subtitle="Track your progress through the instructor pipeline." />
      <p className="text-sm text-muted-foreground">No application found. Please apply first.</p>
    </div>
  )

  const videosSubmitted = videos?.filter((v) => v.status === "submitted").length ?? 0
  const modulesUploaded = modules?.filter((m) => m.submission_status && m.submission_status !== "rejected").length ?? 0

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

          {status.status === "research_approved" && (
            <div>
              <div className="flex items-start gap-3 mb-4">
                <FlaskConical className="text-primary shrink-0 mt-0.5" size={20} />
                <div>
                  <p className="font-semibold">Research approved</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Please complete the 10 Questions Assessment below. Upload your answers as a single PDF.
                    If the PDF exceeds 10MB, upload it to Google Drive (set access to "Anyone with the link")
                    and share the link below.
                  </p>
                </div>
              </div>

              {status.assessment ? (
                <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm space-y-1">
                  <p className="font-semibold">Assessment submitted</p>
                  {status.assessment.file_url && (
                    <p className="text-muted-foreground">
                      File:{" "}
                      <a href={status.assessment.file_url} target="_blank" rel="noreferrer" className="text-primary underline">
                        View PDF
                      </a>
                    </p>
                  )}
                  {status.assessment.google_drive_link && (
                    <p className="text-muted-foreground">
                      Google Drive link:{" "}
                      <a href={status.assessment.google_drive_link} target="_blank" rel="noreferrer" className="text-primary underline break-all">
                        {status.assessment.google_drive_link}
                      </a>
                    </p>
                  )}
                  {status.assessment.comments && (
                    <p className="text-muted-foreground whitespace-pre-wrap">Comments: {status.assessment.comments}</p>
                  )}
                </div>
              ) : (
                <>
                  <div className="flex flex-col gap-3 mb-5">
                    {(assessmentQuestions ?? []).map((q) => (
                      <div key={q.question_id} className="rounded-lg border border-border p-4">
                        <span className="inline-block text-[10px] font-semibold uppercase tracking-wide text-primary bg-primary/10 rounded-full px-2 py-0.5 mb-2">
                          {q.category_id} — {q.category_name}
                        </span>
                        <p className="text-sm text-foreground">{q.task}</p>
                        <div className="mt-2 rounded-md bg-muted/40 p-2.5">
                          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                            Follow-Up Task
                          </p>
                          <p className="text-sm text-muted-foreground">{q.follow_up}</p>
                        </div>
                      </div>
                    ))}
                  </div>

                  <form onSubmit={handleAssessmentSubmit} className="flex flex-col gap-3 border-t border-border pt-4">
                    <div>
                      <label className="text-sm font-medium block mb-1">Upload PDF</label>
                      <input
                        type="file"
                        accept="application/pdf"
                        className="input"
                        onChange={(e) => setAssessmentFile(e.target.files?.[0] ?? null)}
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium block mb-1">Google Drive link (optional)</label>
                      <input
                        className="input"
                        placeholder="https://drive.google.com/..."
                        value={assessmentDriveLink}
                        onChange={(e) => setAssessmentDriveLink(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium block mb-1">Comments (optional)</label>
                      <textarea
                        className="input min-h-[80px]"
                        value={assessmentComments}
                        onChange={(e) => setAssessmentComments(e.target.value)}
                      />
                    </div>
                    {assessmentError && <p className="text-sm text-destructive">{assessmentError}</p>}
                    <Button type="submit" disabled={submitAssessment.isPending} className="self-start">
                      {submitAssessment.isPending ? "Submitting…" : "Submit assessment"}
                    </Button>
                  </form>
                </>
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
