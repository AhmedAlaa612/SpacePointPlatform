import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Boxes, CheckCircle2, X } from "lucide-react"
import {
  getKitsApi,
  getLocationsApi,
  getSessionKitsApi,
  issueSessionKitsApi,
  removeSessionKitApi,
  returnSessionKitsApi,
  setSessionKitsApi,
} from "@/api/inventory"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

/**
 * Kits for a session, on the ops side (I2-1/I2-3).
 *
 * Lives in its own file rather than inside Cohorts.tsx, which is already
 * ~105 KB and has produced three stale-prop bugs of the same class. The
 * modal takes one import and one line.
 */
export function SessionKitAssignment({ sessionId, hasInstructor, onChanged }: {
  sessionId: string
  hasInstructor: boolean
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const [picking, setPicking] = useState(false)
  const [returning, setReturning] = useState(false)
  const [error, setError] = useState("")

  const { data } = useQuery({
    queryKey: ["session-kits", sessionId],
    queryFn: () => getSessionKitsApi(sessionId),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["session-kits", sessionId] })
    qc.invalidateQueries({ queryKey: ["inv-kits"] })
    onChanged()
  }

  const remove = useMutation({
    mutationFn: (kitId: string) => removeSessionKitApi({ sessionId, kitId }),
    onSuccess: refresh,
  })
  const issue = useMutation({
    mutationFn: () => issueSessionKitsApi({ sessionId }),
    onSuccess: () => { setError(""); refresh() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not hand the kits out"),
  })

  const kits = data?.kits ?? []
  const anyOut = kits.some((k) => k.holder_name)

  return (
    <div className="border-t border-border pt-4 mt-4 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Boxes size={14} /> Kits
        </p>
        <button onClick={() => setPicking(true)} className="text-xs text-primary hover:underline">
          Choose kits
        </button>
      </div>

      {kits.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No kits for this session. Sessions without kits are unaffected by any of this.
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            {kits.map((k) => (
              <div key={k.kit_id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0">
                  <span className="font-mono text-foreground">{k.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {k.holder_name ? ` · with ${k.holder_name}` : ` · ${k.location_name}`}
                  </span>
                </span>
                <span className="flex items-center gap-2 shrink-0">
                  {k.post_checked ? (
                    <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <AlertTriangle size={13} className="text-amber-600 dark:text-amber-400" />
                  )}
                  <button
                    onClick={() => remove.mutate(k.kit_id)}
                    className="text-muted-foreground hover:text-red-600"
                    title="Remove from this session"
                  >
                    <X size={13} />
                  </button>
                </span>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2 mt-1">
            {!anyOut && (
              <button
                onClick={() => issue.mutate()}
                disabled={issue.isPending || !hasInstructor}
                title={hasInstructor ? undefined : "Assign an instructor to this session first"}
                className="h-8 px-3 bg-primary text-primary-foreground rounded-lg text-xs font-medium disabled:opacity-50"
              >
                {issue.isPending ? "…" : "Hand out to the instructor"}
              </button>
            )}
            {anyOut && (
              <button
                onClick={() => setReturning(true)}
                className="h-8 px-3 border border-border rounded-lg text-xs font-medium text-muted-foreground hover:bg-muted"
              >
                Receive them back
              </button>
            )}
          </div>

          {!anyOut && !hasInstructor && (
            <p className="text-xs text-muted-foreground">Assign an instructor first.</p>
          )}
          {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        </>
      )}

      {picking && (
        <KitPicker
          sessionId={sessionId}
          selected={kits.map((k) => k.kit_id)}
          onClose={() => setPicking(false)}
          onDone={() => { setPicking(false); refresh() }}
        />
      )}
      {returning && (
        <ReceiveModal
          sessionId={sessionId}
          onClose={() => setReturning(false)}
          onDone={() => { setReturning(false); refresh() }}
        />
      )}
    </div>
  )
}

function KitPicker({ sessionId, selected, onClose, onDone }: {
  sessionId: string
  selected: string[]
  onClose: () => void
  onDone: () => void
}) {
  const [chosen, setChosen] = useState<string[]>(selected)
  const { data: kits = [] } = useQuery({ queryKey: ["inv-kits", "", "", false], queryFn: () => getKitsApi() })

  // The API takes the whole set and is idempotent, so the picker resubmits
  // everything rather than diffing.
  const save = useMutation({
    mutationFn: () => setSessionKitsApi({ sessionId, kitIds: chosen }),
    onSuccess: onDone,
  })

  return (
    <Modal title="Kits for this session" onClose={onClose} maxWidth="max-w-md">
      <div className="flex flex-col gap-1 max-h-[50vh] overflow-y-auto">
        {kits.map((k) => {
          const on = chosen.includes(k.id)
          return (
            <label
              key={k.id}
              className={cn(
                "flex items-center justify-between gap-2 px-3 py-2 rounded-xl border cursor-pointer transition-colors",
                on ? "border-primary/30 bg-primary/5" : "border-border hover:bg-muted",
              )}
            >
              <span className="min-w-0">
                <span className="font-mono text-sm text-foreground">{k.label}</span>
                <span className="block text-xs text-muted-foreground truncate">
                  {k.location_name}
                  {k.holder_name && ` · with ${k.holder_name}`}
                  {k.shortage_count > 0 && ` · ${k.shortage_count} missing`}
                </span>
              </span>
              <input
                type="checkbox" checked={on}
                onChange={() => setChosen(on ? chosen.filter((id) => id !== k.id) : [...chosen, k.id])}
              />
            </label>
          )
        })}
        {kits.length === 0 && (
          <p className="text-sm text-muted-foreground py-4 text-center">No kits exist yet.</p>
        )}
      </div>
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={false}
        label="Save"
      />
    </Modal>
  )
}

function ReceiveModal({ sessionId, onClose, onDone }: {
  sessionId: string
  onClose: () => void
  onDone: () => void
}) {
  const { data: locations = [] } = useQuery({ queryKey: ["inv-locations"], queryFn: () => getLocationsApi() })
  const [locationId, setLocationId] = useState("")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: returnSessionKitsApi,
    onSuccess: onDone,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  return (
    <Modal title="Receive the kits back" onClose={onClose}>
      <Field label="Where are they going?">
        <select
          value={locationId} onChange={(e) => setLocationId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        >
          <option value="">Choose…</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </Field>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      <ModalActions
        onCancel={onClose}
        onConfirm={() => { setError(""); mutation.mutate({ sessionId, toLocationId: locationId }) }}
        loading={mutation.isPending}
        disabled={!locationId}
        label="Received"
      />
    </Modal>
  )
}
