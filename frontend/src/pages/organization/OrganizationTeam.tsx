import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  UserPlus,
  KeyRound,
  Trash2,
  Copy,
  Check,
} from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { ORG_ROLE_LABEL, type OrgSandboxRole } from "@/types/shared"
import {
  getOrganizationTeamApi,
  addOrganizationTeamMemberApi,
  updateOrganizationTeamMemberApi,
  removeOrganizationTeamMemberApi,
  getOrganizationMemberResetLinkApi,
  memberOrgRoles,
  type OrgTeamMember,
} from "@/api/websiteEvents"
import { OrgRolePickerGrid, OrgRoleToggleRow } from "@/components/organization/OrgRolePills"

export default function OrganizationTeam() {
  const toast = useToast()
  const qc = useQueryClient()
  const { user, refreshMe } = useAuth()
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [resetModalData, setResetModalData] = useState<{
    name: string
    email: string
    url: string
    emailSent: boolean
  } | null>(null)

  const { data: team = [], isLoading } = useQuery({
    queryKey: ["org-team-members"],
    queryFn: () => getOrganizationTeamApi(),
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
      toast.error(getErrorMessage(err, "Failed to remove member"))
    },
  })

  const roleMut = useMutation({
    mutationFn: ({ userId, orgRoles }: { userId: string; orgRoles: OrgSandboxRole[] }) =>
      updateOrganizationTeamMemberApi(userId, orgRoles),
    onSuccess: (res) => {
      const rolesText = memberOrgRoles(res)
        .map((r) => ORG_ROLE_LABEL[r])
        .join(", ")
      toast.success(`${res.full_name} roles updated: ${rolesText}`)
      invalidate()
      if (user?.id === res.id) {
        void refreshMe()
      }
    },
    onError: (err: any) => {
      toast.error(getErrorMessage(err, "Failed to change member roles"))
    },
  })

  const getResetLinkMut = useMutation({
    mutationFn: (member: OrgTeamMember) =>
      getOrganizationMemberResetLinkApi(member.id).then((res) => ({
        name: member.full_name,
        email: member.email,
        url: res.reset_url,
        emailSent: res.email_sent,
      })),
    onSuccess: (data) => {
      setResetModalData(data)
      if (data.emailSent) {
        toast.success(`Password link emailed to ${data.email}`)
      } else {
        toast.error("Email could not be sent — copy the link below instead")
      }
    },
    onError: (err: any) => {
      toast.error(getErrorMessage(err, "Failed to generate password reset link"))
    },
  })

  return (
    <div className="flex flex-col gap-6 max-w-4xl mx-auto pb-12">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">Organization Team</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Assign one or more sandbox roles to each member (including extra delivery or judging
            roles for the Primary Owner). Switch workspaces anytime from the top-right switcher.
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
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-sm text-foreground">
                        {member.full_name}
                      </span>
                      {!member.is_owner && member.invite_pending && (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
                          Invite pending
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground block mt-0.5">{member.email}</span>
                    <div className="mt-2">
                      <OrgRoleToggleRow
                        isOwner={member.is_owner}
                        roles={memberOrgRoles(member)}
                        disabled={roleMut.isPending}
                        onChange={(orgRoles) =>
                          roleMut.mutate({ userId: member.id, orgRoles })
                        }
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  <button
                    type="button"
                    disabled={getResetLinkMut.isPending}
                    onClick={() => getResetLinkMut.mutate(member)}
                    className="inline-flex items-center gap-1 h-8 px-2.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition"
                    title="Email a password setup link"
                  >
                    <KeyRound className="w-3.5 h-3.5" /> Send Link
                  </button>

                  {!member.is_owner && (
                    <button
                      type="button"
                      disabled={removeMut.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Remove "${member.full_name}" from your organization team?\n\nTheir SpacePoint account is kept — they just lose access to this organization.`
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
  const [orgRoles, setOrgRoles] = useState<Exclude<OrgSandboxRole, "owner">[]>(["coordinator"])

  const mut = useMutation({
    mutationFn: () =>
      addOrganizationTeamMemberApi({
        full_name: fullName.trim(),
        email: email.trim(),
        password: password.trim() || undefined,
        org_role: orgRoles[0],
        org_roles: orgRoles,
      }),
    onSuccess: (res) => {
      if (res.existing_account) {
        toast.success(
          res.invite_email_sent
            ? `Added ${res.full_name} — they can sign in with their existing account (email sent)`
            : `Added ${res.full_name} — they can sign in with their existing account`
        )
      } else {
        toast.success(
          res.invite_email_sent
            ? `Added ${res.full_name} — invite email sent!`
            : `Added ${res.full_name}. Email not sent — use "Send Link" to share it.`
        )
      }
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(getErrorMessage(err, "Failed to add team member"))
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Add Team Member</h2>
        <p className="text-xs text-muted-foreground -mt-2">
          We'll email them a set-password invite. If they already have a SpacePoint account it's
          linked automatically and they keep their existing password.
        </p>

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

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground">Organization Roles</span>
            <OrgRolePickerGrid value={orgRoles} onChange={setOrgRoles} />
          </div>

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
  data: { name: string; email: string; url: string; emailSent: boolean }
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
            {data.emailSent ? (
              <>
                Emailed to <strong>{data.email}</strong>. You can also share this link with{" "}
                <strong>{data.name}</strong> to set their password (valid for 7 days):
              </>
            ) : (
              <>
                Email could not be sent. Share this link with <strong>{data.name}</strong> (
                {data.email}) to set their password (valid for 7 days):
              </>
            )}
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
