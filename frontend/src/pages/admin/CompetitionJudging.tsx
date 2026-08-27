import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import { ArrowLeft, Plus, Trash2, Trophy, Upload, UserPlus, UserMinus, Pencil, X, Check } from "lucide-react"
import { getCohortApi, getCohortsApi } from "@/api/sessions/cohorts"
import type { Cohort } from "@/types/sessions"
import {
  advanceCohortTeamsApi, createCohortTeamApi, deleteTeamApi, getCohortExportTop20Api,
  getCohortJudgesApi, getCohortLeaderboardApi, getCohortPublicationApi, getCohortTeamsApi, getProgramRubricApi,
  importCohortRegistrationsApi,
  inviteCohortJudgeApi, publishCohortResultsApi, putProgramRubricApi, registerAndAddTeamMemberApi,
  removeTeamMemberApi, renameTeamApi, revokeCohortJudgeApi, unpublishCohortResultsApi,
  type CompetitionImportResult, type CompetitionJudgeProgress, type CompetitionLeaderboardRow,
  type CompetitionPublication, type CompetitionRubric, type CompetitionTeam,
} from "@/api/competitions"
import { PageHeader, Spinner, EmptyState } from "@/components/ui/primitives"
import { Field } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"

type JudgingTab = "roster" | "teams" | "rubric" | "judges" | "results"
const TABS: { key: JudgingTab; label: string }[] = [
  { key: "roster", label: "Roster" },
  { key: "teams", label: "Teams" },
  { key: "rubric", label: "Rubric" },
  { key: "judges", label: "Judges" },
  { key: "results", label: "Results" },
]

export default function CompetitionJudging() {
  const { cohortId } = useParams({ strict: false }) as { cohortId: string }
  const [tab, setTab] = useState<JudgingTab>("roster")

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

      {tab === "roster" && <RosterTab cohortId={cohort.id} />}
      {tab === "teams" && <TeamsTab cohortId={cohort.id} />}
      {tab === "rubric" && <RubricTab programId={cohort.program_id} />}
      {tab === "judges" && <JudgesTab cohortId={cohort.id} />}
      {tab === "results" && <ResultsTab cohortId={cohort.id} programId={cohort.program_id} />}
    </div>
  )
}

