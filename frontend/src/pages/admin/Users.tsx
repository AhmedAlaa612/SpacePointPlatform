import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Trash2, UserPlus, FileText, Pencil } from "lucide-react"
import type { Role, User } from "@/types/shared"
import { ROLE_LABEL } from "@/types/shared"
import { UserProfileModal } from "@/components/UserProfileModal"
import type { Team } from "@/types/interns"
import { getUsersApi, createUserApi, updateUserApi, deleteUserApi } from "@/api/admin/users"
import { getTeamsApi, addTeamMemberApi } from "@/api/interns/teams"
import { listAdminTemplatesApi, adminGenerateDocumentApi } from "@/api/documents"
import { getSettingsApi } from "@/api/admin/settings"
import { cn } from "@/lib/utils"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"

const ALL_ROLES: Role[] = ["admin", "intern", "leader", "applicant", "instructor", "facilitator", "ambassador", "teacher"]

const roleBadgeColor: Record<Role, string> = {
  admin: "bg-foreground text-background",
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
  const [editUser, setEditUser] = useState<User | null>(null)
  const [profileUserId, setProfileUserId] = useState<string | null>(null)

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
              <button
                onClick={() => setProfileUserId(u.id)}
                className="flex items-center gap-3 min-w-0 text-left hover:opacity-80 transition-opacity"
              >
                <div className="w-9 h-9 rounded-full bg-foreground text-background text-xs font-semibold flex items-center justify-center flex-shrink-0 overflow-hidden">
                  {u.photo_url ? (
                    <img src={u.photo_url} alt={u.full_name} className="w-full h-full object-cover" />
                  ) : (
                    u.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{u.full_name}</p>
                  <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                </div>
              </button>
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
                  onClick={() => setEditUser(u)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                  title="Edit user"
                >
                  <Pencil size={14} />
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

        {editUser && (
          <EditUserModal
            user={editUser}
            onClose={() => setEditUser(null)}
            onSuccess={() => { queryClient.invalidateQueries({ queryKey: ["users"] }); setEditUser(null) }}
          />
        )}

        {profileUserId && (
          <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
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

type DocTemplate = { id: string; key: string; name: string; roles: string[]; body_text?: string }

const DOC_TYPE_LABEL: Record<string, string> = {
  certificate:           "Certificate",
  confirmation_letter:   "Confirmation Letter",
  completion_letter:     "Completion Letter",
  recommendation_letter: "Recommendation Letter",
}

function templateDocType(key: string): string {
  for (const suffix of ["recommendation_letter", "completion_letter", "confirmation_letter", "certificate"]) {
    if (key.endsWith(suffix)) return suffix
  }
  return key
}

function prefillText(tpl: DocTemplate, user: User): string {
  const text = tpl.body_text ?? ""
  const startDate = user.created_at
    ? new Date(user.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
    : "[start date]"
  const today = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
  const role = tpl.roles[0] ?? "member"
  return text
    .replace(/{name}/g, user.full_name)
    .replace(/{start_date}/g, startDate)
    .replace(/{end_date}/g, today)
    .replace(/{role}/g, role.charAt(0).toUpperCase() + role.slice(1))
    .replace(/{program}/g, `${role.charAt(0).toUpperCase() + role.slice(1)} Program`)
}

function DocumentsModal({ user, onClose }: { user: User; onClose: () => void }) {
  const [selected, setSelected] = useState<DocTemplate | null>(null)
  const [bodyText, setBodyText] = useState("")
  const [signatoryName, setSignatoryName] = useState("")
  const [signatoryTitle, setSignatoryTitle] = useState("")
  const [documentDate, setDocumentDate] = useState("")
  const [documentTitle, setDocumentTitle] = useState("")
  const [fileUrl, setFileUrl] = useState<string | null>(null)
  const [error, setError] = useState("")

  const { data: allTemplates = [], isLoading } = useQuery({
    queryKey: ["admin-templates"],
    queryFn: listAdminTemplatesApi,
  })

  const { data: systemSettings } = useQuery<any>({
    queryKey: ["admin-settings"],
    queryFn: getSettingsApi,
  })

  // Filter to only templates relevant to this user's roles
  const templates: DocTemplate[] = allTemplates.filter((t) =>
    t.roles.some((r) => user.roles.includes(r as any))
  )

  function pickTemplate(t: DocTemplate) {
    setSelected(t)
    setBodyText(prefillText(t, user))
    setSignatoryName(systemSettings?.admin_signatory_name || "ABDULLAH ALSALMANI")
    setSignatoryTitle(systemSettings?.admin_signatory_title || "Co-Founder & CEO of SpacePoint")
    setDocumentTitle(t.name)
    
    const today = new Date().toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" })
    setDocumentDate(today)
    
    setFileUrl(null)
    setError("")
  }

  const generate = useMutation({
    mutationFn: () => adminGenerateDocumentApi({
      user_id: user.id,
      template_key: selected!.key,
      body_text: bodyText,
      signatory_name: signatoryName || undefined,
      signatory_title: signatoryTitle || undefined,
      date: documentDate || undefined,
      title: documentTitle || undefined,
    }),
    onSuccess: (r) => { setFileUrl(r.file_url); setError("") },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Generation failed"),
  })

  return (
    <Modal title={`Generate document — ${user.full_name}`} onClose={onClose}>
      <div className="flex flex-col gap-4">

        {/* ── Step 1: template picker ── */}
        {!selected ? (
          <>
            <p className="text-xs text-muted-foreground">
              Select a document template for this user.
            </p>
            {isLoading ? (
              <Spinner />
            ) : templates.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No templates available for this user's roles.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {templates.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => pickTemplate(t)}
                    className="flex items-start gap-3 p-3 text-left border border-border rounded-xl hover:border-primary/50 hover:bg-primary/5 transition-colors"
                  >
                    <FileText size={15} className="text-primary mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">{t.name}</p>
                      <p className="text-xs text-muted-foreground capitalize mt-0.5">
                        {DOC_TYPE_LABEL[templateDocType(t.key)] ?? t.key}
                        {" · "}
                        {t.roles.map((r) => r.charAt(0).toUpperCase() + r.slice(1)).join(", ")}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </>
        ) : (
          /* ── Step 2: edit text + generate ── */
          <>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { setSelected(null); setFileUrl(null); setError("") }}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                ← Back
              </button>
              <span className="text-xs text-muted-foreground">·</span>
              <p className="text-xs font-medium text-foreground">{selected.name}</p>
            </div>

            <Field label="Document text">
              <textarea
                value={bodyText}
                onChange={(e) => { setBodyText(e.target.value); setError("") }}
                rows={7}
                className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
              />
            </Field>

            <div className="flex flex-col gap-3 mt-1">
              <Field label="Document Title">
                <input
                  value={documentTitle}
                  onChange={(e) => setDocumentTitle(e.target.value)}
                  placeholder="e.g. Recommendation Letter"
                  className="w-full h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
              <Field label="Date">
                <input
                  value={documentDate}
                  onChange={(e) => setDocumentDate(e.target.value)}
                  placeholder="e.g. 27 June 2026"
                  className="w-full h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
              <Field label="Signatory Name">
                <input
                  value={signatoryName}
                  onChange={(e) => setSignatoryName(e.target.value)}
                  placeholder="e.g. Abdullah Alsalmani"
                  className="w-full h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
              <Field label="Signatory Title">
                <input
                  value={signatoryTitle}
                  onChange={(e) => setSignatoryTitle(e.target.value)}
                  placeholder="e.g. Co-Founder & CEO"
                  className="w-full h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
            </div>

            <div className="flex flex-col gap-1.5 mt-1">
              <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                Signatory Signature
              </label>
              <div className="relative overflow-hidden rounded-xl border border-border bg-muted/20 p-2 flex items-center justify-center min-h-[40px] max-w-[200px]">
                {systemSettings?.admin_signature_url ? (
                  <img
                    src={systemSettings.admin_signature_url}
                    alt="Admin signature"
                    className="max-h-8 object-contain dark:invert"
                  />
                ) : (
                  <span className="text-[10px] text-amber-500 italic">No admin signature uploaded in settings</span>
                )}
              </div>
            </div>

            {error && <p className="text-xs text-red-500">{error}</p>}

            {fileUrl ? (
              <div className="flex flex-col gap-2">
                <a
                  href={fileUrl} target="_blank" rel="noreferrer"
                  className="flex items-center justify-center gap-1.5 h-10 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:opacity-90 transition-colors"
                >
                  <FileText size={14} /> Open document ↗
                </a>
                <button
                  onClick={() => { setFileUrl(null) }}
                  className="h-9 border border-border rounded-xl text-sm text-muted-foreground hover:bg-muted transition-colors"
                >
                  Generate another
                </button>
              </div>
            ) : (
              <button
                onClick={() => generate.mutate()}
                disabled={!bodyText.trim() || generate.isPending}
                className="h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
              >
                {generate.isPending ? "Generating…" : "Generate document"}
              </button>
            )}
          </>
        )}

        <button
          onClick={onClose}
          className="w-full h-9 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
        >
          Done
        </button>
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Edit user modal                                                     */
/* ================================================================== */
function EditUserModal({ user, onClose, onSuccess }: { user: User; onClose: () => void; onSuccess: () => void }) {
  const [fullName, setFullName] = useState(user.full_name)
  const [email,    setEmail]    = useState(user.email)
  const [roles,    setRoles]    = useState<Role[]>(user.roles)
  const [phone,    setPhone]    = useState(user.phone || "")
  const [error,    setError]    = useState("")

  const toggleRole = (role: Role) =>
    setRoles((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]))

  const mutation = useMutation({
    mutationFn: () => updateUserApi(user.id, { full_name: fullName, email, roles, phone: phone || undefined }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to update user"),
  })

  return (
    <Modal title={`Edit user — ${user.full_name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Full name">
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Jane Smith" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Email">
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@example.com" type="email"
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
        <Field label="WhatsApp number (optional)">
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+20 10 0000 0000"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!fullName.trim() || !email.trim() || roles.length === 0}
          label="Save changes"
        />
      </div>
    </Modal>
  )
}
