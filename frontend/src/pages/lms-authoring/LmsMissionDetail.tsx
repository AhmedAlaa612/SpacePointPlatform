import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useParams } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { ArrowLeft } from "lucide-react"
import { PageHeader, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  getMissionAdminApi, updateMissionAdminApi, deleteMissionAdminApi,
  listMissionRosterApi, grantMissionAssignmentApi, bulkGrantMissionAssignmentApi, revokeMissionAssignmentApi,
  type MissionAdmin, type MissionTeamPolicy, type MissionAccessMode,
} from "@/api/missions_admin"
import { AssignPanel } from "@/pages/lms-authoring/components/AssignPanel"
import { MissionContentSection } from "@/pages/lms-authoring/components/MissionContentSection"
import { PrerequisitesSection } from "@/pages/lms-authoring/components/PrerequisitesSection"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** Mission detail/edit page (2026-08-12) — missions previously had only a
 * status dropdown on the list page, no edit or delete. Mirrors
 * `LmsCourseDetail.tsx`'s shape: edit modal, delete (guarded server-side by
 * attempt history), inline prerequisites, and staff assignment. */
export default function LmsMissionDetail() {
  const { missionId } = useParams({ strict: false }) as { missionId: string }
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteError, setDeleteError] = useState("")

  const { data: mission, isLoading: missionLoading } = useQuery({
    queryKey: ["missions-admin-detail", missionId],
    queryFn: () => getMissionAdminApi(missionId),
  })
  const invalidateMission = () => queryClient.invalidateQueries({ queryKey: ["missions-admin-detail", missionId] })

  const { data: roster = [], isLoading: rosterLoading } = useQuery({
    queryKey: ["missions-admin-roster", missionId],
    queryFn: () => listMissionRosterApi(missionId),
  })
  const [bulkResult, setBulkResult] = useState<{ granted: number; already_assigned: number } | null>(null)
  const invalidateRoster = () => queryClient.invalidateQueries({ queryKey: ["missions-admin-roster", missionId] })
  const grantMutation = useMutation({
    mutationFn: (userId: string) => grantMissionAssignmentApi(missionId, userId),
    onSuccess: invalidateRoster,
  })
  const bulkGrantMutation = useMutation({
    mutationFn: (role: string) => bulkGrantMissionAssignmentApi(missionId, role),
    onSuccess: (result) => { setBulkResult(result); invalidateRoster() },
  })
  const revokeMutation = useMutation({
    mutationFn: (assignmentId: string) => revokeMissionAssignmentApi(assignmentId),
    onSuccess: invalidateRoster,
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteMissionAdminApi(missionId),
    onSuccess: () => void navigate({ to: "/lms-authoring/missions" }),
    onError: (e) => setDeleteError(errorDetail(e, "Couldn't delete this mission")),
  })

  if (missionLoading || !mission) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <button
        onClick={() => void navigate({ to: "/lms-authoring/missions" })}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors w-fit"
      >
        <ArrowLeft size={14} /> Missions
      </button>

      <PageHeader
        title={mission.title}
        subtitle={mission.summary ?? undefined}
        action={
          <div className="flex gap-2">
            <button
              onClick={() => setEditOpen(true)}
              className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              Edit
            </button>
            <button
              onClick={() => setDeleteOpen(true)}
              className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-red-600 hover:bg-red-500/10 transition-colors"
            >
              Delete
            </button>
          </div>
        }
      />
      <div className="flex items-center gap-2 flex-wrap -mt-3">
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">{mission.status}</span>
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary capitalize">{mission.kind}</span>
        {mission.track && <span className="text-xs text-muted-foreground">{mission.track}</span>}
        {mission.authored_by_name && <span className="text-xs text-muted-foreground">Author: {mission.authored_by_name}</span>}
      </div>
      {mission.description && <p className="text-sm text-muted-foreground max-w-2xl">{mission.description}</p>}

      <PrerequisitesSection itemType="mission" itemId={missionId} />

      {/* Design v2 (7D-8) — renders nothing for kinds with no authored
          content model, so this is safe on every mission. */}
      <MissionContentSection missionId={missionId} />

      <AssignPanel
        roster={roster
          .filter((a) => a.status === "active")
          .map((a) => ({
            id: a.id, userId: a.user_id, name: a.user_name, email: a.user_email, status: a.status,
          }))}
        isLoading={rosterLoading}
        onGrant={(userId) => grantMutation.mutate(userId)}
        onBulkGrant={(role) => bulkGrantMutation.mutate(role)}
        onRevoke={(assignmentId) => revokeMutation.mutate(assignmentId)}
        grantPending={grantMutation.isPending}
        bulkPending={bulkGrantMutation.isPending}
        revokePending={revokeMutation.isPending}
        bulkResult={bulkResult}
      />

      {editOpen && (
        <EditMissionModal
          missionId={missionId}
          mission={mission}
          onClose={() => setEditOpen(false)}
          onSuccess={() => { invalidateMission(); setEditOpen(false) }}
        />
      )}
      {deleteOpen && (
        <ConfirmDialog
          title={`Delete mission "${mission.title}"?`}
          description={deleteError || "Refused if any attempt has been made against this mission — archive it instead."}
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteOpen(false)}
          onConfirm={() => deleteMutation.mutate()}
        />
      )}
    </div>
  )
}

function EditMissionModal({ mission, onClose, onSuccess }: {
  missionId: string; mission: MissionAdmin; onClose: () => void; onSuccess: () => void
}) {
  const [title, setTitle] = useState(mission.title)
  const [summary, setSummary] = useState(mission.summary ?? "")
  const [description, setDescription] = useState(mission.description ?? "")
  const [track, setTrack] = useState(mission.track ?? "")
  const [accessMode, setAccessMode] = useState<MissionAccessMode>(mission.access_mode)
  const [teamPolicy, setTeamPolicy] = useState<MissionTeamPolicy>(mission.team_policy)
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => updateMissionAdminApi(mission.id, {
      title: title.trim(), summary: summary.trim(), description: description.trim(),
      track: track.trim() || undefined, access_mode: accessMode, team_policy: teamPolicy,
    }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to save mission"),
  })

  return (
    <Modal title="Edit mission" onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-3">
        <Field label="Title">
          <input
            value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Summary">
          <input
            value={summary} onChange={(e) => setSummary(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Description">
          <textarea
            value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Track (optional)">
            <input
              value={track} onChange={(e) => setTrack(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Team policy">
            <select
              value={teamPolicy} onChange={(e) => setTeamPolicy(e.target.value as MissionTeamPolicy)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="solo">Solo</option>
              <option value="team">Team</option>
              <option value="either">Either</option>
            </select>
          </Field>
        </div>
        <Field label="Access mode">
          <select
            value={accessMode} onChange={(e) => setAccessMode(e.target.value as MissionAccessMode)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="open">Open</option>
            <option value="invite">Invite only</option>
          </select>
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!title.trim()} label="Save changes" />
      </div>
    </Modal>
  )
}
