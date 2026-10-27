import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  UserPlus,
  Crown,
  KeyRound,
  Trash2,
  Copy,
  Check,
} from "lucide-react"
import { useToast } from "@/components/ui/toast"
import {
  getOrganizationTeamApi,
  addOrganizationTeamMemberApi,
  removeOrganizationTeamMemberApi,
  getOrganizationMemberResetLinkApi,
  type OrgTeamMember,
} from "@/api/websiteEvents"

export default function OrganizationTeam() {
  const toast = useToast()
  const qc = useQueryClient()
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [resetModalData, setResetModalData] = useState<{
    name: string
    email: string
    url: string
  } | null>(null)

  const { data: team = [], isLoading } = useQuery({
    queryKey: ["org-team-members"],
    queryFn: getOrganizationTeamApi,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["org-team-members"] })
  }

  const removeMut = useMutation({
    mutationFn: (userId: string) => removeOrganizationTeamMemberApi(userId),
    onSuccess: () => {
      toast.success("Team member removed")
      invalidate()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to remove member")
    },
  })

  const getResetLinkMut = useMutation({
    mutationFn: (member: OrgTeamMember) =>
      getOrganizationMemberResetLinkApi(member.id).then((res) => ({
        name: member.full_name,
        email: member.email,
        url: res.reset_url,
      })),
    onSuccess: (data) => {
      setResetModalData(data)
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to generate password reset link")
    },
  })

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto pb-12">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">Organization Team</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Manage coordinators and administrators who have access to manage your programs and
            cohorts.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setAddModalOpen(true)}
          className="inline-flex items-center justify-center gap-2 h-10 px-4 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 transition w-fit"
        >
          <UserPlus className="w-4 h-4" /> Add Team Member
        </button>
      </div>

      {/* ── Members List ────────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="p-12 text-center text-sm text-muted-foreground">Loading team…</div>
      ) : (
        <div className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
          <div className="divide-y divide-border">
            {team.map((member) => (
              <div
                key={member.id}
                className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-muted/10 transition"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm shrink-0">
                    {member.full_name.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-foreground">
                        {member.full_name}
                      </span>
                      {member.is_owner ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
                          <Crown className="w-2.5 h-2.5" /> Primary Owner
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                          Coordinator
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground block">{member.email}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  <button
                    type="button"
                    disabled={getResetLinkMut.isPending}
                    onClick={() => getResetLinkMut.mutate(member)}
                    className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition"
                    title="Generate direct password reset link"
                  >
                    <KeyRound className="w-3.5 h-3.5" /> Reset Link
                  </button>

                  {!member.is_owner && (
                    <button
                      type="button"
                      disabled={removeMut.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Remove "${member.full_name}" from your organization team?`
                          )
                        ) {
                          removeMut.mutate(member.id)
                        }
                      }}
                      className="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition"
                      title="Remove Member"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Add Member Modal ────────────────────────────────────────────────── */}
      {addModalOpen && (
        <AddTeamMemberModal
          onClose={() => setAddModalOpen(false)}
          onSuccess={() => {
            setAddModalOpen(false)
            invalidate()
          }}
        />
      )}

      {/* ── Reset Link Modal ────────────────────────────────────────────────── */}
      {resetModalData && (
        <ResetLinkDisplayModal
          data={resetModalData}
          onClose={() => setResetModalData(null)}
        />
      )}
    </div>
  )
}

function AddTeamMemberModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")

  const mut = useMutation({
    mutationFn: () =>
      addOrganizationTeamMemberApi({
        full_name: fullName.trim(),
        email: email.trim(),
        password: password.trim() || undefined,
      }),
    onSuccess: (res) => {
      toast.success(`Added ${res.full_name} to the team!`)
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to add team member")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Add Team Member</h2>

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Full Name *</span>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Sarah Jenkins"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Email Address *</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="sarah@example.com"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">
              Initial Password (Optional)
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Leave blank to let them set it via reset link"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!fullName.trim() || !email.trim() || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Adding..." : "Add Member"}
          </button>
        </div>
      </div>
    </div>
  )
}

function ResetLinkDisplayModal({
  data,
  onClose,
}: {
  data: { name: string; email: string; url: string }
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)

  const copyToClipboard = () => {
    navigator.clipboard?.writeText(data.url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <div>
          <h2 className="text-base font-bold text-foreground">Password Setup Link</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Share this link with <strong>{data.name}</strong> ({data.email}) to set their password
            (valid for 72 hours):
          </p>
        </div>

        <div className="rounded-xl border border-border bg-background p-3 font-mono text-xs text-foreground break-all select-all">
          {data.url}
        </div>

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Close
          </button>
          <button
            type="button"
            onClick={copyToClipboard}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" /> Copied!
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" /> Copy Link
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
