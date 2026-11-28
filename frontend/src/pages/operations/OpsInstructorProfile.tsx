import { useMemo, useState } from "react"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  ArrowLeft,
  Award,
  BookOpen,
  Calendar,
  Car,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  CreditCard,
  ExternalLink,
  Eye,
  Globe,
  GraduationCap,
  Layers,
  Mail,
  MapPin,
  Phone,
  Sparkles,
  Star,
  TrendingUp,
  Trophy,
} from "lucide-react"
import { isAxiosError } from "axios"
import {
  getAttemptReviewByIdApi,
  getInstructorPerformanceApi,
  setInstructorCertifiedApi,
  upsertInstructorRatingApi,
} from "@/api/instructor_assessment"
import {
  RATING_DIMENSIONS,
  type CohortRatingSummary,
  type InstructorCohortHistoryEntry,
  type RatingDimensionKey,
  type RatingFlag,
} from "@/types/instructor_assessment"
import { Spinner, StatCard } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/context/AuthContext"
import { useToast } from "@/components/ui/toast"
import { EmptyState, Modal } from "@/pages/admin/components/common"
import { QuestionReviewList } from "@/components/AssessmentReview"
import { InstructorPaymentHistoryPanel } from "@/components/InstructorPaymentHistoryPanel"
import { DocsComplianceChip, OpsIdCardModal } from "@/pages/operations/OpsInstructors"
import { cn } from "@/lib/utils"

const RATING_FLAGS: { key: RatingFlag; label: string }[] = [
  { key: "concern", label: "Concern" },
  { key: "none", label: "None" },
  { key: "exceptional", label: "Exceptional" },
]

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return "?"
  return parts
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()
}

function formatDateRange(startsOn?: string | null, endsOn?: string | null): string {
  if (!startsOn && !endsOn) return "Dates TBD"
  const fmt = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
  if (startsOn && endsOn) return `${fmt(startsOn)} – ${fmt(endsOn)}`
  return startsOn ? `From ${fmt(startsOn)}` : `Until ${fmt(endsOn!)}`
}