/* ================================================================== */
/* Roster (registration import)                                        */
/* ================================================================== */
function RosterTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [result, setResult] = useState<CompetitionImportResult | null>(null)

  const importMutation = useMutation({
    mutationFn: (file: File) => importCohortRegistrationsApi(cohortId, file),
    onSuccess: (res) => {
      setResult(res)
      toast.success(`Imported: ${res.summary.created} created, ${res.summary.matched} matched, ${res.summary.error} errors`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to import roster")),
  })

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <p className="text-sm text-muted-foreground">
        Upload the final roster exported from the registration form — columns <code>team_name</code>,{" "}
        <code>member_name</code>, <code>email</code>, and optionally <code>phone</code>/<code>school</code>.
        Creates a student account, registration, and team per row; re-uploading the same sheet just matches
        instead of duplicating.
      </p>
      <input
        ref={fileInputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
        onChange={(e) => { const file = e.target.files?.[0]; if (file) importMutation.mutate(file); e.target.value = "" }}
      />
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={importMutation.isPending}
        className="self-start flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
      >
        <Upload size={14} /> {importMutation.isPending ? "Importing…" : "Upload roster"}
      </button>

      {result && (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-foreground">
            {result.summary.total} rows · {result.summary.created} created · {result.summary.matched} matched ·{" "}
            {result.summary.error} errors
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
                  <th className="py-2 pr-3">Row</th>
                  <th className="py-2 pr-3">Team</th>
                  <th className="py-2 pr-3">Email</th>
                  <th className="py-2 pr-3">Result</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.row_number} className="border-b border-border/50">
                    <td className="py-2 pr-3 text-muted-foreground">{r.row_number}</td>
                    <td className="py-2 pr-3">{r.team_name ?? "—"}</td>
                    <td className="py-2 pr-3">{r.email ?? "—"}</td>
                    <td className={`py-2 pr-3 ${r.disposition === "error" ? "text-red-600 dark:text-red-400" : "text-foreground"}`}>
                      {r.disposition === "error" ? r.reason : r.disposition}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

/* ================================================================== */
/* Teams (manual management — complements Roster import)               */
/* ================================================================== */
function TeamsTab({ cohortId }: { cohortId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["competitions-teams", cohortId] })

  const { data: teams = [], isLoading } = useQuery<CompetitionTeam[]>({
    queryKey: ["competitions-teams", cohortId],
    queryFn: () => getCohortTeamsApi(cohortId),
  })

  const [newTeamName, setNewTeamName] = useState("")
  const createMutation = useMutation({
    mutationFn: () => createCohortTeamApi(cohortId, newTeamName.trim()),
    onSuccess: () => { setNewTeamName(""); invalidate() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to create team")),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <p className="text-sm text-muted-foreground">
        For one-off corrections after a Roster import — a late signup, a team split, someone switching
        teams — without re-uploading a whole sheet. Adding a member by name + email registers them if
        they're new, or matches an existing account if that email already has one — same as a Roster row.
      </p>

      <div className="flex items-end gap-2">
        <Field label="New team name">
          <input
            value={newTeamName} onChange={(e) => setNewTeamName(e.target.value)} placeholder="Falcon Eye"
            className="w-64 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending || !newTeamName.trim()}
          className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
        >
          <Plus size={14} /> Add team
        </button>
      </div>

      <div className="flex flex-col gap-3">
        {teams.map((team) => (
          <TeamCard key={team.id} team={team} onChanged={invalidate} />
        ))}
        {teams.length === 0 && (
          <EmptyState title="No teams yet" hint="Add one above, or import a roster from the Roster tab." />
        )}
      </div>
    </div>
  )
}

function TeamCard({ team, onChanged }: { team: CompetitionTeam; onChanged: () => void }) {
  const toast = useToast()
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(team.name)
  const [adding, setAdding] = useState(false)
  const [memberName, setMemberName] = useState("")
  const [memberEmail, setMemberEmail] = useState("")

  const renameMutation = useMutation({
    mutationFn: () => renameTeamApi(team.id, name.trim()),
    onSuccess: () => { setRenaming(false); onChanged() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to rename team")),
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteTeamApi(team.id),
    onSuccess: onChanged,
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to delete team")),
  })
  const addMemberMutation = useMutation({
    mutationFn: () => registerAndAddTeamMemberApi(team.id, { full_name: memberName.trim(), email: memberEmail.trim() }),
    onSuccess: () => { setMemberName(""); setMemberEmail(""); setAdding(false); onChanged() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to add member")),
  })
  const removeMemberMutation = useMutation({
    mutationFn: (userId: string) => removeTeamMemberApi(team.id, userId),
    onSuccess: onChanged,
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to remove member")),
  })

  return (
    <div className="p-4 bg-card border border-border rounded-2xl flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        {renaming ? (
          <div className="flex items-center gap-2 flex-1">
            <input
              value={name} onChange={(e) => setName(e.target.value)} autoFocus
              className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
            />
            <button
              onClick={() => renameMutation.mutate()} disabled={renameMutation.isPending || !name.trim()}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
            >
              <Check size={14} />
            </button>
            <button
              onClick={() => { setRenaming(false); setName(team.name) }}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <>
            <p className="text-sm font-semibold text-foreground">{team.name}</p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setRenaming(true)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                title="Rename"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => { if (confirm(`Delete team "${team.name}"?`)) deleteMutation.mutate() }}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
                title="Delete team"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {team.member_names.map((memberFullName, i) => (
          <div key={team.member_ids[i]} className="flex items-center justify-between text-sm">
            <div>
              <span className="text-foreground">{memberFullName}</span>
              <span className="text-muted-foreground text-xs ml-2">{team.member_emails[i]}</span>
            </div>
            <button
              onClick={() => { if (confirm(`Remove ${memberFullName} from ${team.name}?`)) removeMemberMutation.mutate(team.member_ids[i]) }}
              className="p-1 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
              title="Remove from team"
            >
              <UserMinus size={13} />
            </button>
          </div>
        ))}
        {team.member_names.length === 0 && <p className="text-xs text-muted-foreground">No members yet.</p>}
      </div>

      {adding ? (
        <div className="flex items-end gap-2 flex-wrap pt-1 border-t border-border/50">
          <Field label="Name">
            <input
              value={memberName} onChange={(e) => setMemberName(e.target.value)}
              className="w-40 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
            />
          </Field>
          <Field label="Email">
            <input
              value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} type="email"
              className="w-56 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
            />
          </Field>
          <button
            onClick={() => addMemberMutation.mutate()}
            disabled={addMemberMutation.isPending || !memberName.trim() || !memberEmail.trim()}
            className="h-9 px-3 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            {addMemberMutation.isPending ? "Adding…" : "Add"}
          </button>
          <button
            onClick={() => setAdding(false)}
            className="h-9 px-3 border border-border rounded-lg text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          onClick={() => setAdding(true)}
          className="self-start flex items-center gap-1.5 text-xs font-medium text-primary hover:opacity-80 pt-1 border-t border-border/50 w-full justify-start"
        >
          <UserPlus size={13} /> Add member
        </button>
      )}
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
function ResultsTab({ cohortId, programId }: { cohortId: string; programId: string }) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [showTop20, setShowTop20] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [toCohortId, setToCohortId] = useState("")

  const { data: board = [], isLoading } = useQuery<CompetitionLeaderboardRow[]>({
    queryKey: ["competitions-leaderboard", cohortId],
    queryFn: () => getCohortLeaderboardApi(cohortId),
  })
  const { data: top20 = [] } = useQuery<CompetitionLeaderboardRow[]>({
    queryKey: ["competitions-top20", cohortId],
    queryFn: () => getCohortExportTop20Api(cohortId),
    enabled: showTop20,
  })
  const { data: siblingCohorts = [] } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts", programId],
    queryFn: () => getCohortsApi(programId),
  })
  const advanceTargets = siblingCohorts.filter((c) => c.id !== cohortId)

  const { data: publication } = useQuery<CompetitionPublication>({
    queryKey: ["competitions-publication", cohortId],
    queryFn: () => getCohortPublicationApi(cohortId),
  })
  const isPublished = publication?.published ?? false

  const invalidatePublication = () => {
    queryClient.invalidateQueries({ queryKey: ["competitions-publication", cohortId] })
    queryClient.invalidateQueries({ queryKey: ["competitions-leaderboard", cohortId] })
  }
  const publishMutation = useMutation({
    mutationFn: () => publishCohortResultsApi(cohortId),
    onSuccess: () => { toast.success("Results published"); invalidatePublication() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to publish results")),
  })
  const unpublishMutation = useMutation({
    mutationFn: () => unpublishCohortResultsApi(cohortId),
    onSuccess: () => { toast.success("Results unpublished — judges can score again"); invalidatePublication() },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to unpublish results")),
  })
  const advanceMutation = useMutation({
    mutationFn: () => advanceCohortTeamsApi(cohortId, { team_ids: [...selected], to_cohort_id: toCohortId }),
    onSuccess: (results) => {
      const targetName = advanceTargets.find((c) => c.id === toCohortId)?.name ?? "the next stage"
      toast.success(`Advanced ${results.length} team(s) to ${targetName}`)
      setSelected(new Set())
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to advance teams")),
  })

  if (isLoading) return <Spinner />

  const toggleTeam = (teamId: string) => {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(teamId)) next.delete(teamId); else next.add(teamId)
      return next
    })
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <span
          className={`flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${
            isPublished ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
          }`}
        >
          <Trophy size={12} />
          {isPublished
            ? `Published${publication?.published_at ? ` · ${new Date(publication.published_at).toLocaleDateString()}` : ""}`
            : "Not published"}
        </span>
        <button
          onClick={() => (isPublished ? unpublishMutation.mutate() : publishMutation.mutate())}
          disabled={publishMutation.isPending || unpublishMutation.isPending}
          className={`h-9 px-4 rounded-xl text-sm font-medium transition-colors disabled:opacity-50 ${
            isPublished
              ? "border border-border text-foreground hover:bg-muted"
              : "bg-primary text-primary-foreground hover:opacity-90"
          }`}
        >
          {publishMutation.isPending || unpublishMutation.isPending
            ? "Working…"
            : isPublished ? "Unpublish" : "Publish results"}
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

      {advanceTargets.length > 0 ? (
        <div className="flex items-center gap-2 p-3 bg-card border border-border rounded-xl flex-wrap">
          <span className="text-sm text-foreground font-medium">
            {selected.size > 0 ? `${selected.size} team(s) selected` : "Select teams below to advance"}
          </span>
          <select
            value={toCohortId} onChange={(e) => setToCohortId(e.target.value)}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary cursor-pointer"
          >
            <option value="">Advance to…</option>
            {advanceTargets.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button
            onClick={() => advanceMutation.mutate()}
            disabled={advanceMutation.isPending || selected.size === 0 || !toCohortId}
            className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            {advanceMutation.isPending ? "Advancing…" : "Advance selected teams"}
          </button>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground p-3 bg-card border border-dashed border-border rounded-xl">
          No other cohort exists yet under this program to advance teams into — create one (e.g. a Finalist
          stage) on the Cohorts page first, and this control appears here.
        </p>
      )}

      <LeaderboardTable rows={showTop20 ? top20 : board} selected={selected} onToggle={toggleTeam} />
    </div>
  )
}

function LeaderboardTable({ rows, selected, onToggle }: {
  rows: CompetitionLeaderboardRow[]; selected?: Set<string>; onToggle?: (teamId: string) => void
}) {
  if (rows.length === 0) return <EmptyState title="No teams yet" hint="Teams appear here once they're formed for this cohort." />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground uppercase tracking-wider border-b border-border">
            {onToggle && <th className="py-2 pr-3 w-8" />}
            <th className="py-2 pr-3">Rank</th>
            <th className="py-2 pr-3">Team</th>
            <th className="py-2 pr-3">Score</th>
            <th className="py-2 pr-3">Judges scored</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.team_id} className="border-b border-border/50">
              {onToggle && (
                <td className="py-2 pr-3">
                  <input
                    type="checkbox" checked={selected?.has(r.team_id) ?? false}
                    onChange={() => onToggle(r.team_id)}
                  />
                </td>
              )}
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
