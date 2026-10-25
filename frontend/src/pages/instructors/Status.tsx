import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CheckCircle2, ChevronRight, FileVideo, FlaskConical, ListChecks, Lock, Send, XCircle } from "lucide-react"
import {
  getApplicationStatusApi,
  getAssessmentQuestionsApi,
  listVideosApi,
  listModulesApi,
  reopenApplicationApi,
  submitApplicationApi,
  submitAssessmentApi,
  submitPresentationApi,
} from "@/api/instructors/applicant"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"
import { ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"

function ProgressRing({ percent }: { percent: number }) {
  const r = 15
  const c = 2 * Math.PI * r
  const dash = (Math.min(100, Math.max(0, percent)) / 100) * c
  return (
    <svg width="28" height="28" viewBox="0 0 36 36" style={{ transform: "rotate(-90deg)" }}>
      <circle cx="18" cy="18" r={r} fill="none" stroke="currentColor" strokeOpacity={0.15} strokeWidth={3} />
      <circle
        cx="18" cy="18" r={r} fill="none" stroke="currentColor" strokeWidth={3}
        strokeLinecap="round" strokeDasharray={`${dash} ${c}`}
      />
    </svg>
  )
}

type StepState = "locked" | "progress" | "complete"

function StepCard({
  title,
  description,
  lockedHint,
  done,
  total,
  state,
  to,
}: {
  title: string
  description: string
  lockedHint?: string
  done: number
  total: number
  state: StepState
  to: string
}) {
  const percent = total > 0 ? Math.round((done / total) * 100) : 0

  const icon =
    state === "complete" ? (
      <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-green-500/10 ring-1 ring-green-500/30 text-green-500">
        <CheckCircle2 size={22} />
      </div>
    ) : state === "locked" ? (
      <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-muted ring-1 ring-border text-muted-foreground">
        <Lock size={18} />
      </div>
    ) : (
      <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/30 text-primary">
        <ProgressRing percent={percent} />
      </div>
    )

  const cta =
    state === "complete" ? (
      <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-green-500/30 bg-green-500/10 px-3.5 py-1.5 text-xs font-semibold text-green-500">
        <CheckCircle2 size={13} /> Completed
      </span>
    ) : state === "locked" ? (
      <span className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border bg-muted/50 px-3.5 py-1.5 text-xs font-semibold text-muted-foreground">
        <Lock size={13} /> Locked
      </span>
    ) : (
      <Button size="sm" className="shrink-0 gap-1">
        {done === 0 ? "Start" : "Continue"} <ChevronRight size={14} />
      </Button>
    )

  const tourSlug = `applicant-step-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`

  const card = (
    <Card
      data-tour={tourSlug}
      className={
        state === "locked"
          ? "border-dashed opacity-80"
          : "transition-all hover:-translate-y-0.5 hover:border-primary/40 cursor-pointer"
      }
    >
      <CardContent className="flex items-center gap-4 p-5">
        {icon}
        <div className="min-w-0 flex-1 flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">{title}</h3>
            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground">
              {done}/{total}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">{state === "locked" && lockedHint ? lockedHint : description}</p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full rounded-full transition-all ${state === "complete" ? "bg-green-500" : "bg-primary"}`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
        {cta}
      </CardContent>
    </Card>
  )

  if (state === "locked") return card
  return <Link to={to as any} className="block">{card}</Link>
}

function SubmitApplicationCard({
  ready,
  pending,
  error,
  onSubmit,
}: {
  ready: boolean
  pending: boolean
  error: string | null
  onSubmit: () => void
}) {
  return (
    <Card className={ready ? "border-primary/40" : "border-dashed opacity-80"}>
      <CardContent className="flex items-center gap-4 p-5">
        <div
          className={`flex size-11 shrink-0 items-center justify-center rounded-full ${
            ready ? "bg-primary/10 ring-1 ring-primary/30 text-primary" : "bg-muted ring-1 ring-border text-muted-foreground"
          }`}
        >
          <Send size={18} />
        </div>
        <div className="min-w-0 flex-1 flex flex-col gap-1">
          <h3 className="text-sm font-semibold">Submit Application</h3>
          <p className="text-xs text-muted-foreground">
            {ready
              ? "Both steps above are complete — submit your application for review."
              : "Complete both steps above to submit your application for review."}
          </p>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <Button size="sm" className="shrink-0" disabled={!ready || pending} onClick={onSubmit}>
          {pending ? "Submitting…" : "Submit Application"}
        </Button>
      </CardContent>
    </Card>
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
    enabled: status?.status === "in_progress" || status?.status === "under_review",
  })
  const { data: modules } = useQuery({
    queryKey: ["instructor-modules"],
    queryFn: listModulesApi,
    enabled: status?.status === "in_progress" || status?.status === "under_review",
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

  const submitApp = useMutation({
    mutationFn: submitApplicationApi,
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
  // Video count is facilitator-editable, not fixed at 3 (2026-09) —
  // "done" compares against however many this applicant actually has.
  const videosTotal = videos?.length ?? 0
  const videosDone = videosTotal > 0 && videosSubmitted === videosTotal
  const modulesTotal = modules?.length ?? 0
  const modulesDone = modulesTotal > 0 && modulesUploaded === modulesTotal

  // "under_review" is reused for later review rounds too (after the
  // presentation, after the assessment) — only show the Phase 1 step cards
  // for the round that's actually about videos/modules, not stale ones for
  // someone whose presentation or assessment is what's actually under review.
  const isPhase1 =
    status.status === "in_progress" ||
    (status.status === "under_review" && !status.assessment && !status.presentation_video_link)

  return (
    <div>
      <PageHeader title="Application Status" subtitle="Track your progress through the instructor pipeline." />

      {isPhase1 ? (
        <div className="flex flex-col gap-4">
          {status.status === "under_review" && (
            <Card>
              <CardContent className="p-6 flex items-start gap-3">
                <ListChecks className="text-primary shrink-0 mt-0.5" size={20} />
                <div>
                  <p className="font-semibold">Under review</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Our team is reviewing your video summaries and checklist modules. You can still
                    view or update your submissions below until they're approved.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
          <StepCard
            title="Video Summaries"
            description={`Watch ${videosTotal || "the"} short video${videosTotal === 1 ? "" : "s"} and write a 200+ word summary of each.`}
            done={videosSubmitted}
            total={videosTotal}
            state={videosDone ? "complete" : "progress"}
            to="/instructors/videos"
          />
          <StepCard
            title="Checklist Modules"
            description="Upload the required research PDFs for each module."
            lockedHint="Locked — submit all video summaries above to unlock."
            done={modulesUploaded}
            total={modulesTotal}
            state={!videosDone ? "locked" : modulesDone ? "complete" : "progress"}
            to="/instructors/modules"
          />
          {status.status === "in_progress" && (
            <SubmitApplicationCard
              ready={videosDone && modulesDone}
              pending={submitApp.isPending}
              error={submitApp.isError ? getErrorMessage(submitApp.error, "Could not submit application.") : null}
              onSubmit={() => submitApp.mutate()}
            />
          )}
        </div>
      ) : (
      <Card>
        <CardContent className="p-6 space-y-5">

          {status.status === "under_review" && (
            <div className="flex items-start gap-3">
              <ListChecks className="text-primary shrink-0 mt-0.5" size={20} />
              <div>
                <p className="font-semibold">Under review</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {status.assessment
                    ? "Our team is reviewing your assessment. We'll notify you once a decision is made."
                    : status.presentation_video_link
                    ? "Our team is reviewing your presentation. We'll notify you once a decision is made."
                    : "Our team is reviewing your video summaries and checklist modules. We'll notify you once a decision is made."}
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
                      <a href={ensureAbsoluteUrl(status.assessment.google_drive_link)} target="_blank" rel="noreferrer" className="text-primary underline break-all">
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
                    <Button
                      type="submit"
                      size="xl"
                      disabled={submitAssessment.isPending}
                      className="self-start rounded-md px-10"
                    >
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
      )}
    </div>
  )
}
