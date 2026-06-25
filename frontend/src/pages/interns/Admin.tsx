import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Trash2, UserPlus, Users, Plus, Crown, X } from "lucide-react"
import type { User, Team, Role } from "@/types/interns"
import { getUsersApi, createUserApi, updateUserApi, deleteUserApi } from "@/api/interns/users"
import { getTeamsApi, createTeamApi, addTeamMemberApi, removeTeamMemberApi } from "@/api/interns/teams"
import { userRole } from "@/types/interns"
import { cn } from "@/lib/utils"

const roleBadge: Record<string, string> = {
  admin:  "bg-black dark:bg-white text-white dark:text-black border border-transparent dark:border-border",
  leader: "bg-[#643f83] text-white",
  intern: "bg-[#d6c7e1] text-[#643f83]",
}

type Tab = "users" | "teams"

export default function Admin() {
  const [tab, setTab] = useState<Tab>("users")

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Admin</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage users and teams</p>
      </div>

      <div className="flex gap-1 border-b border-border">
        {(["users", "teams"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px",
              tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t === "users" ? "Users" : "Teams"}
          </button>
        ))}
      </div>

      {tab === "users" && <UsersPanel />}
      {tab === "teams" && <TeamsPanel />}
    </div>
  )
}

/* ================================================================== */
/* Users panel                                                         */
/* ================================================================== */
function UsersPanel() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [changePasswordUser, setChangePasswordUser] = useState<User | null>(null)

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
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${roleBadge[userRole(u)]}`}>
                {userRole(u)}
              </span>
              <button
                onClick={() => setChangePasswordUser(u)}
                className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Change password
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
    </div>
  )
}

/* ================================================================== */
/* Teams panel                                                         */
/* ================================================================== */
function TeamsPanel() {
  const queryClient = useQueryClient()
  const [createOpen,   setCreateOpen]   = useState(false)
  const [managingTeam, setManagingTeam] = useState<Team | null>(null)

  const { data: teams = [], isLoading: teamsLoading } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: getTeamsApi,
  })

  const { data: users = [] } = useQuery<User[]>({
    queryKey: ["users"],
    queryFn: getUsersApi,
  })

  if (teamsLoading) return <Spinner />

  const getUserName = (id: string) => users.find((u) => u.id === id)?.full_name ?? "Unknown"

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{teams.length} team{teams.length !== 1 ? "s" : ""}</p>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
        >
          <Plus size={14} /> New team
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {teams.map((team) => (
          <div
            key={team.id}
            className="bg-card border border-border rounded-2xl p-5 flex flex-col gap-3 hover:border-muted-foreground/30 transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-foreground">{team.name}</p>
                <div className="flex items-center gap-1 mt-0.5 text-xs text-muted-foreground">
                  <Crown size={11} />
                  <span>{getUserName(team.leader_id)}</span>
                </div>
              </div>
              <span className="text-xs text-muted-foreground flex-shrink-0 mt-0.5">
                {team.members.length} member{team.members.length !== 1 ? "s" : ""}
              </span>
            </div>

            {team.members.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {team.members.map((m) => (
                  <div
                    key={m.id} title={m.full_name}
                    className="w-7 h-7 rounded-full bg-[#d6c7e1] text-[#643f83] text-[10px] font-semibold flex items-center justify-center"
                  >
                    {m.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={() => setManagingTeam(team)}
              className="h-8 border border-border rounded-lg text-xs font-medium text-foreground bg-card hover:bg-muted transition-colors flex items-center justify-center gap-1.5"
            >
              <Users size={12} /> Manage members
            </button>
          </div>
        ))}
        {teams.length === 0 && (
          <div className="col-span-2 flex items-center justify-center h-32 border border-dashed border-border rounded-2xl">
            <p className="text-sm text-muted-foreground">No teams yet</p>
          </div>
        )}
      </div>

      {createOpen && (
        <CreateTeamModal
          users={users}
          onClose={() => setCreateOpen(false)}
          onSuccess={() => { queryClient.invalidateQueries({ queryKey: ["teams"] }); setCreateOpen(false) }}
        />
      )}

      {managingTeam && (
        <ManageMembersModal
          team={managingTeam} users={users}
          onClose={() => setManagingTeam(null)}
          onSuccess={() => queryClient.invalidateQueries({ queryKey: ["teams"] })}
        />
      )}
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
  const [role,     setRole]     = useState<Role>("intern")
  const [phone,    setPhone]    = useState("")
  const [error,    setError]    = useState("")

  const mutation = useMutation({
    mutationFn: () => createUserApi({ full_name: fullName, email, password, role, phone: phone || undefined }),
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
        <Field label="Role">
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer">
            <option value="intern" className="bg-card text-foreground">Intern</option>
            <option value="leader" className="bg-card text-foreground">Team leader</option>
            <option value="admin" className="bg-card text-foreground">Admin</option>
          </select>
        </Field>
        <Field label="WhatsApp number (optional)">
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+20 10 0000 0000"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!fullName.trim() || !email.trim() || !password.trim()}
          label="Create user"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Create team modal                                                   */
/* ================================================================== */
function CreateTeamModal({ users, onClose, onSuccess }: {
  users: User[]; onClose: () => void; onSuccess: () => void
}) {
  const leaders = users.filter((u) => u.roles.includes("leader") || u.roles.includes("admin"))
  const [name,     setName]     = useState("")
  const [leaderId, setLeaderId] = useState(leaders[0]?.id ?? "")
  const [error,    setError]    = useState("")

  const mutation = useMutation({
    mutationFn: () => createTeamApi({ name, leader_id: leaderId }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create team"),
  })

  return (
    <Modal title="New team" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Team name">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Team Alpha" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        </Field>
        <Field label="Team leader">
          {leaders.length === 0 ? (
            <p className="text-xs text-red-500">No leaders found. Create a user with the "leader" role first.</p>
          ) : (
            <select value={leaderId} onChange={(e) => setLeaderId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer">
              {leaders.map((u) => (
                <option key={u.id} value={u.id} className="bg-card text-foreground">{u.full_name} ({userRole(u)})</option>
              ))}
            </select>
          )}
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!name.trim() || !leaderId}
          label="Create team"
        />
      </div>
    </Modal>
  )
}

/* ================================================================== */
/* Manage members modal                                                */
/* ================================================================== */
function ManageMembersModal({ team, users, onClose, onSuccess }: {
  team: Team; users: User[]; onClose: () => void; onSuccess: () => void
}) {
  const queryClient = useQueryClient()
  const interns   = users.filter((u) => u.roles.includes("intern"))
  const memberIds = new Set(team.members.map((m) => m.id))

  const addMutation = useMutation({
    mutationFn: (userId: string) => addTeamMemberApi(team.id, userId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["teams"] }); onSuccess() },
  })
  const removeMutation = useMutation({
    mutationFn: (userId: string) => removeTeamMemberApi(team.id, userId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["teams"] }); onSuccess() },
  })

  return (
    <Modal title={`Members — ${team.name}`} onClose={onClose}>
      <div className="flex flex-col gap-2">
        {interns.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-4">
            No interns found. Create intern accounts first.
          </p>
        )}
        {interns.map((intern) => {
          const isMember  = memberIds.has(intern.id)
          const isPending = addMutation.isPending || removeMutation.isPending
          return (
            <div key={intern.id} className="flex items-center justify-between p-3 border border-border rounded-xl">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-[#d6c7e1] text-[#643f83] text-xs font-semibold flex items-center justify-center">
                  {intern.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{intern.full_name}</p>
                  <p className="text-xs text-muted-foreground">{intern.email}</p>
                </div>
              </div>
              <button
                onClick={() => isMember ? removeMutation.mutate(intern.id) : addMutation.mutate(intern.id)}
                disabled={isPending}
                className={cn(
                  "h-7 px-3 rounded-lg text-xs font-medium transition-colors disabled:opacity-50",
                  isMember
                    ? "border border-border text-muted-foreground hover:bg-red-500/10 hover:text-red-500 hover:border-red-200"
                    : "bg-primary text-primary-foreground hover:opacity-90"
                )}
              >
                {isMember ? "Remove" : "Add"}
              </button>
            </div>
          )
        })}
      </div>
      <div className="mt-4">
        <button onClick={onClose}
          className="w-full h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
          Done
        </button>
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
/* Shared helpers                                                      */
/* ================================================================== */
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-6 flex flex-col gap-4 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <p className="text-base font-semibold text-foreground">{title}</p>
          <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">{label}</label>
      {children}
    </div>
  )
}

function ModalActions({ onCancel, onConfirm, loading, disabled, label }: {
  onCancel: () => void; onConfirm: () => void; loading: boolean; disabled: boolean; label: string
}) {
  return (
    <div className="flex gap-2 mt-1">
      <button onClick={onCancel}
        className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
        Cancel
      </button>
      <button onClick={onConfirm} disabled={disabled || loading}
        className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50">
        {loading ? "…" : label}
      </button>
    </div>
  )
}

function Spinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  )
}
