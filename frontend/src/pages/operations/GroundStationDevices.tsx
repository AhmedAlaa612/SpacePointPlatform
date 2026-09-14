import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { Antenna, Copy, Plus, Radio } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import {
  listDevices, registerDevice, listGroundStationAttempts,
  type GroundStationDevice, type GroundStationAttemptSummary,
} from "@/api/groundStation"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

function StatusPill({ status }: { status: "online" | "offline" }) {
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
      status === "online" ? "bg-green-500/15 text-green-600 dark:text-green-400" : "bg-muted text-muted-foreground"
    }`}>
      {status === "online" ? "Online" : "Offline"}
    </span>
  )
}

/** Ground Station ops view (2026-09-14 rework): a rig now belongs to a
 * mission attempt (solo or team) — this page is where staff watch every
 * team's run and, separately, register an orphan/shared rig (a demo booth
 * kit with no student owner). No secrets to hand out anymore: ingest has
 * no auth (operator directive), so a device id is the whole address. */
export default function GroundStationDevices() {
  const queryClient = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)
  const [label, setLabel] = useState("")
  const [actionError, setActionError] = useState("")

  const { data: attempts = [], isLoading: attemptsLoading } = useQuery({
    queryKey: ["ground-station-attempts"],
    queryFn: listGroundStationAttempts,
  })
  const { data: devices = [], isLoading: devicesLoading } = useQuery({
    queryKey: ["ground-station-devices"],
    queryFn: listDevices,
  })
  const orphanDevices = devices.filter((d: GroundStationDevice) => !d.mission_attempt_id)

  const createMutation = useMutation({
    mutationFn: () => registerDevice(label.trim()),
    onSuccess: () => {
      setActionError(""); setAddOpen(false); setLabel("")
      void queryClient.invalidateQueries({ queryKey: ["ground-station-devices"] })
    },
    onError: (e) => setActionError(errorDetail(e, "Couldn't register this device")),
  })

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Ground Station"
        subtitle="Every team/solo run and its rig — a device is private to its owner and ops, no secret needed on either side."
      />

      {actionError && <p className="text-sm text-red-500">{actionError}</p>}

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-foreground">Mission runs</h2>
        {attemptsLoading ? (
          <Spinner />
        ) : attempts.length === 0 ? (
          <EmptyState title="No one has started the Ground Station mission yet" />
        ) : (
          <div className="flex flex-col gap-2">
            {attempts.map((a: GroundStationAttemptSummary) => (
              <Link
                key={a.attempt_id}
                to="/learn/missions/ground-station/$attemptId"
                params={{ attemptId: a.attempt_id }}
                className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 p-4 bg-card border border-border rounded-2xl hover:ring-1 hover:ring-primary/30 transition-shadow"
              >
                <Radio size={16} className="text-muted-foreground shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-foreground">{a.owner_label}</span>
                    {a.team_id && <span className="text-xs text-muted-foreground">Team</span>}
                    {a.device_status && <StatusPill status={a.device_status} />}
                  </div>
                  {a.device_last_seen_at && (
                    <div className="text-xs text-muted-foreground mt-0.5">
                      Last seen {new Date(a.device_last_seen_at).toLocaleString()}
                    </div>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Shared / demo rigs</h2>
          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-1.5 h-8 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <Plus size={13} /> New device
          </button>
        </div>
        {devicesLoading ? (
          <Spinner />
        ) : orphanDevices.length === 0 ? (
          <EmptyState title="No shared devices" hint="Register one for a booth/demo kit that isn't tied to a student's mission run." />
        ) : (
          <div className="flex flex-col gap-2">
            {orphanDevices.map((d: GroundStationDevice) => (
              <div key={d.id} className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 p-4 bg-card border border-border rounded-2xl">
                <Antenna size={16} className="text-muted-foreground shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-foreground">{d.label}</span>
                    <StatusPill status={d.status} />
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <code className="text-xs text-muted-foreground font-mono">{d.id}</code>
                    <button
                      type="button"
                      onClick={() => void navigator.clipboard.writeText(d.id)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <Copy size={11} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {addOpen && (
        <Modal title="Register a shared device" onClose={() => setAddOpen(false)}>
          <p className="text-sm text-muted-foreground">
            For a booth/demo kit with no student owner. Its ESP32 posts to this device's id — no secret, no
            configuration beyond the id itself.
          </p>
          <Field label="Label">
            <input
              autoFocus
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Exhibition Booth Rig"
              className="w-full h-9 px-3 rounded-lg ring-1 ring-border bg-background text-sm"
            />
          </Field>
          <ModalActions
            onCancel={() => setAddOpen(false)}
            onConfirm={() => createMutation.mutate()}
            loading={createMutation.isPending}
            disabled={!label.trim()}
            label="Register"
          />
        </Modal>
      )}
    </div>
  )
}
