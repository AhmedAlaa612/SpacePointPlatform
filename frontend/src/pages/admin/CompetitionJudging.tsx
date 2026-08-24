import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import { ArrowLeft, Plus, Trash2, Trophy, UserPlus } from "lucide-react"
import { getCohortApi } from "@/api/sessions/cohorts"
import {
  getCohortExportTop20Api, getCohortJudgesApi, getCohortLeaderboardApi, getProgramRubricApi,
  inviteCohortJudgeApi, publishCohortResultsApi, putProgramRubricApi, revokeCohortJudgeApi,
  unpublishCohortResultsApi,
  type CompetitionJudgeProgress, type CompetitionLeaderboardRow, type CompetitionPublication, type CompetitionRubric,
} from "@/api/competitions"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"
import { Field } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

type JudgingTab = "rubric" | "judges" | "results"
const TABS: { key: JudgingTab; label: string }[] = [
  { key: "rubric", label: "Rubric" },
  { key: "judges", label: "Judges" },
  { key: "results", label: "Results" },
]

export default function CompetitionJudging() {
  const { cohortId } = useParams({ strict: false }) as { cohortId: string }
  const [tab, setTab] = useState<JudgingTab>("rubric")

  const { data: cohort, isLoading } = useQuery({
    queryKey: ["sessions-cohort", cohortId],
    queryFn: () => getCohortApi(cohortId),
  })

  if (isLoading) return <Spinner />
  if (!cohort) {
    return (
      <div className="flex flex-col gap-4">
        <Link to="/operations/cohorts" className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft size={14} /> Cohorts
        </Link>
        <p className="text-sm text-muted-foreground">Cohort not found.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <Link
        to="/operations/cohorts/$cohortId" params={{ cohortId: cohort.id }}
        className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft size={14} /> {cohort.name}
      </Link>

      <PageHeader title={`Judging — ${cohort.name}`} subtitle={cohort.program_name ?? "—"} />

      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "rubric" && <RubricTab programId={cohort.program_id} />}
      {tab === "judges" && <JudgesTab cohortId={cohort.id} />}
      {tab === "results" && <ResultsTab cohortId={cohort.id} />}
    </div>
  )
}

/* ================================================================== */
/* Rubric                                                               */
/* ================================================================== */
function RubricTab({ programId }: { programId: string }) {
  const toast = useToast()
  const { data: rubric, isLoading } = useQuery<CompetitionRubric | null>({
    queryKey: ["competitions-rubric", programId],
    queryFn: () => getProgramRubricApi(programId).catch((e) => {
      if (e?.response?.status === 404) return null
      throw e
    }),
  })

  const [name, setName] = useState("")
  const [criteria, setCriteria] = useState<{ key: string; label: string; max_points: number }[]>([])

  useEffect(() => {
    setName(rubric?.name ?? "Competition Rubric")
    setCriteria(
      rubric?.criteria.map((c) => ({ key: c.key, label: c.label, max_points: c.max_points })) ?? [],
    )
  }, [rubric])

  const queryClient = useQueryClient()
  const saveMutation = useMutation({
    mutationFn: () => putProgramRubricApi(programId, { name, criteria }),
    onSuccess: () => {
      toast.success("Rubric saved")
      queryClient.invalidateQueries({ queryKey: ["competitions-rubric", programId] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to save rubric")),
  })

  if (isLoading) return <Spinner />

  const total = criteria.reduce((sum, c) => sum + (Number(c.max_points) || 0), 0)

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <Field label="Rubric name">
        <input
          value={name} onChange={(e) => setName(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
      </Field>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
            Criteria · {total} pts total
          </label>
          <button
            onClick={() => setCriteria((c) => [...c, { key: `criterion_${c.length + 1}`, label: "", max_points: 10 }])}
            className="flex items-center gap-1 text-xs font-medium text-primary hover:opacity-80"
          >
            <Plus size={12} /> Add criterion
          </button>
        </div>
        {criteria.map((c, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={c.key} placeholder="key"
              onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, key: e.target.value } : x))}
              className="w-32 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-xs font-mono focus:outline-none focus:border-primary"
            />
            <input
              value={c.label} placeholder="Label"
              onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, label: e.target.value } : x))}
              className="flex-1 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
            />
            <input
              value={c.max_points} type="number" min={0}
              onChange={(e) => setCriteria((cs) => cs.map((x, j) => j === i ? { ...x, max_points: Number(e.target.value) } : x))}
              className="w-20 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
            />
            <button
              onClick={() => setCriteria((cs) => cs.filter((_, j) => j !== i))}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {criteria.length === 0 && (
          <p className="text-xs text-muted-foreground">No criteria yet — add at least one before judges can score.</p>
        )}
      </div>

      <button
        onClick={() => saveMutation.mutate()}
        disabled={saveMutation.isPending || criteria.some((c) => !c.key.trim() || !c.label.trim())}
        className="self-start h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
      >
        {saveMutation.isPending ? "Saving…" : "Save rubric"}
      </button>
    </div>
  )
}

