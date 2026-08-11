import { useRef, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { Upload } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  myProposalsApi, createProposalApi, uploadProposalZipApi,
  type MissionProposal, type ProposalStatus,
} from "@/api/missions_proposals"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

const STATUS_STYLE: Record<ProposalStatus, string> = {
  submitted: "bg-primary/10 text-primary",
  in_review: "bg-amber-500/10 text-amber-600",
  approved: "bg-emerald-500/10 text-emerald-500",
  rejected: "bg-red-500/10 text-red-500",
}

const STATUS_LABEL: Record<ProposalStatus, string> = {
  submitted: "Submitted", in_review: "In review", approved: "Approved", rejected: "Rejected",
}

function ProposalRow({ proposal }: { proposal: MissionProposal }) {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [zipError, setZipError] = useState("")

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadProposalZipApi(proposal.id, file),
    onSuccess: () => { setZipError(""); queryClient.invalidateQueries({ queryKey: ["missions-proposals-mine"] }) },
    onError: (e) => setZipError(errorDetail(e, "Upload failed")),
  })

  return (
    <Card className="p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{proposal.title}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{proposal.description}</p>
        </div>
        <span className={`shrink-0 text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-md ${STATUS_STYLE[proposal.status]}`}>
          {STATUS_LABEL[proposal.status]}
        </span>
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        {proposal.repo_url && <a href={proposal.repo_url} target="_blank" rel="noreferrer" className="text-primary hover:opacity-80">Repo link</a>}
        {proposal.zip_url && <a href={proposal.zip_url} target="_blank" rel="noreferrer" className="text-primary hover:opacity-80">Uploaded zip</a>}
      </div>
      {proposal.status === "submitted" && !proposal.repo_url && !proposal.zip_url && (
        <div className="flex items-center gap-2">
          <input
            ref={fileRef} type="file" accept=".zip"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadMutation.mutate(f) }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="flex items-center gap-1.5 text-xs text-primary hover:opacity-80"
          >
            <Upload size={12} /> {uploadMutation.isPending ? "Uploading..." : "Upload a zip instead"}
          </button>
        </div>
      )}
      {zipError && <p className="text-xs text-destructive">{zipError}</p>}
      {proposal.review_notes && (
        <p className="text-xs text-muted-foreground italic border-t border-border pt-2 mt-1">
          Reviewer note: {proposal.review_notes}
        </p>
      )}
    </Card>
  )
}

/** 7B-6 (Missions Phase 2B, 2026-08-12) — D7's front door: an intern
 * proposes a mission (repo link or zip + description), staff reviews it
 * from the LMS authoring side. Submitting here never creates a real
 * mission by itself — that's staff integrating it by hand afterward. */
export default function ProposeMission() {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [error, setError] = useState("")

  const { data: proposals = [], isLoading } = useQuery({ queryKey: ["missions-proposals-mine"], queryFn: myProposalsApi })

  const createMutation = useMutation({
    mutationFn: () => createProposalApi({ title, description, repo_url: repoUrl || null }),
    onSuccess: () => {
      setError(""); setTitle(""); setDescription(""); setRepoUrl("")
      queryClient.invalidateQueries({ queryKey: ["missions-proposals-mine"] })
    },
    onError: (e) => setError(errorDetail(e, "Couldn't submit this proposal")),
  })

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <PageHeader
        title="Propose a Mission"
        subtitle="Bring your own mission idea — a repo link or a zip, plus what it does and why it's worth building."
      />

      <Card className="p-5 flex flex-col gap-3">
        <input
          value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title"
          className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
        />
        <textarea
          value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder="What does it do? What would students learn?"
          rows={4}
          className="px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
        />
        <input
          value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="Repo URL (optional — you can upload a zip after submitting instead)"
          className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
        />
        <Button
          onClick={() => title.trim() && description.trim() && createMutation.mutate()}
          disabled={!title.trim() || !description.trim() || createMutation.isPending}
          className="self-start"
        >
          {createMutation.isPending ? "Submitting..." : "Submit proposal"}
        </Button>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </Card>

      {isLoading ? (
        <Spinner />
      ) : proposals.length === 0 ? (
        <EmptyState title="No proposals yet" hint="Submit one above to get started." />
      ) : (
        <div className="flex flex-col gap-3">
          {proposals.map((p) => <ProposalRow key={p.id} proposal={p} />)}
        </div>
      )}
    </div>
  )
}
