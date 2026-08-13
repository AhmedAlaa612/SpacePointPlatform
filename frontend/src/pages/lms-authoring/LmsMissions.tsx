import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { ChevronRight } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  listMissionsAdminFullApi, updateMissionAdminApi,
  type MissionAdmin, type MissionStatus,
} from "@/api/missions_admin"
import { proposalQueueApi, reviewProposalApi, type MissionProposal } from "@/api/missions_proposals"

const STATUS_LABEL: Record<MissionStatus, string> = {
  draft: "Draft", in_review: "In review", published: "Published", archived: "Archived",
}

const STATUS_BADGE: Record<MissionStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  in_review: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  published: "bg-green-500/15 text-green-600 dark:text-green-400",
  archived: "bg-red-500/15 text-red-600 dark:text-red-400",
}

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

function MissionRow({ mission }: { mission: MissionAdmin }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [error, setError] = useState("")

  const statusMutation = useMutation({
    mutationFn: (status: MissionStatus) => updateMissionAdminApi(mission.id, { status }),
    onSuccess: () => { setError(""); queryClient.invalidateQueries({ queryKey: ["lms-admin-missions"] }) },
    onError: (e) => setError(errorDetail(e, "Couldn't change status")),
  })

  return (
    <div
      onClick={() => void navigate({ to: `/lms-authoring/missions/${mission.id}` })}
      className="flex items-center gap-4 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors cursor-pointer"
    >
      <div className="w-16 h-16 rounded-xl bg-muted shrink-0 overflow-hidden flex items-center justify-center text-[10px] text-muted-foreground">
        {mission.image_url ? (
          <img src={mission.image_url} alt="" className="w-full h-full object-cover" />
        ) : "No image"}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium text-foreground truncate">{mission.title}</p>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_BADGE[mission.status]}`}>
            {STATUS_LABEL[mission.status]}
          </span>
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary capitalize">{mission.kind}</span>
          {mission.track && <span className="text-xs text-muted-foreground">{mission.track}</span>}
        </div>
        {mission.summary && <p className="text-xs text-muted-foreground truncate">{mission.summary}</p>}
        {mission.authored_by_name && <p className="text-xs text-muted-foreground mt-0.5">Author: {mission.authored_by_name}</p>}
        {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
      </div>
      <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
        <select
          value={mission.status}
          disabled={statusMutation.isPending}
          onChange={(e) => statusMutation.mutate(e.target.value as MissionStatus)}
          className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer disabled:opacity-50"
        >
          <option value="draft">Draft</option>
          <option value="in_review">In review</option>
          <option value="published">Published</option>
          <option value="archived">Archived</option>
        </select>
      </div>
      <ChevronRight size={16} className="text-muted-foreground shrink-0" />
    </div>
  )
}

function ProposalCard({ proposal }: { proposal: MissionProposal }) {
  const queryClient = useQueryClient()
  const [notes, setNotes] = useState("")
  const [error, setError] = useState("")

  const reviewMutation = useMutation({
    mutationFn: (status: "in_review" | "approved" | "rejected") =>
      reviewProposalApi(proposal.id, { status, review_notes: notes || null }),
    onSuccess: () => { setError(""); queryClient.invalidateQueries({ queryKey: ["missions-proposals-queue"] }) },
    onError: (e) => setError(errorDetail(e, "Couldn't submit this review")),
  })

  const hasArtifact = !!(proposal.repo_url || proposal.zip_url)

  return (
    <Card className="p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{proposal.title}</p>
          <p className="text-xs text-muted-foreground mt-0.5">by {proposal.submitted_by_name}</p>
        </div>
        <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-md bg-primary/10 text-primary">
          {proposal.status === "in_review" ? "In review" : "Submitted"}
        </span>
      </div>
      <p className="text-sm text-foreground">{proposal.description}</p>
      <div className="flex flex-wrap gap-3 text-xs">
        {proposal.repo_url && <a href={proposal.repo_url} target="_blank" rel="noreferrer" className="text-primary hover:opacity-80">Repo link</a>}
        {proposal.zip_url && <a href={proposal.zip_url} target="_blank" rel="noreferrer" className="text-primary hover:opacity-80">Download zip</a>}
        {!hasArtifact && <span className="text-muted-foreground italic">Waiting on a repo link or zip upload</span>}
      </div>

      <textarea
        value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Review notes (optional)"
        rows={2}
        className="px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
      />
      <div className="flex flex-wrap gap-2">
        {proposal.status === "submitted" && (
          <Button size="sm" variant="secondary" onClick={() => reviewMutation.mutate("in_review")} disabled={!hasArtifact || reviewMutation.isPending}>
            Start review
          </Button>
        )}
        <Button size="sm" onClick={() => reviewMutation.mutate("approved")} disabled={!hasArtifact || reviewMutation.isPending}>
          Approve
        </Button>
        <Button size="sm" variant="destructive" onClick={() => reviewMutation.mutate("rejected")} disabled={!hasArtifact || reviewMutation.isPending}>
          Reject
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </Card>
  )
}

function MissionsTab() {
  const { data: missions = [], isLoading } = useQuery({ queryKey: ["lms-admin-missions"], queryFn: listMissionsAdminFullApi })

  if (isLoading) return <Spinner />
  if (missions.length === 0) {
    return <EmptyState title="No missions yet" hint="Missions are created via the seed scripts or the intern proposal pipeline." />
  }
  return (
    <div className="flex flex-col gap-2">
      {missions.map((m) => <MissionRow key={m.id} mission={m} />)}
    </div>
  )
}

function ProposalsTab() {
  const { data: queue = [], isLoading } = useQuery({ queryKey: ["missions-proposals-queue"], queryFn: proposalQueueApi })

  if (isLoading) return <Spinner />
  if (queue.length === 0) {
    return <EmptyState title="Nothing to review" hint="Intern proposals will show up here once submitted." />
  }
  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      {queue.map((p) => <ProposalCard key={p.id} proposal={p} />)}
    </div>
  )
}

/** Ops-facing mission admin — status control (2026-08-06) plus, as of
 * 2026-08-12, the proposal review queue folded in as a tab (it used to be
 * its own nav entry, `LmsMissionProposals.tsx`; the operator's ask was one
 * fewer sidebar tab, same underlying pages). */
export default function LmsMissions() {
  const [tab, setTab] = useState<"missions" | "proposals">("missions")

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Missions"
        subtitle="Publish or unpublish missions, and review intern-submitted proposals."
      />

      <div className="flex gap-1 border-b border-border w-fit">
        {(["missions", "proposals"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t === "missions" ? "Missions" : "Proposals"}
          </button>
        ))}
      </div>

      {tab === "missions" ? <MissionsTab /> : <ProposalsTab />}
    </div>
  )
}
