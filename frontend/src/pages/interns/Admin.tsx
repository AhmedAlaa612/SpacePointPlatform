import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Users, Plus, Crown } from "lucide-react"
import type { User, Team } from "@/types/interns"
import { userRole } from "@/types/interns"
import { getUsersApi } from "@/api/admin/users"
import { getTeamsApi, createTeamApi, addTeamMemberApi, removeTeamMemberApi } from "@/api/interns/teams"
import { cn } from "@/lib/utils"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"

export default function Admin() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Admin</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage teams</p>
      </div>

      <TeamsPanel />
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
