import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { GitMerge, Link2, UserX } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"
import { getMergeReviewsApi, resolveMergeReviewApi } from "@/api/spine/merge_reviews"
import {
  CONTACT_ROLE_LABEL,
  RELATION_LABEL,
  type ContactBrief,
  type ContactRole,
  type ContactRelationType,
  type MergeReviewOut,
} from "@/types/spine"

const ALL_RELATIONS: ContactRelationType[] = ["guardian_of", "child_of", "sibling_of", "spouse_of", "other"]

const REASON_LABEL: Record<string, string> = {
  phone_match: "Matching phone number",
  import_ambiguous: "Ambiguous import",
}

const QUERY_KEY = ["spine-merge-reviews", "pending"]

/* ================================================================== */
/* Merge reviews page                                                  */
/* ================================================================== */
export default function MergeReviews() {
  const { activeRole } = useAuth()
  // Resolving is admin-only server-side (routers/spine/merge_reviews.py —
  // operations can browse/search but not resolve); hide the action buttons
  // for operations here too, rather than showing controls that 403.
  const canResolve = activeRole === "admin"

  const { data: reviews = [], isLoading } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => getMergeReviewsApi("pending"),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Merge Reviews</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Two contacts that might be the same person — read both records below and decide.
          {!canResolve && " Only an admin can resolve a review."}
        </p>
      </div>

      <div className="flex flex-col gap-3">
        {reviews.map((review) => (
          <ReviewRow key={review.id} review={review} canResolve={canResolve} />
        ))}
        {reviews.length === 0 && (
          <div className="flex items-center justify-center h-32 border border-dashed border-border rounded-2xl">
            <p className="text-sm text-muted-foreground">No pending merge reviews</p>
          </div>
        )}
      </div>
    </div>
  )
}

/* ================================================================== */
/* One review — both candidates side by side, three resolution actions */
/* ================================================================== */
function ReviewRow({ review, canResolve }: { review: MergeReviewOut; canResolve: boolean }) {
  const queryClient = useQueryClient()
  const [mergeOpen, setMergeOpen] = useState(false)
  const [linkOpen, setLinkOpen] = useState(false)
  const [error, setError] = useState("")

  const resolve = useMutation({
    mutationFn: (body: { action: "merge" | "keep_separate" | "link_household"; winner_id?: string; relation?: string }) =>
      resolveMergeReviewApi(review.id, body),
    onSuccess: () => {
      setError("")
      queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to resolve this review"),
  })

  const keepSeparate = () => {
    if (confirm("Mark these as two different people? This can't be undone.")) {
      resolve.mutate({ action: "keep_separate" })
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <CandidateCard contact={review.candidate_a} />
        <CandidateCard contact={review.candidate_b} />
      </div>

      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="text-xs text-muted-foreground">
          Reason: {REASON_LABEL[review.reason] ?? review.reason}
        </span>
        {canResolve && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMergeOpen(true)}
              disabled={resolve.isPending}
              className="flex items-center gap-1.5 h-9 px-3 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              <GitMerge size={14} /> Merge
            </button>
            <button
              onClick={keepSeparate}
              disabled={resolve.isPending}
              className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              <UserX size={14} /> Keep Separate
            </button>
            <button
              onClick={() => setLinkOpen(true)}
              disabled={resolve.isPending}
              className="flex items-center gap-1.5 h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              <Link2 size={14} /> Link as Household
            </button>
          </div>
        )}
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {mergeOpen && (
        <MergeModal
          review={review}
          onClose={() => setMergeOpen(false)}
          onConfirm={(winnerId) => {
            resolve.mutate({ action: "merge", winner_id: winnerId })
            setMergeOpen(false)
          }}
        />
      )}
      {linkOpen && (
        <LinkHouseholdModal
          review={review}
          onClose={() => setLinkOpen(false)}
          onConfirm={(relation) => {
            resolve.mutate({ action: "link_household", relation })
            setLinkOpen(false)
          }}
        />
      )}
    </div>
  )
}

/* Plain fields only — name, phone, email, roles. No similarity score or
   algorithmic hint of any kind: a human reads both records and decides
   (see backend/app/services/spine/identity.py). */
function CandidateCard({ contact }: { contact: ContactBrief | null }) {
  if (!contact) {
    return (
      <div className="p-3 border border-dashed border-border rounded-xl text-sm text-muted-foreground">
        Contact not found
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1.5 p-3 border border-border rounded-xl">
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{contact.full_name}</p>
      </div>
      <div className="flex flex-wrap gap-1">
        {contact.contact_roles.map((r) => (
          <span key={r} className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
            {CONTACT_ROLE_LABEL[r as ContactRole] ?? r}
          </span>
        ))}
      </div>
      <p className="text-xs text-muted-foreground truncate">{contact.primary_phone_e164 || "No phone on file"}</p>
      <p className="text-xs text-muted-foreground truncate">{contact.email || "No email on file"}</p>
    </div>
  )
}

/* ================================================================== */
/* Merge — pick which of the two candidates is the winner               */
/* ================================================================== */
function MergeModal({
  review, onClose, onConfirm,
}: { review: MergeReviewOut; onClose: () => void; onConfirm: (winnerId: string) => void }) {
  const [winnerId, setWinnerId] = useState<string | null>(null)
  const candidates = [review.candidate_a, review.candidate_b].filter((c): c is ContactBrief => c !== null)

  return (
    <Modal title="Choose which contact to keep" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          The other contact's data will be merged into whichever one you choose, and the other will be retired
          (not deleted — every record that pointed to it keeps working).
        </p>
        <div className="flex flex-col gap-2">
          {candidates.map((c) => (
            <label
              key={c.id}
              className={cn(
                "flex items-center gap-3 p-3 border rounded-xl cursor-pointer transition-colors",
                winnerId === c.id ? "border-primary bg-primary/10" : "border-border hover:bg-muted",
              )}
            >
              <input
                type="radio" name="winner" checked={winnerId === c.id}
                onChange={() => setWinnerId(c.id)} className="accent-primary"
              />
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{c.full_name}</p>
                <p className="text-xs text-muted-foreground truncate">{c.primary_phone_e164 || c.email || "—"}</p>
              </div>
            </label>
          ))}
        </div>
        <ModalActions
          onCancel={onClose} onConfirm={() => winnerId && onConfirm(winnerId)}
          loading={false} disabled={!winnerId} label="Merge"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Link as household — pick a relation type                            */
/* ================================================================== */
function LinkHouseholdModal({
  review, onClose, onConfirm,
}: { review: MergeReviewOut; onClose: () => void; onConfirm: (relation: string) => void }) {
  const [relation, setRelation] = useState<ContactRelationType>("guardian_of")
  const aName = review.candidate_a?.full_name ?? "Candidate A"
  const bName = review.candidate_b?.full_name ?? "Candidate B"

  return (
    <Modal title="Link as household" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Records that <span className="font-medium text-foreground">{aName}</span> is a{" "}
          <span className="font-medium text-foreground">{RELATION_LABEL[relation]?.toLowerCase()}</span>{" "}
          <span className="font-medium text-foreground">{bName}</span>. Keeps both contacts separate.
        </p>
        <Field label="Relation type">
          <select
            value={relation} onChange={(e) => setRelation(e.target.value as ContactRelationType)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            {ALL_RELATIONS.map((r) => (
              <option key={r} value={r}>{RELATION_LABEL[r]}</option>
            ))}
          </select>
        </Field>
        <ModalActions
          onCancel={onClose} onConfirm={() => onConfirm(relation)}
          loading={false} disabled={false} label="Link"
        />
      </div>
    </Modal>
  )
}
