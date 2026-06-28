import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { ArrowLeft, Check, ExternalLink, FileText, Video, Play, CheckCircle2, XCircle, AlertCircle, MessageSquare } from "lucide-react"
import { getApplicantDetailApi, reviewApplicantApi } from "@/api/instructors/admin"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState, Spinner, StatusPill } from "@/pages/instructors/components/common"
import { cn } from "@/lib/utils"

export default function ApplicantReviewPage() {
  const { userId } = useParams({ from: "/auth/instructors/admin/applicants/$userId" })
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [feedback, setFeedback] = useState("")

  const { data: detail, isLoading, isError } = useQuery({
    queryKey: ["admin-applicant-detail", userId],
    queryFn: () => getApplicantDetailApi(userId),
    enabled: !!userId,
  })

  const review = useMutation({
    mutationFn: (status: string) => reviewApplicantApi(userId, status, feedback || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-applicants"] })
      qc.invalidateQueries({ queryKey: ["admin-applicant-detail", userId] })
      qc.invalidateQueries({ queryKey: ["admin-overview"] })
      setFeedback("")
      void navigate({ to: "/instructors/admin" })
    },
  })

  if (isLoading) return <Spinner />
  if (isError || !detail) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <AlertCircle className="w-12 h-12 text-destructive mb-3" />
        <p className="font-semibold text-foreground">Applicant not found</p>
        <Link to="/instructors/admin" className="text-primary hover:underline mt-2 text-sm">
          Go back to Admin
        </Link>
      </div>
    )
  }

  const reviewStatus = detail.review?.status ?? "in_progress"

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto pb-12 animate-fade-in">
      {/* Back button */}
      <div>
        <Link
          to="/instructors/admin"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors group"
        >
          <ArrowLeft size={16} className="group-hover:-translate-x-0.5 transition-transform" />
          Back to Applications
        </Link>
      </div>

      {/* Header card with glassmorphism style */}
      <div className="relative overflow-hidden rounded-2xl border border-border/80 bg-card/65 p-6 shadow-md backdrop-blur-md">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">{detail.full_name}</h1>
            <p className="text-sm text-muted-foreground mt-1">{detail.email}</p>
            {detail.profile && (
              <p className="text-sm text-muted-foreground mt-0.5">
                {[detail.profile.university, detail.profile.city_of_residence, detail.profile.country]
                  .filter(Boolean)
                  .join(" — ")}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">Status:</span>
            <StatusPill status={reviewStatus} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Left 2 Columns: Application Submissions */}
        <div className="lg:col-span-2 space-y-6">
          {/* Phase 1: Video Submissions */}
          <Card className="border-border/80 bg-card/40 backdrop-blur-sm">
            <CardHeader className="flex flex-row items-center gap-2 border-b border-border/40 pb-4">
              <Video className="w-5 h-5 text-primary" />
              <CardTitle className="text-base font-bold">Phase 1: Training Video Summaries</CardTitle>
            </CardHeader>
            <CardContent className="p-5 space-y-4">
              {detail.videos && detail.videos.length > 0 ? (
                detail.videos.map((v: any) => {
                  const isSubmitted = v.status === "submitted"
                  return (
                    <div
                      key={v.id}
                      className={cn(
                        "rounded-xl border p-4 transition-all bg-card/30",
                        isSubmitted ? "border-primary/25 shadow-sm" : "border-border/60 opacity-70"
                      )}
                    >
                      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                        <span className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wide">
                          <Play size={12} className="text-primary" /> Video {v.video_no}
                        </span>
                        <span
                          className={cn(
                            "text-[10px] font-semibold px-2.5 py-0.5 rounded-full border",
                            isSubmitted
                              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                              : "bg-muted text-muted-foreground border-border"
                          )}
                        >
                          {v.status === "submitted" ? "SUBMITTED" : "DRAFT"}
                        </span>
                      </div>

                      {v.youtube_url && (
                        <p className="text-xs text-foreground font-medium mb-3 truncate flex items-center gap-1.5">
                          <span className="text-muted-foreground">Link:</span>
                          <a
                            href={v.youtube_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-primary underline hover:text-primary/80 transition-colors inline-flex items-center gap-1"
                          >
                            {v.youtube_url}
                            <ExternalLink size={10} />
                          </a>
                        </p>
                      )}

                      {v.summary_text ? (
                        <div className="bg-card p-3 rounded-xl border border-border/50 text-xs">
                          <p className="font-semibold text-foreground/80 mb-1">Summary ({v.word_count} words):</p>
                          <p className="text-muted-foreground whitespace-pre-wrap leading-relaxed">{v.summary_text}</p>
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground italic">No summary submitted yet.</p>
                      )}
                    </div>
                  )
                })
              ) : (
                <EmptyState title="No video submissions found" />
              )}
            </CardContent>
          </Card>

          {/* Phase 1: Checklist Modules & Uploads */}
          <Card className="border-border/80 bg-card/40 backdrop-blur-sm">
            <CardHeader className="flex flex-row items-center gap-2 border-b border-border/40 pb-4">
              <FileText className="w-5 h-5 text-primary" />
              <CardTitle className="text-base font-bold">Phase 1: Checklist Modules & Tasks</CardTitle>
            </CardHeader>
            <CardContent className="p-5 space-y-4">
              {detail.modules && detail.modules.length > 0 ? (
                detail.modules.map((m: any) => {
                  const hasSub = !!m.submission
                  const subStatus = m.submission?.status
                  const checkedCount = m.checklist_items.filter((it: any) => it.is_completed).length
                  const totalCount = m.checklist_items.length

                  return (
                    <div key={m.id} className="rounded-xl border border-border/60 bg-card/30 p-4 space-y-3">
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <p className="font-bold text-sm text-foreground">{m.title}</p>
                        <span className="text-[10px] font-semibold bg-muted px-2 py-0.5 rounded-full text-muted-foreground">
                          {checkedCount} / {totalCount} Items Completed
                        </span>
                      </div>

                      {/* Checklist items list */}
                      <ul className="space-y-1 bg-card/25 p-3 rounded-lg border border-border/30">
                        {m.checklist_items.map((it: any) => (
                          <li key={it.id} className="flex items-center gap-2 text-xs">
                            <span className={cn(
                              "w-3.5 h-3.5 rounded flex items-center justify-center border",
                              it.is_completed
                                ? "bg-primary border-primary text-primary-foreground"
                                : "border-border"
                            )}>
                              {it.is_completed && <Check size={10} />}
                            </span>
                            <span className={cn(it.is_completed ? "text-foreground" : "text-muted-foreground")}>
                              {it.title}
                            </span>
                          </li>
                        ))}
                      </ul>

                      {/* Module file upload submission */}
                      {hasSub ? (
                        <div className="bg-card/50 border border-border/50 rounded-xl p-3 text-xs space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-foreground/80">Uploaded File Submission</span>
                            <span className={cn(
                              "text-[9px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wider",
                              subStatus === "approved" && "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
                              subStatus === "submitted" && "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
                              subStatus === "rejected" && "bg-destructive/10 text-destructive border-destructive/20"
                            )}>
                              {subStatus}
                            </span>
                          </div>

                          <p className="truncate flex items-center gap-1">
                            <span className="text-muted-foreground">File:</span>
                            <a
                              href={m.submission.file_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-primary underline font-medium inline-flex items-center gap-0.5"
                            >
                              {m.submission.original_filename || "Download Submission"}
                              <ExternalLink size={10} />
                            </a>
                          </p>

                          {m.submission.notes_text && (
                            <div className="text-muted-foreground bg-card/85 p-2 rounded border border-border/30 mt-1">
                              <span className="font-semibold text-[10px] text-foreground block mb-0.5">Notes:</span>
                              <p className="whitespace-pre-wrap">{m.submission.notes_text}</p>
                            </div>
                          )}

                          {m.submission.feedback && (
                            <div className="text-amber-700 dark:text-amber-400 bg-amber-500/5 p-2 rounded border border-amber-500/10 mt-1">
                              <span className="font-semibold text-[10px] block mb-0.5">Reviewer feedback:</span>
                              <p className="whitespace-pre-wrap">{m.submission.feedback}</p>
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground italic">No file submission uploaded for this module.</p>
                      )}
                    </div>
                  )
                })
              ) : (
                <p className="text-sm text-muted-foreground italic">No checklist modules found.</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right 1 Column: Phase 2 + Actions */}
        <div className="space-y-6">
          {/* Phase 2 Card */}
          <Card className="border-border/80 bg-card/40 backdrop-blur-sm">
            <CardHeader className="flex flex-row items-center gap-2 border-b border-border/40 pb-4">
              <CheckCircle2 className="w-5 h-5 text-primary" />
              <CardTitle className="text-base font-bold">Phase 2: Presentation</CardTitle>
            </CardHeader>
            <CardContent className="p-5 space-y-3">
              {detail.presentation_link ? (
                <div className="bg-muted/40 border border-primary/20 rounded-xl p-3.5 text-sm space-y-2">
                  <div className="flex items-center gap-1.5 text-xs text-primary font-bold uppercase tracking-wider mb-1">
                    <CheckCircle2 size={13} /> Presentation Submitted
                  </div>
                  <p className="text-xs text-muted-foreground">The applicant has uploaded their presentation video link:</p>
                  <a
                    href={detail.presentation_link}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary underline font-medium text-xs break-all inline-flex items-center gap-1"
                  >
                    {detail.presentation_link}
                    <ExternalLink size={10} />
                  </a>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-6 text-center text-muted-foreground">
                  <AlertCircle className="w-8 h-8 opacity-40 mb-2" />
                  <p className="text-xs font-semibold">Presentation not submitted yet</p>
                  <p className="text-[10px] max-w-[180px] mt-0.5">Required for Phase 2 final review</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Action Card */}
          <Card className="border-border/80 bg-card/60 backdrop-blur-md shadow-lg">
            <CardHeader className="border-b border-border/40 pb-4">
              <CardTitle className="text-base font-bold flex items-center gap-1.5">
                <MessageSquare size={16} className="text-primary" />
                Application Decision
              </CardTitle>
            </CardHeader>
            <CardContent className="p-5 space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                  Review Feedback
                </label>
                <textarea
                  className="input min-h-[100px] py-2 resize-none text-xs bg-background/50 border-border focus:border-primary"
                  placeholder="Provide feedback to the applicant..."
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
              </div>

              <div className="flex flex-col gap-2 pt-2 border-t border-border/40">
                <Button
                  className="w-full gap-1.5 justify-center py-2.5"
                  onClick={() => review.mutate("phase_1_approved")}
                  disabled={(reviewStatus === "phase_1_approved" || reviewStatus === "approved" || reviewStatus === "rejected") || review.isPending}
                >
                  <Check size={14} /> Approve Phase 1
                </Button>
                <Button
                  className="w-full gap-1.5 justify-center py-2.5 bg-affair dark:bg-heliotrope hover:opacity-90 transition-opacity"
                  onClick={() => review.mutate("approved")}
                  disabled={(reviewStatus === "approved" || reviewStatus === "rejected") || review.isPending}
                >
                  <CheckCircle2 size={14} /> Final Approve
                </Button>
                <Button
                  variant="destructive"
                  className="w-full gap-1.5 justify-center py-2.5"
                  onClick={() => review.mutate("rejected")}
                  disabled={(reviewStatus === "approved" || reviewStatus === "rejected") || review.isPending}
                >
                  <XCircle size={14} /> Reject Application
                </Button>
              </div>

              {review.isPending && (
                <div className="flex items-center justify-center py-1">
                  <span className="text-xs text-muted-foreground animate-pulse">Submitting decision...</span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
