import { useMemo, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Trash2, UserPlus, FileText, Pencil, UserX, UserCheck } from "lucide-react"
import type { Role, User } from "@/types/shared"
import { ROLE_LABEL } from "@/types/shared"
import { UserProfileModal } from "@/components/UserProfileModal"
import { AVATAR_PRESETS } from "@/components/games/avatarPresets"
import type { Team } from "@/types/interns"
import { getUsersApi, createUserApi, updateUserApi, deleteUserApi, getUserPasswordResetLinkApi } from "@/api/admin/users"
import { getTeamsApi, addTeamMemberApi } from "@/api/interns/teams"
import { listAdminTemplatesApi, adminGenerateDocumentApi } from "@/api/documents"
import { getSettingsApi } from "@/api/admin/settings"
import { cn } from "@/lib/utils"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"
import { PasswordInput } from "@/components/ui/PasswordInput"
import { CountrySelect } from "@/components/ui/CountrySelect"
import { CityNameSelect } from "@/components/ui/CitySelect"

const ALL_ROLES: Role[] = ["admin", "intern", "leader", "applicant", "instructor", "facilitator", "ambassador", "teacher", "operations", "coo", "storekeeper", "student", "judge", "lms_author", "observer", "organization", "mentor"]

const roleBadgeColor: Record<Role, string> = {
  admin: "bg-foreground text-background",
  leader: "bg-[#643f83] text-white",
  intern: "bg-[#d6c7e1] text-[#643f83]",
  applicant: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  instructor: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  facilitator: "bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-400",
  ambassador: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400",
  teacher: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  operations: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-400",
  coo: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400",
  storekeeper: "bg-slate-200 text-slate-700 dark:bg-slate-500/20 dark:text-slate-300",
  student: "bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-400",
  judge: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-500/15 dark:text-fuchsia-400",
  lms_author: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-400",
  observer: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400",
  organization: "bg-[#643f83]/20 text-[#a880ff]",
  mentor: "bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400",
}

