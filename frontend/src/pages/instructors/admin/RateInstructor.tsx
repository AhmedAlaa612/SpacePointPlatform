import { useState } from "react"
import { useNavigate, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowLeft, Star } from "lucide-react"
import { isAxiosError } from "axios"
import { PageHeader, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { getUserProfileApi } from "@/api/auth"
import { getInstructorRatingApi, upsertInstructorRatingApi } from "@/api/instructor_assessment"
import type { InstructorProgramRating } from "@/types/instructor_assessment"
import { RATING_DIMENSIONS, type RatingDimensionKey, type RatingFlag } from "@/types/instructor_assessment"

const FLAGS: { key: RatingFlag; label: string }[] = [
  { key: "concern", label: "Concern" },
  { key: "none", label: "None" },
  { key: "exceptional", label: "Exceptional" },
]

/** Post-program instructor rating form (2026-09) — 10 fixed dimensions,
 *  autosaved as a draft, then a deliberate submit that locks it (same
 *  ratchet contract as competition judging's scores). Fetches first, then
 *  mounts the form seeded with whatever draft already exists — the form's
 *  own state is only ever initialized once, at mount, never synced in from
 *  a later-arriving query via an effect. */
export default function RateInstructor() {
  const { cohortId, instructorUserId } = useParams({ strict: false }) as { cohortId: string; instructorUserId: string }

  const { data: instructor, isLoading: userLoading } = useQuery({
    queryKey: ["user-profile", instructorUserId],
    queryFn: () => getUserProfileApi(instructorUserId),
  })
  const { data: existing, isLoading: ratingLoading } = useQuery({
    queryKey: ["instructor-rating", cohortId, instructorUserId],
    queryFn: () => getInstructorRatingApi(cohortId, instructorUserId),
  })

  if (userLoading || ratingLoading) return <Spinner />

  if (existing?.submitted) {
    return <AlreadySubmittedNotice instructorUserId={instructorUserId} />
  }

  return (
    <RatingForm
      cohortId={cohortId} instructorUserId={instructorUserId}
      instructorName={instructor?.full_name ?? "Instructor"} existing={existing ?? null}
    />
  )
}

function AlreadySubmittedNotice({ instructorUserId }: { instructorUserId: string }) {
  const navigate = useNavigate()
  return (
    <div className="max-w-lg mx-auto flex flex-col gap-3 py-16 text-center">
      <p className="text-sm font-semibold">This rating has already been submitted and can't be edited.</p>
      <Button variant="outline" onClick={() => void navigate({ to: `/instructors/admin/instructors/${instructorUserId}/performance` })}>
        View performance profile
      </Button>
    </div>
  )
}

function RatingForm({ cohortId, instructorUserId, instructorName, existing }: {
  cohortId: string
  instructorUserId: string
  instructorName: string
  existing: InstructorProgramRating | null
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [scores, setScores] = useState<Partial<Record<RatingDimensionKey, number>>>(existing?.dimension_scores ?? {})
  const [strengths, setStrengths] = useState(existing?.strengths ?? "")
  const [areas, setAreas] = useState(existing?.areas_for_improvement ?? "")
  const [recommended, setRecommended] = useState<boolean | null>(existing?.recommended ?? null)
  const [flag, setFlag] = useState<RatingFlag>(existing?.flag ?? "none")
  const [error, setError] = useState("")

  const filled = RATING_DIMENSIONS.every((d) => scores[d.key])
  const overall = filled
    ? Math.round((RATING_DIMENSIONS.reduce((sum, d) => sum + (scores[d.key] ?? 0), 0) / RATING_DIMENSIONS.length) * 10) / 10
    : null

  const submit = useMutation({
    mutationFn: () => upsertInstructorRatingApi(cohortId, instructorUserId, {
      dimension_scores: scores as Record<string, number>,
      strengths: strengths || null,
      areas_for_improvement: areas || null,
      recommended,
      flag,
      submit: true,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instructor-rating", cohortId, instructorUserId] })
      queryClient.invalidateQueries({ queryKey: ["instructor-performance", instructorUserId] })
      void navigate({ to: `/instructors/admin/instructors/${instructorUserId}/performance` })
    },
    onError: (err) => setError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string") ? err.response.data.detail : "Couldn't save this rating.",
    ),
  })

  return (
    <div className="max-w-xl mx-auto flex flex-col gap-6">
      <Button variant="outline" size="sm" onClick={() => window.history.back()} className="self-start gap-1.5">
        <ArrowLeft size={14} /> Back
      </Button>
      <PageHeader title={`Rate ${instructorName}`} subtitle="Post-program performance rating" />

      <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5 flex flex-col divide-y divide-border">
        {RATING_DIMENSIONS.map((d) => (
          <div key={d.key} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
            <span className="text-sm font-medium">{d.label}</span>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} onClick={() => setScores((prev) => ({ ...prev, [d.key]: n }))}>
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

      <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5 flex items-center justify-between">
        <span className="text-sm text-muted-foreground">Overall Rating (average of the 10 dimensions)</span>
        <span className="font-display text-xl font-bold">{overall ?? "—"} <span className="text-sm font-normal text-muted-foreground">/ 5</span></span>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Strengths</label>
        <textarea
          value={strengths} onChange={(e) => setStrengths(e.target.value)} rows={2}
          placeholder="What did they do particularly well?"
          className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Areas for improvement</label>
        <textarea
          value={areas} onChange={(e) => setAreas(e.target.value)} rows={2}
          placeholder="What should they work on before their next session?"
          className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
        />
      </div>

      <div className="flex flex-wrap gap-8">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Recommended for future sessions</label>
          <div className="flex rounded-xl border border-border overflow-hidden w-fit">
            {[{ v: true, l: "Yes" }, { v: false, l: "No" }].map(({ v, l }) => (
              <button
                key={l} onClick={() => setRecommended(v)}
                className={`px-4 py-1.5 text-sm ${recommended === v ? "bg-primary text-primary-foreground font-semibold" : "text-muted-foreground"}`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Flag</label>
          <div className="flex rounded-xl border border-border overflow-hidden w-fit">
            {FLAGS.map(({ key, label }) => (
              <button
                key={key} onClick={() => setFlag(key)}
                className={`px-4 py-1.5 text-sm ${flag === key ? "bg-primary text-primary-foreground font-semibold" : "text-muted-foreground"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <button
        onClick={() => submit.mutate()}
        disabled={!filled || submit.isPending}
        className="h-11 bg-primary text-primary-foreground rounded-xl text-sm font-semibold hover:opacity-90 transition-colors disabled:opacity-50"
      >
        {submit.isPending ? "Submitting…" : "Submit Rating"}
      </button>
    </div>
  )
}
