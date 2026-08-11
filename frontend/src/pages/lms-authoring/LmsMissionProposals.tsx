import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { proposalQueueApi, reviewProposalApi, type MissionProposal } from "@/api/missions_proposals"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
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

/** 7B-6 (Missions Phase 2B, 2026-08-12) — the staff side of D7's intake
 * pipeline: interns submit at /interns/propose-mission, staff reviews
 * here. Approving/rejecting never creates a Mission row — integrating an
 * approved proposal into a real, playable mission is deliberate manual
 * engineering work through the existing mission authoring surface, done
 * only after review here (D8: the intern spec doc gets written from that
 * friction, not guessed up front). */
export default function LmsMissionProposals() {
  const { data: queue = [], isLoading } = useQuery({ queryKey: ["missions-proposals-queue"], queryFn: proposalQueueApi })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Mission Proposals"
        subtitle="Intern-submitted mission ideas awaiting review — approving starts the manual integration, it doesn't finish it."
      />

      {isLoading ? (
        <Spinner />
      ) : queue.length === 0 ? (
        <EmptyState title="Nothing to review" hint="Intern proposals will show up here once submitted." />
      ) : (
        <div className="flex flex-col gap-4 max-w-2xl">
          {queue.map((p) => <ProposalCard key={p.id} proposal={p} />)}
        </div>
      )}
    </div>
  )
}