/* ================================================================== */
/* Users page                                                          */
/* ================================================================== */
export default function Users() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [changePasswordUser, setChangePasswordUser] = useState<User | null>(null)
  const [resetLinkData, setResetLinkData] = useState<{ user: User; url: string } | null>(null)
  const [documentsUser, setDocumentsUser] = useState<User | null>(null)
  const [editUser, setEditUser] = useState<User | null>(null)
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [roleFilter, setRoleFilter] = useState<Role | "all">("all")
  const [view, setView] = useState<"staff" | "students" | "organizations">("staff")
  const studentsOnly = view === "students"
  const organizationsOnly = view === "organizations"

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ["users"],
    queryFn: getUsersApi,
  })

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase()
    return users.filter((u) => {
      // An "organization user" is an ACCOUNT with the organization role —
      // NOT any student/staff merely linked to a school via organization_id
      // (every student with a school carries that field from their contact,
      // which used to leak SP-ST- students with Student badges into this tab).
      const isOrgUser = u.roles.includes("organization")
      if (q) {
        const matchesName = u.full_name.toLowerCase().includes(q)
        const matchesEmail = u.email.toLowerCase().includes(q)
        const matchesOrg = !!u.organization_name && u.organization_name.toLowerCase().includes(q)
        // Matches "SP-0005", "sp-0005-uae", or a bare "0005" against card_id.
        const matchesId = !!u.card_id && u.card_id.toLowerCase().includes(q)
        if (!matchesName && !matchesEmail && !matchesOrg && !matchesId) return false
      }
      if (studentsOnly) return u.roles.includes("student")
      if (organizationsOnly) return isOrgUser
      if (u.roles.includes("student")) return false
      // If admin explicitly filtered by "organization" role in the dropdown, show org users
      if (roleFilter === "organization") return isOrgUser
      if (u.roles.length === 1 && u.roles[0] === "organization") return false
      if (roleFilter !== "all" && !u.roles.includes(roleFilter)) return false
      return true
    })
  }, [users, search, roleFilter, studentsOnly, organizationsOnly])


  const deleteMutation = useMutation({
    mutationFn: deleteUserApi,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  })

  const resetLinkMutation = useMutation({
    mutationFn: async (u: User) => {
      const res = await getUserPasswordResetLinkApi(u.id)
      return { user: u, url: res.reset_url }
    },
    onSuccess: (data) => {
      if (navigator.clipboard) {
        navigator.clipboard.writeText(data.url).catch(() => {})
      }
      setResetLinkData(data)
    },
  })

  // Deactivating (not deleting) is the right lever for an account that's
  // done but shouldn't lose its history — a judge who already scored
  // teams, most concretely: status="inactive" blocks login/every request
  // immediately (already enforced backend-wide), without touching rows
  // that reference them (e.g. competition_scores, which CASCADE on a real
  // delete and would silently erase the evaluations they gave).
  const statusMutation = useMutation({
    mutationFn: ({ id, status: next }: { id: string; status: string }) => updateUserApi(id, { status: next }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Users</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage staff, students, and partner organizations across the platform</p>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {filteredUsers.length} {organizationsOnly ? "organization" : "user"}{filteredUsers.length !== 1 ? "s" : ""}
            {filteredUsers.length !== users.length ? ` of ${users.length}` : ""}
          </p>
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <UserPlus size={14} /> {organizationsOnly ? "New organization" : "New user"}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={organizationsOnly ? "Search by organization, contact, or email…" : "Search by name, email, or ID…"}
            className="h-9 px-3 w-full sm:w-64 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
          <select
            value={organizationsOnly ? "organization" : roleFilter}
            onChange={(e) => {
              const val = e.target.value as Role | "all"
              if (val === "organization") {
                setView("organizations")
                setRoleFilter("all")
              } else {
                if (organizationsOnly) setView("staff")
                setRoleFilter(val)
              }
            }}
            disabled={studentsOnly}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <option value="all">All roles</option>
            {ALL_ROLES.map((r) => (
              <option key={r} value={r}>{ROLE_LABEL[r]}</option>
            ))}
          </select>
        </div>

        <div className="flex justify-center">
          <div className="flex items-center h-9 p-1 border border-border bg-card rounded-xl text-sm">
            {(["staff", "students", "organizations"] as const).map((v) => (
              <button
                key={v}
                onClick={() => {
                  setView(v)
                  setRoleFilter("all")
                }}
                className={cn(
                  "h-7 px-3 rounded-lg capitalize transition-colors cursor-pointer",
                  view === v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {v}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          {filteredUsers.map((u) => (
            <div
              key={u.id}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 sm:p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors"
            >
              <button
                onClick={() => setProfileUserId(u.id)}
                className="flex items-center gap-3 min-w-0 text-left hover:opacity-80 transition-opacity"
              >
                <div className="w-10 h-10 rounded-full bg-foreground text-background text-xs font-semibold flex items-center justify-center flex-shrink-0 overflow-hidden">
                  {u.photo_url ? (
                    <img src={u.photo_url} alt={u.full_name} className="w-full h-full object-cover" />
                  ) : (
                    (organizationsOnly && u.organization_name ? u.organization_name : u.full_name).split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <p className="text-sm font-medium text-foreground truncate">
                      {organizationsOnly && u.organization_name ? `${u.organization_name} (${u.full_name})` : u.full_name}
                    </p>
                    {u.card_id && (
                      <span className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0">
                        {u.card_id}
                      </span>
                    )}
                    {organizationsOnly && u.organization_type && (
                      <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-primary/15 text-primary shrink-0">
                        {u.organization_type}
                        {u.organization_country ? ` · ${u.organization_country.toUpperCase()}` : ""}
                      </span>
                    )}
                    {u.status !== "active" && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">
                        Inactive
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate">
                    {u.email}
                    {!organizationsOnly && u.organization_name ? ` · ${u.organization_name}` : ""}
                    {u.organization_city ? ` · ${u.organization_city}` : ""}
                  </p>
                  <div className="flex sm:hidden flex-wrap gap-1 mt-1.5">
                    {u.roles.map((r) => (
                      <span key={r} className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${roleBadgeColor[r]}`}>
                        {ROLE_LABEL[r]}
                      </span>
                    ))}
                  </div>
                </div>
              </button>

              <div className="flex items-center justify-between sm:justify-end gap-2 shrink-0 pt-2.5 sm:pt-0 border-t sm:border-t-0 border-border/40">
                <div className="hidden sm:flex flex-wrap gap-1 justify-end max-w-[220px]">
                  {u.roles.map((r) => (
                    <span key={r} className={`text-xs font-semibold px-2 py-0.5 rounded-full ${roleBadgeColor[r]}`}>
                      {ROLE_LABEL[r]}
                    </span>
                  ))}
                </div>
                <div className="flex items-center gap-1 sm:gap-1.5 w-full sm:w-auto justify-between sm:justify-start">
                  <button
                    onClick={() => resetLinkMutation.mutate(u)}
                    disabled={resetLinkMutation.isPending}
                    className="px-2 py-1 text-xs font-medium text-primary hover:opacity-80 bg-primary/10 rounded-lg transition-colors"
                    title="Generate & copy password reset link"
                  >
                    Reset link
                  </button>
                  <button
                    onClick={() => setChangePasswordUser(u)}
                    className="px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground bg-muted/40 sm:bg-transparent rounded-lg sm:rounded-none transition-colors"
                  >
                    Change password
                  </button>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setEditUser(u)}
                      className="p-2 sm:p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                      title="Edit user"
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      onClick={() => setDocumentsUser(u)}
                      className="p-2 sm:p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      title="Documents"
                    >
                      <FileText size={15} />
                    </button>
                    <button
                      onClick={() => {
                        const next = u.status === "active" ? "inactive" : "active"
                        if (confirm(`${next === "inactive" ? "Deactivate" : "Reactivate"} ${u.full_name}?`)) {
                          statusMutation.mutate({ id: u.id, status: next })
                        }
                      }}
                      className="p-2 sm:p-1.5 rounded-lg text-muted-foreground hover:text-amber-500 hover:bg-amber-500/10 transition-colors"
                      title={u.status === "active" ? "Deactivate" : "Reactivate"}
                    >
                      {u.status === "active" ? <UserX size={15} /> : <UserCheck size={15} />}
                    </button>
                    <button
                      onClick={() => { if (confirm(`Delete ${u.organization_name || u.full_name}?`)) deleteMutation.mutate(u.id) }}
                      className="p-2 sm:p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors"
                      title="Delete user"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
          {filteredUsers.length === 0 && (
            <div className="flex items-center justify-center h-32 border border-dashed border-border rounded-2xl">
              <p className="text-sm text-muted-foreground">
                {users.length === 0 ? "No users yet" : "No users match your search/filter"}
              </p>
            </div>
          )}
        </div>

        {createOpen && (
          <CreateUserModal
            defaultRoles={organizationsOnly ? ["organization"] : ["intern"]}
            onClose={() => setCreateOpen(false)}
            onSuccess={(createdUser) => {
              queryClient.invalidateQueries({ queryKey: ["users"] })
              queryClient.invalidateQueries({ queryKey: ["admin-website-organizations"] })
              if (createdUser?.roles?.includes("organization") || createdUser?.organization_id) {
                setView("organizations")
              }
              setCreateOpen(false)
            }}
          />
        )}

        {changePasswordUser && (
          <ChangePasswordModal
            user={changePasswordUser}
            onClose={() => setChangePasswordUser(null)}
            onSuccess={() => setChangePasswordUser(null)}
          />
        )}

        {resetLinkData && (
          <ResetLinkModal
            user={resetLinkData.user}
            url={resetLinkData.url}
            onClose={() => setResetLinkData(null)}
          />
        )}

        {documentsUser && (
          <DocumentsModal user={documentsUser} onClose={() => setDocumentsUser(null)} />
        )}

        {editUser && (
          <EditUserModal
            user={editUser}
            onClose={() => setEditUser(null)}
            onSuccess={() => {
              queryClient.invalidateQueries({ queryKey: ["users"] })
              queryClient.invalidateQueries({ queryKey: ["admin-website-organizations"] })
              setEditUser(null)
            }}
          />
        )}

        {profileUserId && (
          <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
        )}
      </div>
    </div>
  )
}

function LmsAuthorPermissionsField({
  canPublish,
  setCanPublish,
  scopeAll,
  setScopeAll,
}: {
  canPublish: boolean
  setCanPublish: (val: boolean) => void
  scopeAll: boolean
  setScopeAll: (val: boolean) => void
}) {
  return (
    <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-3 flex flex-col gap-3">
      <span className="text-xs font-semibold text-violet-700 dark:text-violet-400">LMS Author Permissions</span>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">Publishing access</span>
        <div className="flex rounded-lg border border-border overflow-hidden shrink-0">
          <button
            type="button"
            onClick={() => setCanPublish(false)}
            className={`h-8 px-3 text-xs font-medium transition-colors ${
              !canPublish
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Draft only
          </button>
          <button
            type="button"
            onClick={() => setCanPublish(true)}
            className={`h-8 px-3 text-xs font-medium transition-colors ${
              canPublish
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Publish access
          </button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">Content access</span>
        <div className="flex rounded-lg border border-border overflow-hidden shrink-0">
          <button
            type="button"
            onClick={() => setScopeAll(false)}
            className={`h-8 px-3 text-xs font-medium transition-colors ${
              !scopeAll
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Authored content only
          </button>
          <button
            type="button"
            onClick={() => setScopeAll(true)}
            className={`h-8 px-3 text-xs font-medium transition-colors ${
              scopeAll
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Full access
          </button>
        </div>
      </div>
    </div>
  )
}

/* ================================================================== */
/* Create user modal                                                   */
/* ================================================================== */
function CreateUserModal({
  defaultRoles = ["intern"],
  onClose,
  onSuccess,
}: {
  defaultRoles?: Role[]
  onClose: () => void
  onSuccess: (createdUser?: User) => void
}) {
  const [fullName, setFullName] = useState("")
  const [email,    setEmail]    = useState("")
  const [password, setPassword] = useState("")
  const [roles,    setRoles]    = useState<Role[]>(defaultRoles)
  const [authorCanPublish, setAuthorCanPublish] = useState(false)
  const [authorScopeAll,   setAuthorScopeAll]   = useState(false)
  const [orgNameLatin, setOrgNameLatin] = useState("")
  const [orgNameArabic, setOrgNameArabic] = useState("")
  const [orgType, setOrgType] = useState("university")
  const [orgCountry, setOrgCountry] = useState("AE")
  const [orgCity, setOrgCity] = useState("")
  const [teamId,   setTeamId]   = useState("")
  const [phone,    setPhone]    = useState("")
  const [error,    setError]    = useState("")

  const { data: teams = [] } = useQuery<Team[]>({ queryKey: ["teams"], queryFn: getTeamsApi })

  const toggleRole = (role: Role) =>
    setRoles((prev) => {
      if (prev.includes(role)) return prev.filter((r) => r !== role)
      if (role === "organization" && prev.length === 1 && prev[0] === "intern") {
        return ["organization"]
      }
      return [...prev, role]
    })

  const isOrg = roles.includes("organization")

  const mutation = useMutation({
    mutationFn: async () => {
      const user = await createUserApi({
        full_name: fullName,
        email,
        password,
        roles,
        phone: phone || undefined,
        author_can_publish: roles.includes("lms_author") ? authorCanPublish : undefined,
        author_scope_all: roles.includes("lms_author") ? authorScopeAll : undefined,
        ...(isOrg
          ? {
              org_name_latin: orgNameLatin.trim() || fullName.trim(),
              org_name_arabic: orgNameArabic.trim() || undefined,
              org_type: orgType,
              org_country: orgCountry,
              org_city: orgCity.trim() || undefined,
            }
          : {}),
      })
      if (teamId && roles.includes("intern")) {
        await addTeamMemberApi(teamId, user.id)
      }
      return user
    },
    onSuccess: (createdUser) => onSuccess(createdUser),
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create user"),
  })

  return (
    <Modal title={isOrg ? "New organization account" : "New user"} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {isOrg && (
          <div className="rounded-xl border border-primary/25 bg-primary/5 p-3 flex flex-col gap-3">
            <span className="text-xs font-semibold text-primary">Organization Profile</span>
            <Field label="Organization Name *">
              <input
                value={orgNameLatin}
                onChange={(e) => setOrgNameLatin(e.target.value)}
                placeholder="Abu Dhabi University"
                autoFocus
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
            <Field label="Organization Arabic Name (optional)">
              <input
                value={orgNameArabic}
                onChange={(e) => setOrgNameArabic(e.target.value)}
                placeholder="جامعة أبوظبي"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <Field label="Type">
                <select
                  value={orgType}
                  onChange={(e) => setOrgType(e.target.value)}
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                >
                  <option value="university">University</option>
                  <option value="school">School</option>
                  <option value="company">Company</option>
                  <option value="government">Government</option>
                  <option value="ngo">NGO / Club</option>
                  <option value="other">Other</option>
                </select>
              </Field>
              <Field label="Country">
                <CountrySelect
                  value={orgCountry}
                  onChange={setOrgCountry}
                  valueType="code"
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
              <Field label="City">
                <CityNameSelect
                  country={orgCountry}
                  value={orgCity}
                  onChange={setOrgCity}
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
            </div>
          </div>
        )}
        <Field label={isOrg ? "Contact person full name *" : "Full name"}>
          <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Jane Smith" autoFocus={!isOrg}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Email">
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@example.com" type="email"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Password">
          <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••"
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
        {roles.includes("lms_author") && (
          <LmsAuthorPermissionsField
            canPublish={authorCanPublish}
            setCanPublish={setAuthorCanPublish}
            scopeAll={authorScopeAll}
            setScopeAll={setAuthorScopeAll}
          />
        )}
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
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+971 50 000 0000"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!fullName.trim() || !email.trim() || !password.trim() || roles.length === 0 || (isOrg && !orgNameLatin.trim())}
          label={isOrg ? "Create organization" : "Create user"}
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Reset link modal                                                    */
/* ================================================================== */
function ResetLinkModal({
  user,
  url,
  onClose,
}: {
  user: User
  url: string
  onClose: () => void
}) {
  const [copied, setCopied] = useState(true)

  const handleCopy = () => {
    navigator.clipboard?.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Modal title={`Password reset link — ${user.organization_name || user.full_name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <p className="text-xs text-muted-foreground">
          Share this direct link with <strong>{user.email}</strong> so they can set or reset their password (valid for 72 hours):
        </p>
        <div className="rounded-xl border border-border bg-background p-3 font-mono text-xs text-foreground break-all select-all">
          {url}
        </div>
        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 border border-border rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            Close
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs font-medium hover:opacity-90 transition-colors"
          >
            {copied ? "Copied to clipboard ✓" : "Copy link"}
          </button>
        </div>
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
          <PasswordInput
            value={password} onChange={(e) => { setPassword(e.target.value); setError("") }}
            placeholder="••••••••" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Confirm password">
          <PasswordInput
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
            placeholder="••••••••"
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
  const [authorCanPublish, setAuthorCanPublish] = useState(user.author_can_publish ?? false)
  const [authorScopeAll,   setAuthorScopeAll]   = useState(user.author_scope_all ?? false)
  const [orgNameLatin, setOrgNameLatin] = useState(user.organization_name || "")
  const [orgNameArabic, setOrgNameArabic] = useState(user.organization_name_arabic || "")
  const [orgType, setOrgType] = useState(user.organization_type || "university")
  const [orgCountry, setOrgCountry] = useState(user.organization_country || user.country || "AE")
  const [orgCity, setOrgCity] = useState(user.organization_city || user.city_other || "")
  const [phone,    setPhone]    = useState(user.phone || "")
  const [nickname, setNickname] = useState(user.nickname || "")
  const [avatar,   setAvatar]   = useState(user.avatar || "")
  const [error,    setError]    = useState("")
  const isStudent = user.roles.includes("student")
  const isOrg = roles.includes("organization")

  const toggleRole = (role: Role) =>
    setRoles((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]))

  const mutation = useMutation({
    mutationFn: () => updateUserApi(user.id, {
      full_name: fullName, email, roles, phone: phone || undefined,
      // Only sent for students — nickname and avatar are the live-games
      // identity, and there is nothing for a staff account to set them on.
      ...(isStudent ? { nickname: nickname || undefined, avatar: avatar || undefined } : {}),
      ...(roles.includes("lms_author") ? { author_can_publish: authorCanPublish, author_scope_all: authorScopeAll } : {}),
      ...(isOrg
        ? {
            org_name_latin: orgNameLatin.trim() || fullName.trim(),
            org_name_arabic: orgNameArabic.trim(),
            org_type: orgType,
            org_country: orgCountry,
            org_city: orgCity.trim(),
          }
        : {}),
    }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to update user"),
  })

  return (
    <Modal title={`Edit ${isOrg ? "organization" : "user"} — ${user.organization_name || user.full_name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {isOrg && (
          <div className="rounded-xl border border-primary/25 bg-primary/5 p-3 flex flex-col gap-3">
            <span className="text-xs font-semibold text-primary">Organization Profile</span>
            <Field label="Organization Name *">
              <input
                value={orgNameLatin}
                onChange={(e) => setOrgNameLatin(e.target.value)}
                placeholder="Abu Dhabi University"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
            <Field label="Organization Arabic Name (optional)">
              <input
                value={orgNameArabic}
                onChange={(e) => setOrgNameArabic(e.target.value)}
                placeholder="جامعة أبوظبي"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </Field>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <Field label="Type">
                <select
                  value={orgType}
                  onChange={(e) => setOrgType(e.target.value)}
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                >
                  <option value="university">University</option>
                  <option value="school">School</option>
                  <option value="company">Company</option>
                  <option value="government">Government</option>
                  <option value="ngo">NGO / Club</option>
                  <option value="other">Other</option>
                </select>
              </Field>
              <Field label="Country">
                <CountrySelect
                  value={orgCountry}
                  onChange={setOrgCountry}
                  valueType="code"
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
              <Field label="City">
                <CityNameSelect
                  country={orgCountry}
                  value={orgCity}
                  onChange={setOrgCity}
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </Field>
            </div>
          </div>
        )}
        <Field label={isOrg ? "Contact person full name" : "Full name"}>
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
        {roles.includes("lms_author") && (
          <LmsAuthorPermissionsField
            canPublish={authorCanPublish}
            setCanPublish={setAuthorCanPublish}
            scopeAll={authorScopeAll}
            setScopeAll={setAuthorScopeAll}
          />
        )}
        <Field label="WhatsApp number (optional)">
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+971 50 000 0000"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        {/* A generated callsign occasionally lands somewhere unusable in
            front of a class, and until now nobody could change it for a
            student — only the student themselves, from inside a lobby. */}
        {isStudent && (
          <>
            <Field label="Nickname">
              <input value={nickname} onChange={(e) => setNickname(e.target.value)} placeholder="SpaceOtter77"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
            </Field>
            <Field label="Avatar">
              <div className="flex flex-wrap gap-1.5">
                {AVATAR_PRESETS.map((preset) => {
                  const Icon = preset.icon
                  const active = avatar === preset.key
                  return (
                    <button
                      key={preset.key}
                      onClick={() => setAvatar(active ? "" : preset.key)}
                      title={preset.label}
                      className={cn(
                        "size-10 rounded-xl border flex items-center justify-center transition-colors",
                        active ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:bg-muted",
                      )}
                    >
                      <Icon size={16} />
                    </button>
                  )
                })}
              </div>
            </Field>
          </>
        )}
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!fullName.trim() || !email.trim() || roles.length === 0 || (isOrg && !orgNameLatin.trim())}
          label="Save changes"
        />
      </div>
    </Modal>
  )
}
