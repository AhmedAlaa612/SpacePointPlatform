import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { Antenna, Copy, Plus, RefreshCw } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import {
  listDevices, registerDevice, rotateDeviceSecret,
  type GroundStationDevice, type DeviceRegisterResult,
} from "@/api/groundStation"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** Ground Station device registry (2026-09) — the admin side of a feature
 * that was, until now, API-only: registering a device (getting the secret
 * the on-site agent needs) required a raw curl call. This is that missing
 * "click a button, get a secret" page. */
export default function GroundStationDevices() {
  const queryClient = useQueryClient()
  const [addOpen, setAddOpen] = useState(false)
  const [label, setLabel] = useState("")
  const [actionError, setActionError] = useState("")
  const [revealed, setRevealed] = useState<DeviceRegisterResult | null>(null)

  const { data: devices = [], isLoading } = useQuery({
    queryKey: ["ground-station-devices"],
    queryFn: listDevices,
  })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["ground-station-devices"] })

  const createMutation = useMutation({
    mutationFn: () => registerDevice(label.trim()),
    onSuccess: (result) => { setActionError(""); setAddOpen(false); setLabel(""); setRevealed(result); invalidate() },
    onError: (e) => setActionError(errorDetail(e, "Couldn't register this device")),
  })
  const rotateMutation = useMutation({
    mutationFn: (deviceId: string) => rotateDeviceSecret(deviceId),
    onSuccess: (result) => { setActionError(""); setRevealed(result) },
    onError: (e) => setActionError(errorDetail(e, "Couldn't rotate this device's secret")),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Ground Station devices"
        subtitle="Register a rig to get the device ID + secret its on-site agent needs (ops/ground-station/agent/.env)."
        action={
          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <Plus size={14} /> New device
          </button>
        }
      />

      {actionError && <p className="text-sm text-red-500">{actionError}</p>}

      {isLoading ? (
        <Spinner />
      ) : devices.length === 0 ? (
        <EmptyState
          title="No devices registered yet"
          hint="Register one to get its ID + secret — hand those to whoever's running the agent script next to the hardware."
        />
      ) : (
        <div className="flex flex-col gap-2">
          {devices.map((d: GroundStationDevice) => (
            <div key={d.id} className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 p-4 bg-card border border-border rounded-2xl">
              <Antenna size={16} className="text-muted-foreground shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-foreground">{d.label}</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    d.status === "online"
                      ? "bg-green-500/15 text-green-600 dark:text-green-400"
                      : "bg-muted text-muted-foreground"
                  }`}>
                    {d.status === "online" ? "Online" : "Offline"}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground font-mono mt-0.5">{d.id}</div>
                {d.last_seen_at && (
                  <div className="text-xs text-muted-foreground mt-0.5">
                    Last seen {new Date(d.last_seen_at).toLocaleString()}
                  </div>
                )}
              </div>
              <button
                onClick={() => rotateMutation.mutate(d.id)}
                disabled={rotateMutation.isPending}
                className="flex items-center gap-1.5 h-8 px-3 text-xs font-medium rounded-lg ring-1 ring-border hover:bg-muted disabled:opacity-50 transition-colors shrink-0"
              >
                <RefreshCw size={12} /> Rotate secret
              </button>
            </div>
          ))}
        </div>
      )}

      {addOpen && (
        <Modal title="Register a device" onClose={() => setAddOpen(false)}>
          <Field label="Label">
            <input
              autoFocus
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Lab Rig 1"
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

      {revealed && (
        <Modal title="Device secret — shown once" onClose={() => setRevealed(null)}>
          <p className="text-sm text-muted-foreground">
            Copy this into <code className="text-xs bg-muted px-1 py-0.5 rounded">ops/ground-station/agent/.env</code> now
            — it can't be shown again. Rotating later invalidates this one.
          </p>
          <Field label="Device ID">
            <CopyRow value={revealed.device.id} />
          </Field>
          <Field label="Secret">
            <CopyRow value={revealed.secret} />
          </Field>
          <ModalActions onCancel={() => setRevealed(null)} onConfirm={() => setRevealed(null)} loading={false} disabled={false} label="Done" />
        </Modal>
      )}
    </div>
  )
}

function CopyRow({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex items-center gap-2">
      <code className="flex-1 min-w-0 truncate text-xs bg-muted px-2 py-1.5 rounded-lg font-mono">{value}</code>
      <button
        type="button"
        onClick={() => { void navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
        className="shrink-0 flex items-center gap-1 h-8 px-2.5 text-xs font-medium rounded-lg ring-1 ring-border hover:bg-muted transition-colors"
      >
        <Copy size={12} /> {copied ? "Copied" : "Copy"}
      </button>
    </div>
  )
}