export default function OpsInstructorProfile() {
  const { userId } = useParams({ strict: false }) as { userId: string }
  const { activeRole } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()

  const handleBack = () => {
    if (activeRole === "admin" && window.history.length > 1) {
      window.history.back()
      return
    }
    void navigate({ to: "/operations/instructors" })
  }

  const { data: perf, isLoading, isError } = useQuery({
    queryKey: ["instructor-performance", userId],
    queryFn: () => getInstructorPerformanceApi(userId),
  })

  const [cohortTab, setCohortTab] = useState<"all" | "unrated" | "rated">("all")
  const [idCardOpen, setIdCardOpen] = useState(false)
  const [reviewModal, setReviewModal] = useState<{ attemptId: string; cohortName: string } | null>(null)
  const [ratingTarget, setRatingTarget] = useState<InstructorCohortHistoryEntry | null>(null)

  const toggleCertified = useMutation({
    mutationFn: (certified: boolean) => setInstructorCertifiedApi(userId, certified),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["instructor-performance", userId] })
      qc.invalidateQueries({ queryKey: ["ops-instructors"] })
      toast.success(
        res.is_certified
          ? "Certified Instructor label enabled."
          : "Certified Instructor label removed.",
      )
    },
    onError: (err) => {
      const msg =
        isAxiosError(err) && typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : "Could not update certification status."
      toast.error(msg)
    },
  })

  const { filteredCohorts, unratedCount, ratedCount } = useMemo(() => {
    const entries = perf?.cohort_history ?? []
    const unrated = entries.filter((c) => !c.rating).length
    const rated = entries.length - unrated
    const filtered =
      cohortTab === "unrated"
        ? entries.filter((c) => !c.rating)
        : cohortTab === "rated"
        ? entries.filter((c) => !!c.rating)
        : entries
    return { filteredCohorts: filtered, unratedCount: unrated, ratedCount: rated }
  }, [perf?.cohort_history, cohortTab])

  if (isLoading) return <Spinner />

  if (isError || !perf) {
    return (
      <div className="flex flex-col gap-4 max-w-2xl mx-auto py-12">
        <Button
          variant="outline"
          size="sm"
          onClick={handleBack}
          className="self-start gap-1.5"
        >
          <ArrowLeft size={14} /> {activeRole === "admin" ? "Back" : "Back to Instructors"}
        </Button>
        <EmptyState
          icon={<AlertTriangle size={28} />}
          title="Instructor profile unavailable"
          description="We could not load this instructor's Operations performance record."
        />
      </div>
    )
  }

  const reliabilityPct = perf.reliability_ratio != null ? `${Math.round(perf.reliability_ratio * 100)}%` : "—"

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleBack}
          className="gap-1.5"
        >
          <ArrowLeft size={14} /> {activeRole === "admin" ? "Back" : "Back to Instructors"}
        </Button>
      </div>

      {/* Section A — Identity, Compliance, ID Card & Certification Toggle */}
      <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5 sm:p-6 flex flex-col gap-5">
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
          {/* Identity */}
          <div className="flex items-start gap-4 min-w-0">
            <div className="w-16 h-16 rounded-full bg-muted border-2 border-border overflow-hidden flex items-center justify-center text-lg font-bold text-foreground shrink-0">
              {perf.photo_url ? (
                <img src={perf.photo_url} alt={perf.full_name} className="w-full h-full object-cover" />
              ) : (
                initialsOf(perf.full_name)
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">{perf.full_name}</h1>
                {perf.card_id && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2.5 py-0.5 text-xs font-mono font-semibold text-primary">
                    <CreditCard size={12} />
                    {perf.card_id}
                  </span>
                )}
                <DocsComplianceChip complete={perf.docs_complete} />
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <Mail size={12} /> {perf.email}
                </span>
                {perf.phone && (
                  <span className="inline-flex items-center gap-1">
                    <Phone size={12} /> {perf.phone}
                  </span>
                )}
                {perf.nationality && (
                  <span className="inline-flex items-center gap-1">
                    <Globe size={12} /> {perf.nationality}
                  </span>
                )}
                {perf.graduated_university && (
                  <span className="inline-flex items-center gap-1">
                    <GraduationCap size={12} /> {perf.graduated_university}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Right Controls: ID Card + Certification Toggle */}
          <div className="flex flex-wrap items-center gap-3 shrink-0">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setIdCardOpen(true)}
              className="h-9 gap-1.5 text-xs font-semibold"
            >
              <CreditCard size={14} /> View ID Card
            </Button>

            <button
              type="button"
              disabled={toggleCertified.isPending}
              onClick={() => toggleCertified.mutate(!perf.is_certified)}
              className={cn(
                "inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition-all disabled:opacity-50",
                perf.is_certified
                  ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/25"
                  : "border-border bg-background text-foreground hover:border-primary/50 hover:text-primary",
              )}
            >
              <Award size={14} />
              {perf.is_certified ? "Certified" : "+ Certify"}
            </button>
          </div>
        </div>

        {/* Delivery Readiness Strip */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-4 border-t border-border/70 text-xs">
          <div className="rounded-xl bg-muted/40 border border-border/60 p-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
              Home City
            </span>
            <span className="inline-flex items-center gap-1.5 font-semibold text-foreground">
              <MapPin size={13} className="text-primary" />
              {perf.city_name ?? "Not set"}
            </span>
          </div>

          <div className="rounded-xl bg-muted/40 border border-border/60 p-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
              Can Deliver In
            </span>
            {perf.deliver_city_names.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {perf.deliver_city_names.map((c) => (
                  <span
                    key={c}
                    className="rounded-full bg-primary/10 border border-primary/20 px-2 py-0.5 text-[11px] font-medium text-primary"
                  >
                    {c}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-muted-foreground italic">Not set</span>
            )}
          </div>

          <div className="rounded-xl bg-muted/40 border border-border/60 p-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
              Transportation
            </span>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 font-semibold",
                perf.has_own_transportation ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground",
              )}
            >
              <Car size={13} />
              {perf.has_own_transportation ? "Yes — Own Car" : "No — Needs Transport"}
            </span>
          </div>

          <div className="rounded-xl bg-muted/40 border border-border/60 p-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
              Fluent Languages
            </span>
            <span className="font-semibold text-foreground">
              {perf.fluent_languages.length > 0 ? perf.fluent_languages.join(", ") : "Not specified"}
            </span>
          </div>
        </div>
      </div>

      {/* Section B — Aggregated Auto-Calculated Performance */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <h2 className="font-display text-lg font-bold text-foreground">Aggregated Performance</h2>
          {perf.recent_rating_trend.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground flex-wrap">
              <TrendingUp size={14} className="text-primary" />
              <span>Recent ratings:</span>
              {perf.recent_rating_trend.map((v, idx) => (
                <span
                  key={idx}
                  className="rounded-md bg-muted px-2 py-0.5 font-mono font-semibold text-foreground"
                >
                  {v.toFixed(1)}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          <StatCard
            icon={<Trophy size={18} />}
            label="Sessions Delivered"
            value={`${perf.total_sessions_delivered} / ${perf.total_sessions_assigned}`}
          />
          <StatCard icon={<Clock size={18} />} label="Hours Delivered" value={`${perf.total_hours_delivered}h`} />
          <StatCard
            icon={<CheckCircle2 size={18} />}
            label="Reliability"
            value={reliabilityPct}
          />
          <StatCard
            icon={<Layers size={18} />}
            label="Cohorts & Programs"
            value={`${perf.cohorts_participated_in} / ${perf.programs_participated_in}`}
          />
          <StatCard
            icon={<Star size={18} />}
            label="Overall Rating"
            value={perf.average_rating != null ? `${perf.average_rating.toFixed(1)} / 5` : "—"}
          />
        </div>

        {/* 10-Dimension Averages Breakdown */}
        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              10-Dimension Performance Averages
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3">
            {RATING_DIMENSIONS.map((d) => {
              const val = perf.dimension_averages?.[d.key]
              const pct = val != null ? Math.min(100, Math.max(0, (val / 5) * 100)) : 0
              return (
                <div key={d.key} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-foreground">{d.label}</span>
                    <span className="font-mono font-semibold text-foreground">
                      {val != null ? `${val.toFixed(1)} / 5` : "—"}
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        val == null
                          ? "bg-transparent"
                          : val >= 4.2
                          ? "bg-emerald-500"
                          : val >= 3.0
                          ? "bg-primary"
                          : "bg-rose-500",
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Section C — Cohort-by-Cohort Delivery History & Inline Rating */}
      <div className="flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="font-display text-lg font-bold text-foreground">Cohort Delivery History & Ratings</h2>

          <div className="inline-flex rounded-xl border border-border bg-card p-1 gap-1 self-start">
            {[
              { id: "all", label: `All Cohorts (${perf.cohort_history.length})` },
              { id: "unrated", label: `Needs Rating (${unratedCount})` },
              { id: "rated", label: `Rated (${ratedCount})` },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setCohortTab(tab.id as typeof cohortTab)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
                  cohortTab === tab.id
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {filteredCohorts.length === 0 ? (
          <EmptyState
            icon={<Layers size={28} />}
            title={
              cohortTab === "unrated"
                ? "All cohorts have been rated"
                : cohortTab === "rated"
                ? "No rated cohorts yet"
                : "No cohort delivery history yet"
            }
            description={
              cohortTab === "all"
                ? "Once this instructor is staffed on a cohort or session, their delivery and readiness history will appear here."
                : "Switch tabs above to view other cohorts."
            }
          />
        ) : (
          <div className="flex flex-col gap-4">
            {filteredCohorts.map((entry) => (
              <CohortHistoryCard
                key={entry.cohort_id}
                entry={entry}
                onViewQuizAnswers={(attemptId, cohortName) => setReviewModal({ attemptId, cohortName })}
                onOpenRating={() => setRatingTarget(entry)}
              />
            ))}
          </div>
        )}
      </div>

      {activeRole === "admin" && (
        <InstructorPaymentHistoryPanel userId={userId} />
      )}

      {idCardOpen && (
        <OpsIdCardModal
          userId={userId}
          instructorName={perf.full_name}
          onClose={() => setIdCardOpen(false)}
        />
      )}

      {reviewModal && (
        <AttemptReviewByIdModal
          attemptId={reviewModal.attemptId}
          cohortName={reviewModal.cohortName}
          onClose={() => setReviewModal(null)}
        />
      )}

      {ratingTarget && (
        <InlineRatingModal
          cohortId={ratingTarget.cohort_id}
          cohortName={ratingTarget.cohort_name}
          instructorUserId={userId}
          instructorName={perf.full_name}
          existing={ratingTarget.rating ?? null}
          onClose={() => setRatingTarget(null)}
        />
      )}
    </div>
  )
}

function CohortHistoryCard({
  entry,
  onViewQuizAnswers,
  onOpenRating,
}: {
  entry: InstructorCohortHistoryEntry
  onViewQuizAnswers: (attemptId: string, cohortName: string) => void
  onOpenRating: () => void
}) {
  const [dimsExpanded, setDimsExpanded] = useState(false)
  const r = entry.rating

  return (
    <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5 flex flex-col gap-4">
      {/* Header Row */}
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-bold text-foreground">{entry.cohort_name}</h3>
            {entry.program_name && (
              <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-foreground">
                {entry.program_name}
              </span>
            )}
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                entry.staffing_source === "direct" || entry.staffing_source === "Direct Assigned"
                  ? "border-border bg-muted text-foreground"
                  : "border-primary/30 bg-primary/10 text-primary",
              )}
            >
              {entry.staffing_source === "direct" || entry.staffing_source === "Direct Assigned"
                ? "Direct Assigned"
                : "Cohort Call"}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Calendar size={12} /> {formatDateRange(entry.starts_on, entry.ends_on)}
            </span>
            {entry.city_name && (
              <span className="inline-flex items-center gap-1">
                <MapPin size={12} /> {entry.city_name}
              </span>
            )}
            {entry.role_name && <span>Role: {entry.role_name}</span>}
          </div>
        </div>

        <Link
          to="/operations/cohorts/$cohortId"
          params={{ cohortId: entry.cohort_id }}
          className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline shrink-0"
        >
          Open Cohort <ExternalLink size={12} />
        </Link>
      </div>

      {/* Metrics & Quiz Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 rounded-xl border border-border/70 bg-muted/30 p-3 text-xs">
        <div className="flex items-center justify-between sm:justify-start sm:gap-2">
          <span className="text-muted-foreground">Attendance:</span>
          <strong className="font-semibold text-foreground tabular-nums">
            {entry.sessions_delivered} / {entry.sessions_assigned} sessions
          </strong>
        </div>

        <div className="flex items-center justify-between sm:justify-start sm:gap-2">
          <span className="text-muted-foreground">Hours Delivered:</span>
          <strong className="font-semibold text-foreground tabular-nums">{entry.hours_delivered}h</strong>
        </div>

        <div className="flex items-center justify-between sm:justify-end gap-2">
          {entry.quiz_attempt_id ? (
            <>
              <span className="inline-flex items-center gap-1 text-foreground font-semibold">
                <BookOpen size={12} className="text-primary" />
                Quiz: {entry.quiz_score ?? 0}/{entry.quiz_total ?? 0}
              </span>
              <button
                type="button"
                onClick={() => onViewQuizAnswers(entry.quiz_attempt_id!, entry.cohort_name)}
                className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-2 py-1 text-[11px] font-semibold text-foreground hover:border-primary/50 hover:text-primary transition-colors"
              >
                <Eye size={11} /> View Answers
              </button>
            </>
          ) : (
            <span className="text-muted-foreground italic">No readiness quiz taken</span>
          )}
        </div>
      </div>

      {/* Rating Sub-panel */}
      {!r ? (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3">
          <div className="flex items-center gap-2.5 text-xs text-rose-700 dark:text-rose-300">
            <AlertTriangle size={15} className="shrink-0" />
            <span className="font-semibold">Not rated yet</span>
          </div>
          <Button size="sm" onClick={onOpenRating} className="h-8 gap-1.5 text-xs font-semibold shrink-0">
            <Star size={13} /> Rate Instructor
          </Button>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-background/60 p-4 flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-primary/10 border border-primary/25 px-2.5 py-1 text-sm font-bold text-primary">
                <Star size={14} className="fill-primary text-primary" />
                {r.overall_rating.toFixed(1)} / 5
              </span>

              {r.recommended !== null && r.recommended !== undefined && (
                <span
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
                    r.recommended
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                      : "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300",
                  )}
                >
                  {r.recommended ? "Recommended" : "Not Recommended"}
                </span>
              )}

              {r.flag === "exceptional" && (
                <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
                  <Sparkles size={11} /> Exceptional
                </span>
              )}

              {r.flag === "concern" && (
                <span className="inline-flex items-center gap-1 rounded-full border border-red-500/30 bg-red-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-red-700 dark:text-red-300">
                  <AlertTriangle size={11} /> Concern
                </span>
              )}

              <span className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <span>{r.rater_name ? `Rated by ${r.rater_name}` : "Rated"}</span>
                {r.submitted_at && <span>{new Date(r.submitted_at).toLocaleDateString()}</span>}
              </span>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => setDimsExpanded((v) => !v)}
                className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
              >
                10 Dimensions
                {dimsExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
              <Button size="sm" variant="outline" onClick={onOpenRating} className="h-8 gap-1.5 text-xs font-semibold">
                Edit Rating
              </Button>
            </div>
          </div>

          {(r.strengths || r.areas_for_improvement) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              {r.strengths && (
                <div className="rounded-lg bg-muted/40 p-2.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                    Strengths
                  </span>
                  <p className="text-foreground leading-relaxed">{r.strengths}</p>
                </div>
              )}
              {r.areas_for_improvement && (
                <div className="rounded-lg bg-muted/40 p-2.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                    Areas for Improvement
                  </span>
                  <p className="text-foreground leading-relaxed">{r.areas_for_improvement}</p>
                </div>
              )}
            </div>
          )}

          {dimsExpanded && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 border-t border-border/60 text-xs">
              {RATING_DIMENSIONS.map((d) => {
                const score = r.dimension_scores?.[d.key]
                return (
                  <div key={d.key} className="flex items-center justify-between px-2 py-1 rounded bg-muted/30">
                    <span className="text-muted-foreground">{d.label}</span>
                    <span className="font-mono font-semibold text-foreground">
                      {score != null ? `${score} / 5` : "—"}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AttemptReviewByIdModal({
  attemptId,
  cohortName,
  onClose,
}: {
  attemptId: string
  cohortName: string
  onClose: () => void
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["attempt-review-id", attemptId],
    queryFn: () => getAttemptReviewByIdApi(attemptId),
    retry: false,
  })

  return (
    <Modal title={`Readiness Quiz Review — ${cohortName}`} onClose={onClose} maxWidth="max-w-2xl">
      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No submitted readiness quiz answers could be loaded for this attempt.
        </p>
      ) : (
        <div className="flex flex-col gap-4 max-h-[70vh] overflow-y-auto pr-1">
          <div className="flex items-center justify-between px-1">
            <span className="text-sm text-muted-foreground">Score</span>
            <span className="font-display text-lg font-bold">
              {data.score ?? 0} / {data.total}
            </span>
          </div>
          <QuestionReviewList questions={data.questions} />
        </div>
      )}
    </Modal>
  )
}

function InlineRatingModal({
  cohortId,
  cohortName,
  instructorUserId,
  instructorName,
  existing,
  onClose,
}: {
  cohortId: string
  cohortName: string
  instructorUserId: string
  instructorName: string
  existing: CohortRatingSummary | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()

  const [scores, setScores] = useState<Partial<Record<RatingDimensionKey, number>>>(
    existing?.dimension_scores ?? {},
  )
  const [strengths, setStrengths] = useState(existing?.strengths ?? "")
  const [areas, setAreas] = useState(existing?.areas_for_improvement ?? "")
  const [recommended, setRecommended] = useState<boolean | null>(existing?.recommended ?? null)
  const [flag, setFlag] = useState<RatingFlag>(existing?.flag ?? "none")
  const [error, setError] = useState("")

  const allScored = RATING_DIMENSIONS.every((d) => {
    const v = scores[d.key]
    return typeof v === "number" && v >= 1 && v <= 5
  })

  const overall = allScored
    ? Math.round(
        (RATING_DIMENSIONS.reduce((sum, d) => sum + (scores[d.key] ?? 0), 0) / RATING_DIMENSIONS.length) * 10,
      ) / 10
    : null

  const saveRating = useMutation({
    mutationFn: () =>
      upsertInstructorRatingApi(cohortId, instructorUserId, {
        dimension_scores: scores as Record<string, number>,
        strengths: strengths.trim() || null,
        areas_for_improvement: areas.trim() || null,
        recommended,
        flag,
        submit: true,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-performance", instructorUserId] })
      qc.invalidateQueries({ queryKey: ["ops-instructors"] })
      qc.invalidateQueries({ queryKey: ["instructor-rating", cohortId, instructorUserId] })
      toast.success(existing ? "Cohort rating updated." : "Cohort rating submitted.")
      onClose()
    },
    onError: (err) => {
      const msg =
        isAxiosError(err) && typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : "Could not save rating."
      setError(msg)
    },
  })

  return (
    <Modal
      title={`${existing ? "Edit Rating" : "Rate"} — ${instructorName}`}
      onClose={onClose}
      maxWidth="max-w-2xl"
    >
      <div className="flex flex-col gap-4 max-h-[75vh] overflow-y-auto pr-1">
        <div className="flex items-center justify-between rounded-xl border border-border bg-muted/40 px-3.5 py-2 text-xs">
          <span className="text-muted-foreground">Cohort</span>
          <strong className="font-semibold text-foreground">{cohortName}</strong>
        </div>

        <div className="rounded-xl border border-border bg-background/60 p-4 flex flex-col divide-y divide-border">
          {RATING_DIMENSIONS.map((d) => (
            <div key={d.key} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
              <span className="text-xs sm:text-sm font-medium text-foreground">{d.label}</span>
              <div className="flex items-center gap-1 shrink-0">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setScores((prev) => ({ ...prev, [d.key]: n }))}
                    className="p-0.5"
                    aria-label={`${d.label}: ${n} stars`}
                  >
                    <Star
                      size={18}
                      className={(scores[d.key] ?? 0) >= n ? "fill-primary text-primary" : "text-muted-foreground"}
                    />
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between rounded-xl border border-border bg-muted/30 px-4 py-3">
          <span className="text-xs font-medium text-muted-foreground">Overall Rating (average of 10 dimensions)</span>
          <span className="font-display text-lg font-bold text-foreground">
            {overall != null ? overall.toFixed(1) : "—"}{" "}
            <span className="text-xs font-normal text-muted-foreground">/ 5</span>
          </span>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Strengths</label>
          <textarea
            value={strengths}
            onChange={(e) => setStrengths(e.target.value)}
            rows={2}
            placeholder="What did they do particularly well?"
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-xs sm:text-sm focus:outline-none focus:border-primary resize-none"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Areas for Improvement
          </label>
          <textarea
            value={areas}
            onChange={(e) => setAreas(e.target.value)}
            rows={2}
            placeholder="What should they focus on before the next cohort?"
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-xs sm:text-sm focus:outline-none focus:border-primary resize-none"
          />
        </div>

        <div className="flex flex-wrap gap-6">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Recommended for future cohorts
            </label>
            <div className="flex rounded-xl border border-border overflow-hidden w-fit">
              {[
                { v: true, l: "Yes" },
                { v: false, l: "No" },
              ].map(({ v, l }) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => setRecommended(v)}
                  className={cn(
                    "px-4 py-1.5 text-xs font-semibold transition-colors",
                    recommended === v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Flag</label>
            <div className="flex rounded-xl border border-border overflow-hidden w-fit">
              {RATING_FLAGS.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setFlag(key)}
                  className={cn(
                    "px-3.5 py-1.5 text-xs font-semibold transition-colors",
                    flag === key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!allScored || saveRating.isPending}
            onClick={() => saveRating.mutate()}
          >
            {saveRating.isPending ? "Saving…" : existing ? "Save Changes" : "Submit Rating"}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