/* ================================================================== */
/* Judges                                                               */
/* ================================================================== */
function JudgesTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { data: judges = [], isLoading } = useQuery<CompetitionJudgeProgress[]>({
    queryKey: ["competitions-judges", cohortId],
    queryFn: () => getCohortJudgesApi(cohortId),
  })

  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const inviteMutation = useMutation({
    mutationFn: () => inviteCohortJudgeApi(cohortId, { name: name.trim(), email: email.trim() }),
    onSuccess: () => {
      toast.success("Judge invited")
      setName(""); setEmail("")
      queryClient.invalidateQueries({ queryKey: ["competitions-judges", cohortId] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to invite judge")),
  })
  const revokeMutation = useMutation({
    mutationFn: (userId: string) => revokeCohortJudgeApi(cohortId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["competitions-judges", cohortId] }),
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to remove judge")),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      <div className="flex items-end gap-2">
        <Field label="Name">
          <input
            value={name} onChange={(e) => setName(e.target.value)} placeholder="Dr. Amina Al Suwaidi"
            className="w-48 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <Field label="Email">
          <input
            value={email} onChange={(e) => setEmail(e.target.value)} placeholder="amina@example.com" type="email"
            className="w-64 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <button
          onClick={() => inviteMutation.mutate()}
          disabled={inviteMutation.isPending || !name.trim() || !email.trim()}
          className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
        >
          <UserPlus size={14} /> Invite
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {judges.map((j) => (
          <div key={j.user_id} className="flex items-center justify-between p-3 bg-card border border-border rounded-xl">
            <div>
              <p className="text-sm font-medium text-foreground">{j.full_name}</p>
              <p className="text-xs text-muted-foreground">{j.email}</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">{j.scored_count} / {j.team_count} teams scored</span>
              <button
                onClick={() => { if (confirm(`Remove ${j.full_name} from this cohort's judges?`)) revokeMutation.mutate(j.user_id) }}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
        {judges.length === 0 && <EmptyState title="No judges yet" hint="Invite a judge above to get started." />}
      </div>
    </div>
  )
}

/* ================================================================== */
/* Results                                                              */
/* ================================================================== */
function ResultsTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [showTop20, setShowTop20] = useState(false)

  const { data: board = [], isLoading } = useQuery<CompetitionLeaderboardRow[]>({
    queryKey: ["competitions-leaderboard", cohortId],
    queryFn: () => getCohortLeaderboardApi(cohortId),
  })
  const { data: top20 = [] } = useQuery<CompetitionLeaderboardRow[]>({
    queryKey: ["competitions-top20", cohortId],
    queryFn: () => getCohortExportTop20Api(cohortId),
    enabled: showTop20,
  })

  const publishMutation = useMutation({
    mutationFn: () => publishCohortResultsApi(cohortId),
    onSuccess: (pub: CompetitionPublication) => {
      toast.success(pub.published ? "Results published" : "Results updated")
      queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to publish results")),
  })
  const unpublishMutation = useMutation({
    mutationFn: () => unpublishCohortResultsApi(cohortId),
    onSuccess: () => {
      toast.success("Results unpublished — judges can score again")
      queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to unpublish results")),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button
          onClick={() => publishMutation.mutate()}
          disabled={publishMutation.isPending}
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
        >
          <Trophy size={14} /> Publish results
        </button>
        <button
          onClick={() => unpublishMutation.mutate()}
          disabled={unpublishMutation.isPending}
          className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
        >
          Unpublish
        </button>
        <button
          onClick={() => setShowTop20((s) => !s)}
          className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
        >
          {showTop20 ? "Hide Top 20" : "Show Top 20"}
        </button>
      </div>
      <p className="text-xs text-muted-foreground -mt-2">
        Publishing closes scoring for every judge on this cohort — unpublish to reopen it.
      </p>

      <LeaderboardTable rows={showTop20 ? top20 : board} />
    </div>
  )
}

function LeaderboardTable({ rows }: { rows: CompetitionLeaderboardRow[] }) {
  if (rows.length === 0) return <EmptyState title="No teams yet" hint="Teams appear here once they're formed for this cohort." />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
            <th className="py-2 pr-3">Rank</th>
            <th className="py-2 pr-3">Team</th>
            <th className="py-2 pr-3">Score</th>
            <th className="py-2 pr-3">Judges scored</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.team_id} className="border-b border-border/50">
              <td className="py-2 pr-3 font-semibold tabular-nums">{r.rank}</td>
              <td className="py-2 pr-3 text-foreground">{r.team_name}</td>
              <td className="py-2 pr-3 tabular-nums">{r.score ?? "—"}</td>
              <td className="py-2 pr-3 text-muted-foreground">{r.judges_scored}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
