import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Boxes, Check, CheckCircle2, PackageCheck } from "lucide-react"
import {
  confirmCollectedApi,
  getCheckFormApi,
  getLocationsApi,
  getSessionKitsApi,
  returnSessionKitsApi,
  submitCheckApi,
  type ExpectedCount,
} from "@/api/inventory"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

/**
 * Kits for this session, on the instructor's own page (I2-2/I2-3).
 *
 * Renders nothing at all when no kits are assigned — most sessions have none,
 * and they must look exactly as they did before this existed.
 *
 * The post-session count is what unlocks "Mark completed". The pre-session
 * one is offered but never blocks: an instructor standing in front of thirty
 * students at 9am cannot be held up by a form, and one they're forced through
 * gets filled with guesses.
 */
export function SessionKitsPanel({
  sessionId,
  isStarted,
  onChanged,
}: {
  sessionId: string
  isStarted: boolean
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const [checking, setChecking] = useState<{ kitId: string; label: string; phase: "pre" | "post" } | null>(null)
  const [returning, setReturning] = useState(false)

  const { data } = useQuery({
    queryKey: ["session-kits", sessionId],
    queryFn: () => getSessionKitsApi(sessionId),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["session-kits", sessionId] })
    onChanged()
  }

  const [justConfirmed, setJustConfirmed] = useState(false)
  const collected = useMutation({
    mutationFn: () => confirmCollectedApi(sessionId),
    onSuccess: () => { setJustConfirmed(true); refresh() },
  })

  if (!data || data.kits.length === 0) return null

  const anyOut = data.kits.some((k) => k.holder_name)

  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Boxes size={15} /> Kits for this session
          </p>
          {data.can_finish ? (
            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
              <CheckCircle2 size={11} /> All counted
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
              <AlertTriangle size={11} /> {data.outstanding_post_checks.length} to count
            </span>
          )}
        </div>

        {!data.can_finish && (
          <p className="text-xs text-muted-foreground -mt-1">
            Check what&apos;s in each kit — that&apos;s what lets you mark this session completed.
          </p>
        )}

        {data.pending_confirmation && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/5 px-3 py-2.5">
            <p className="text-xs text-foreground">
              These kits were issued to you. Confirm you actually have them in hand.
            </p>
            <Button
              size="sm"
              disabled={collected.isPending}
              onClick={() => collected.mutate()}
            >
              <PackageCheck size={14} className="mr-1.5" />
              {collected.isPending ? "Confirming…" : "I have them"}
            </Button>
          </div>
        )}
        {justConfirmed && !data.pending_confirmation && (
          <p className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 size={13} /> Confirmed — you have these kits.
          </p>
        )}

        <div className="flex flex-col gap-2">
          {data.kits.map((k) => (
            <div
              key={k.kit_id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/50 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground font-mono">{k.label}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {k.template_name}
                  {k.pre_checked && <span className="text-emerald-600 dark:text-emerald-400"> · checked</span>}
                  {k.post_checked && <span className="text-emerald-600 dark:text-emerald-400"> · checked</span>}
                </p>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {!k.pre_checked && !isStarted && (
                  <Button
                    size="sm" variant="outline"
                    onClick={() => setChecking({ kitId: k.kit_id, label: k.label, phase: "pre" })}
                  >
                    Check kit
                  </Button>
                )}
                {k.post_checked ? (
                  <Check size={16} className="text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <Button
                    size="sm"
                    onClick={() => setChecking({ kitId: k.kit_id, label: k.label, phase: "post" })}
                  >
                    Check kit
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>

        {anyOut && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setReturning(true)}>
              Hand them back
            </Button>
          </div>
        )}
      </CardContent>

      {checking && (
        <CheckModal
          sessionId={sessionId}
          kitId={checking.kitId}
          label={checking.label}
          phase={checking.phase}
          onClose={() => setChecking(null)}
          onDone={() => { setChecking(null); refresh() }}
        />
      )}
      {returning && (
        <ReturnModal
          sessionId={sessionId}
          onClose={() => setReturning(false)}
          onDone={() => { setReturning(false); refresh() }}
        />
      )}
    </Card>
  )
}

/** Prefilled with what we believe is in the box. One tap for the normal case;
 *  a form that demands 27 numbers gets 27 guesses. */
function CheckModal({ sessionId, kitId, label, phase, onClose, onDone }: {
  sessionId: string
  kitId: string
  label: string
  phase: "pre" | "post"
  onClose: () => void
  onDone: () => void
}) {
  const [counts, setCounts] = useState<Record<string, number> | null>(null)
  const [note, setNote] = useState("")
  const [error, setError] = useState("")

  const { data: lines = [] } = useQuery<ExpectedCount[]>({
    queryKey: ["check-form", sessionId, kitId],
    queryFn: () => getCheckFormApi({ sessionId, kitId }),
  })

  // Seed from the server's view the first time the form loads.
  const current = counts ?? Object.fromEntries(lines.map((l) => [l.item_id, l.expected]))

  const submit = useMutation({
    mutationFn: submitCheckApi,
    onSuccess: onDone,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not save the count"),
  })

  const short = lines.filter((l) => (current[l.item_id] ?? 0) < l.required)

  return (
    <Modal
      title={`Check kit — ${label}`}
      onClose={onClose}
      maxWidth="max-w-md"
    >
      <p className="text-xs text-muted-foreground -mt-1">
        What we expect is already filled in. Change only what&apos;s different — anything short
        gets reported automatically. Screws and wire aren&apos;t listed; they&apos;re not worth counting.
      </p>

      <div className="flex flex-col gap-1.5 max-h-[45vh] overflow-y-auto">
        {lines.map((l) => {
          const value = current[l.item_id] ?? 0
          const isShort = value < l.required
          return (
            <div key={l.item_id} className="flex items-center justify-between gap-3">
              <span className={cn("text-sm", isShort ? "text-amber-700 dark:text-amber-400" : "text-foreground")}>
                {l.item_name}
                <span className="text-xs text-muted-foreground"> / {l.required}</span>
              </span>
              <input
                type="number" min={0} value={value}
                onChange={(e) =>
                  setCounts({ ...current, [l.item_id]: Math.max(0, Number(e.target.value) || 0) })
                }
                className="w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
              />
            </div>
          )
        })}
        {lines.length === 0 && (
          <p className="text-sm text-muted-foreground py-2">
            This kit has no parts list yet, so there&apos;s nothing to count.
          </p>
        )}
      </div>

      {short.length > 0 && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          {short.length} item{short.length === 1 ? "" : "s"} short — operations will see this.
        </p>
      )}

      <Field label="Note (optional)">
        <input
          value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Anything worth flagging"
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        />
      </Field>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <div className="flex flex-col gap-2">
        <ModalActions
          onCancel={onClose}
          onConfirm={() => {
            setError("")
            submit.mutate({ sessionId, kitId, phase, counts: current, note: note || null })
          }}
          loading={submit.isPending}
          disabled={lines.length === 0}
          label="Save the count"
        />
        <button
          onClick={() => {
            setError("")
            submit.mutate({ sessionId, kitId, phase, skipped: true, note: note || null })
          }}
          className="text-xs text-muted-foreground hover:text-foreground underline"
        >
          {phase === "pre"
            ? "Skip — I'll count it later"
            : "Can't count it right now — record that"}
        </button>
      </div>
    </Modal>
  )
}

function ReturnModal({ sessionId, onClose, onDone }: {
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
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record the return"),
  })

  return (
    <Modal title="Hand the kits back" onClose={onClose}>
      <Field label="Where are you leaving them?">
        <select
          value={locationId} onChange={(e) => setLocationId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
        >
          <option value="">Choose…</option>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <p className="text-xs text-muted-foreground mt-1">
          Operations confirms they arrived — this records that you handed them over.
        </p>
      </Field>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      <ModalActions
        onCancel={onClose}
        onConfirm={() => { setError(""); mutation.mutate({ sessionId, toLocationId: locationId }) }}
        loading={mutation.isPending}
        disabled={!locationId}
        label="Hand them back"
      />
    </Modal>
  )
}
