import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Trash2, UserPlus, FileText } from "lucide-react"
import type { Role, User } from "@/types/shared"
import { ROLE_LABEL } from "@/types/shared"
import type { Team } from "@/types/interns"
import { getUsersApi, createUserApi, updateUserApi, deleteUserApi } from "@/api/admin/users"
import { getTeamsApi, addTeamMemberApi } from "@/api/interns/teams"
import {
  generateConfirmationLetterApi, generateCompletionLetterApi, generateCertificateApi,
} from "@/api/interns/userDocuments"
import { generateRecommendationLetterApi } from "@/api/documents"
import { cn } from "@/lib/utils"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"

const ALL_ROLES: Role[] = ["admin", "intern", "leader", "applicant", "instructor", "facilitator", "ambassador", "teacher"]

const roleBadgeColor: Record<Role, string> = {
  admin: "bg-black dark:bg-white text-white dark:text-black border border-transparent dark:border-border",
  leader: "bg-[#643f83] text-white",
  intern: "bg-[#d6c7e1] text-[#643f83]",
  applicant: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  instructor: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  facilitator: "bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-400",
  ambassador: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400",
  teacher: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
}

/* ================================================================== */
/* Users page                                                          */
/* ================================================================== */
export default function Users() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [changePasswordUser, setChangePasswordUser] = useState<User | null>(null)
  const [documentsUser, setDocumentsUser] = useState<User | null>(null)

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ["users"],
    queryFn: getUsersApi,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteUserApi,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Users</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage users and roles across the whole platform</p>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{users.length} user{users.length !== 1 ? "s" : ""}</p>
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <UserPlus size={14} /> New user
          </button>
        </div>

        <div className="flex flex-col gap-2">
          {users.map((u) => (
            <div
              key={u.id}
              className="flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 rounded-full bg-foreground text-background text-xs font-semibold flex items-center justify-center flex-shrink-0">
                  {u.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{u.full_name}</p>
                  <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                <div className="hidden sm:flex flex-wrap gap-1 justify-end max-w-[220px]">
                  {u.roles.map((r) => (
                    <span key={r} className={`text-xs font-semibold px-2 py-0.5 rounded-full ${roleBadgeColor[r]}`}>
                      {ROLE_LABEL[r]}
                    </span>
                  ))}
                </div>
                <button
                  onClick={() => setChangePasswordUser(u)}
                  className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  Change password
                </button>
                <button
                  onClick={() => setDocumentsUser(u)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  title="Documents"
                >
                  <FileText size={14} />
                </button>
                <button
                  onClick={() => { if (confirm(`Delete ${u.full_name}?`)) deleteMutation.mutate(u.id) }}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          {users.length === 0 && (
            <div className="flex items-center justify-center h-32 border border-dashed border-border rounded-2xl">
              <p className="text-sm text-muted-foreground">No users yet</p>
            </div>
          )}
        </div>

        {createOpen && (
          <CreateUserModal
            onClose={() => setCreateOpen(false)}
            onSuccess={() => { queryClient.invalidateQueries({ queryKey: ["users"] }); setCreateOpen(false) }}
          />
        )}

        {changePasswordUser && (
          <ChangePasswordModal
            user={changePasswordUser}
            onClose={() => setChangePasswordUser(null)}
            onSuccess={() => setChangePasswordUser(null)}
          />
        )}

        {documentsUser && (
          <DocumentsModal user={documentsUser} onClose={() => setDocumentsUser(null)} />
        )}
      </div>
    </div>
  )
}

/* ================================================================== */
/* Create user modal                                                   */
/* ================================================================== */
function CreateUserModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [fullName, setFullName] = useState("")
  const [email,    setEmail]    = useState("")
  const [password, setPassword] = useState("")
  const [roles,    setRoles]    = useState<Role[]>(["intern"])
  const [teamId,   setTeamId]   = useState("")
  const [phone,    setPhone]    = useState("")
  const [error,    setError]    = useState("")

  const { data: teams = [] } = useQuery<Team[]>({ queryKey: ["teams"], queryFn: getTeamsApi })

  const toggleRole = (role: Role) =>
    setRoles((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]))

  const mutation = useMutation({
    mutationFn: async () => {
      const user = await createUserApi({ full_name: fullName, email, password, roles, phone: phone || undefined })
      if (teamId && roles.includes("intern")) {
        await addTeamMemberApi(teamId, user.id)
      }
      return user
    },
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create user"),
  })

  return (
    <Modal title="New user" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Full name">
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Jane Smith" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Email">
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@example.com" type="email"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Password">
          <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" type="password"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Roles">
          <div className="flex flex-wrap gap-1.5">
            {ALL_ROLES.map((r) => (
              <label
                key={r}
                className={cn(
                  "flex items-center px-2.5 py-1.5 rounded-lg border text-xs font-medium cursor-pointer transition-colors select-none",
                  roles.includes(r) ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-muted"
                )}
              >
                <input type="checkbox" checked={roles.includes(r)} onChange={() => toggleRole(r)} className="hidden" />
                {ROLE_LABEL[r]}
              </label>
            ))}
          </div>
        </Field>
        {roles.includes("intern") && (
          <Field label="Team (optional)">
            <select value={teamId} onChange={(e) => setTeamId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer">
              <option value="" className="bg-card text-foreground">— No team —</option>
              {teams.map((t) => (
                <option key={t.id} value={t.id} className="bg-card text-foreground">{t.name}</option>
              ))}
            </select>
          </Field>
        )}
        <Field label="WhatsApp number (optional)">
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+20 10 0000 0000"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!fullName.trim() || !email.trim() || !password.trim() || roles.length === 0}
          label="Create user"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Change password modal                                               */
/* ================================================================== */
function ChangePasswordModal({ user, onClose, onSuccess }: {
  user: User; onClose: () => void; onSuccess: () => void
}) {
  const [password,  setPassword]  = useState("")
  const [confirm,   setConfirm]   = useState("")
  const [error,     setError]     = useState("")

  const mutation = useMutation({
    mutationFn: () => updateUserApi(user.id, { password }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to update password"),
  })

  const mismatch = confirm.length > 0 && password !== confirm

  return (
    <Modal title={`Change password — ${user.full_name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="New password">
          <input
            value={password} onChange={(e) => { setPassword(e.target.value); setError("") }}
            type="password" placeholder="••••••••" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Confirm password">
          <input
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
            type="password" placeholder="••••••••"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
          {mismatch && <p className="text-xs text-red-500 mt-1">Passwords do not match</p>}
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!password.trim() || password !== confirm}
          label="Update password"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Documents modal                                                     */
/* ================================================================== */
function DocumentsModal({ user, onClose }: { user: User; onClose: () => void }) {
  const [recommendationText, setRecommendationText] = useState("")
  const [signatoryName, setSignatoryName] = useState("")
  const [signatoryTitle, setSignatoryTitle] = useState("")
  const [error, setError] = useState("")
  const [lastUrl, setLastUrl] = useState<string | null>(null)

  const isIntern = user.roles.includes("intern")

  const onOk = (url: string) => { setLastUrl(url); setError("") }
  const onErr = (label: string) => () => setError(`Failed to generate ${label}`)

  const recommend = useMutation({
    mutationFn: () => generateRecommendationLetterApi({
      user_id: user.id, recommendation_text: recommendationText,
      signatory_name: signatoryName || undefined, signatory_title: signatoryTitle || undefined,
    }),
    onSuccess: (letter) => { onOk(letter.file_url); setRecommendationText("") },
    onError: onErr("recommendation letter"),
  })
  const confirmationLetter = useMutation({
    mutationFn: () => generateConfirmationLetterApi(user.id),
    onSuccess: (r) => onOk(r.file_url),
    onError: onErr("confirmation letter"),
  })
  const completionLetter = useMutation({
    mutationFn: () => generateCompletionLetterApi(user.id),
    onSuccess: (r) => onOk(r.file_url),
    onError: onErr("completion letter"),
  })
  const certificate = useMutation({
    mutationFn: () => generateCertificateApi(user.id),
    onSuccess: (r) => onOk(r.file_url),
    onError: onErr("certificate"),
  })

  return (
    <Modal title={`Documents — ${user.full_name}`} onClose={onClose}>
      <div className="flex flex-col gap-4">
        {isIntern && (
          <div>
            <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2">
              Intern documents
            </p>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => confirmationLetter.mutate()} disabled={confirmationLetter.isPending}
                className="h-9 border border-border rounded-xl text-sm font-medium text-foreground bg-card hover:bg-muted transition-colors disabled:opacity-50"
              >
                {confirmationLetter.isPending ? "Generating…" : "Generate confirmation letter"}
              </button>
              <button
                onClick={() => completionLetter.mutate()} disabled={completionLetter.isPending}
                className="h-9 border border-border rounded-xl text-sm font-medium text-foreground bg-card hover:bg-muted transition-colors disabled:opacity-50"
              >
                {completionLetter.isPending ? "Generating…" : "Generate completion letter"}
              </button>
              <button
                onClick={() => certificate.mutate()} disabled={certificate.isPending}
                className="h-9 border border-border rounded-xl text-sm font-medium text-foreground bg-card hover:bg-muted transition-colors disabled:opacity-50"
              >
                {certificate.isPending ? "Generating…" : "Generate completion certificate"}
              </button>
            </div>
          </div>
        )}

        <div>
          <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2">
            Recommendation letter
          </p>
          <div className="flex flex-col gap-3">
            <Field label="Letter text">
              <textarea
                value={recommendationText}
                onChange={(e) => { setRecommendationText(e.target.value); setError("") }}
                rows={5} placeholder="Write what this letter should say…"
                className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
              />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Signatory name (optional)">
                <input
                  value={signatoryName} onChange={(e) => setSignatoryName(e.target.value)}
                  placeholder="Abdullah Al-Rashidi"
                  className="w-full h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
              <Field label="Signatory title (optional)">
                <input
                  value={signatoryTitle} onChange={(e) => setSignatoryTitle(e.target.value)}
                  placeholder="Co-Founders & CEO"
                  className="w-full h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
            </div>
            <button
              onClick={() => recommend.mutate()} disabled={!recommendationText.trim() || recommend.isPending}
              className="h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              {recommend.isPending ? "Generating…" : "Generate recommendation letter"}
            </button>
          </div>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}
        {lastUrl && (
          <a
            href={lastUrl} target="_blank" rel="noreferrer"
            className="text-sm text-primary hover:underline text-center"
          >
            Open generated document ↗
          </a>
        )}

        <button
          onClick={onClose}
          className="w-full h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
        >
          Done
        </button>
      </div>
    </Modal>
  )
}
