import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Boxes, Check, CheckCircle2, Clock, PackageCheck } from "lucide-react"
import {
  getCheckFormApi,
  getSessionEquipmentApi,
  getSessionKitsApi,
  markEquipmentReturnLaterApi,
  markKitsReturnedApi,
  receiveSessionKitsApi,
  returnEquipmentApi,
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
 * No custody leg (2026-08-01): a kit assigned to a session is the whole
 * story. There's nothing to "hand" to the instructor and nothing to "hand
 * back" to a location — the instructor just confirms, per kit or all
 * selected at once, that they have it, and later that it's back or coming
 * back later. Ops reviews that report separately, in the session review.
 *
 * The post-session parts count is what unlocks "Mark completed". The
 * pre-session one is offered but never blocks: an instructor standing in
 * front of thirty students at 9am cannot be held up by a form, and one
 * they're forced through gets filled with guesses.
 */
export function SessionKitsPanel({
  sessionId,
  stage,
  locked = false,
  onChanged,
}: {
  sessionId: string
  /** B5: which actions this instance offers. "pre" — receiving kits, before
   *  the session starts. "post" — the post-check and reporting kits back,
   *  once it's over. Both instances read the same underlying kit list; only
   *  the actions on offer differ. */
  stage: "pre" | "post"
  /** The session is marked done — the returned/return-later report (kits and
   *  equipment both) freezes at whatever it says right now. Before that
   *  point either one is a toggle: reporting "returned" and changing your
   *  mind back to "later" is exactly as valid as the other direction. */
  locked?: boolean
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const [checking, setChecking] = useState<{ kitId: string; label: string; phase: "pre" | "post" } | null>(null)
  const [selectedPre, setSelectedPre] = useState<string[]>([])
  const [selectedPost, setSelectedPost] = useState<string[]>([])

  const { data } = useQuery({
    queryKey: ["session-kits", sessionId],
    queryFn: () => getSessionKitsApi(sessionId),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["session-kits", sessionId] })
    onChanged()
  }

  const receive = useMutation({
    mutationFn: (kitIds: string[]) => receiveSessionKitsApi({ sessionId, kitIds }),
    onSuccess: () => { setSelectedPre([]); refresh() },
  })

  const markReturned = useMutation({
    mutationFn: ({ kitIds, later }: { kitIds: string[]; later: boolean }) =>
      markKitsReturnedApi({ sessionId, kitIds, later }),
    onSuccess: () => { setSelectedPost([]); refresh() },
  })

  // Non-kit equipment taken pre-session, surfaced again here (2026-08-01) so
  // "returnable stuff still with you" is one list at the point it actually
  // matters — wrapping up — rather than only living in the pre-session panel.
  const equipment = useQuery({
    queryKey: ["session-equipment", sessionId],
    queryFn: () => getSessionEquipmentApi(sessionId),
    enabled: stage === "post",
  })
  // Taken and still returnable — kept in view even once fully returned, so
  // "actually, later" stays reachable right up until the session locks.
  const returnableOut = (equipment.data?.lines ?? []).filter((l) => l.returnable && l.qty_taken > 0)

  const refreshEquipment = () => {
    qc.invalidateQueries({ queryKey: ["session-equipment", sessionId] })
    onChanged()
  }

  const returnOneEquipment = useMutation({
    mutationFn: (itemId: string) => {
      const line = returnableOut.find((l) => l.item_id === itemId)!
      return returnEquipmentApi({
        sessionId, lines: [{ item_id: itemId, qty: line.outstanding }],
        toWarehouseId: equipment.data?.warehouse_id ?? undefined,
      })
    },
    onSuccess: refreshEquipment,
  })

  // Flags an item as coming back later — or, if it was already marked
  // returned, undoes that first. Same toggle a kit's report gets.
  const flagEquipmentLater = useMutation({
    mutationFn: (itemId: string) => markEquipmentReturnLaterApi({ sessionId, itemIds: [itemId] }),
    onSuccess: refreshEquipment,
  })

  // "Check all kits" — accepts the expected count for every kit not yet
  // post-checked, one tap for the common no-discrepancy case (2026-08-01).
  // Anyone who actually needs to correct a number still can, per-kit, below.
  const checkAll = useMutation({
    mutationFn: async () => {
      for (const kitId of data?.outstanding_post_checks ?? []) {
        const lines = await getCheckFormApi({ sessionId, kitId })
        if (lines.length === 0) {
          await submitCheckApi({ sessionId, kitId, phase: "post", skipped: true })
        } else {
          await submitCheckApi({
            sessionId, kitId, phase: "post",
            counts: Object.fromEntries(lines.map((l) => [l.item_id, l.expected])),
          })
        }
      }
    },
    onSuccess: refresh,
  })

  if (!data || data.kits.length === 0) return null

  const notReceived = data.kits.filter((k) => !k.received)
  const notReturned = data.kits.filter((k) => !k.return_status)
  const allPreSelected = notReceived.length > 0 && selectedPre.length === notReceived.length
  const allPostSelected = notReturned.length > 0 && selectedPost.length === notReturned.length

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
            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
              <Clock size={11} /> {data.outstanding_post_checks.length} uncounted (optional)
            </span>
          )}
        </div>

        {stage === "post" && !data.can_finish && (
          <p className="text-xs text-muted-foreground -mt-1">
            Counting kits is optional. You can count them now or report them returned later — finishing the session is not blocked.
          </p>
        )}

        {stage === "pre" && !locked && notReceived.length > 0 && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/5 px-3 py-2.5">
            <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={allPreSelected}
                onChange={() => setSelectedPre(allPreSelected ? [] : notReceived.map((k) => k.kit_id))}
              />
              Select all
            </label>
            <Button
              size="sm"
              disabled={selectedPre.length === 0 || receive.isPending}
              onClick={() => receive.mutate(selectedPre)}
            >
              <PackageCheck size={14} className="mr-1.5" />
              {receive.isPending ? "Marking…" : `Mark received (${selectedPre.length})`}
            </Button>
          </div>
        )}

        {stage === "post" && !locked && notReturned.length > 0 && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/5 px-3 py-2.5">
            <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={allPostSelected}
                onChange={() => setSelectedPost(allPostSelected ? [] : notReturned.map((k) => k.kit_id))}
              />
              Select all
            </label>
            <span className="flex items-center gap-2">
              <Button
                size="sm" variant="outline"
                disabled={selectedPost.length === 0 || markReturned.isPending}
                onClick={() => markReturned.mutate({ kitIds: selectedPost, later: true })}
              >
                <Clock size={13} className="mr-1.5" /> Return later
              </Button>
              <Button
                size="sm"
                disabled={selectedPost.length === 0 || markReturned.isPending}
                onClick={() => markReturned.mutate({ kitIds: selectedPost, later: false })}
              >
                {markReturned.isPending ? "Recording…" : `Returned (${selectedPost.length})`}
              </Button>
            </span>
          </div>
        )}

        <div className="flex flex-col gap-2">
          {data.kits.map((k) => (
            <div
              key={k.kit_id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/50 px-3 py-2"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                {stage === "pre" && !locked && !k.received && (
                  <input
                    type="checkbox"
                    checked={selectedPre.includes(k.kit_id)}
                    onChange={() => setSelectedPre((prev) =>
                      prev.includes(k.kit_id) ? prev.filter((id) => id !== k.kit_id) : [...prev, k.kit_id])}
                  />
                )}
                {stage === "post" && !locked && !k.return_status && (
                  <input
                    type="checkbox"
                    checked={selectedPost.includes(k.kit_id)}
                    onChange={() => setSelectedPost((prev) =>
                      prev.includes(k.kit_id) ? prev.filter((id) => id !== k.kit_id) : [...prev, k.kit_id])}
                  />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground font-mono">{k.label}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {k.template_name}
                    {stage === "pre" && k.pre_checked && (
                      <span className="text-emerald-600 dark:text-emerald-400"> · counted</span>
                    )}
                    {stage === "post" && k.post_checked && (
                      <span className="text-emerald-600 dark:text-emerald-400"> · counted</span>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {stage === "pre" && (
                  k.received ? (
                    <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                      <Check size={14} /> Received
                    </span>
                  ) : locked ? (
                    <span className="text-xs text-muted-foreground">Not received</span>
                  ) : (
                    <span className="flex items-center gap-1.5">
                      <button
                        onClick={() => setChecking({ kitId: k.kit_id, label: k.label, phase: "pre" })}
                        className="text-[11px] text-muted-foreground hover:text-foreground underline"
                      >
                        Log contents
                      </button>
                      <Button
                        size="sm" variant="outline"
                        disabled={receive.isPending}
                        onClick={() => receive.mutate([k.kit_id])}
                      >
                        Received
                      </Button>
                    </span>
                  )
                )}
                {stage === "post" && (
                  k.return_status ? (
                    <span className="flex items-center gap-2">
                      <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                        <Check size={14} /> {k.return_status === "return_later" ? "Returning later" : "Returned"}
                      </span>
                      {!locked && (
                        <button
                          onClick={() => markReturned.mutate({
                            kitIds: [k.kit_id], later: k.return_status !== "return_later",
                          })}
                          disabled={markReturned.isPending}
                          className="text-[11px] text-muted-foreground hover:text-foreground underline"
                        >
                          {k.return_status === "return_later" ? "Mark returned instead" : "Return later instead"}
                        </button>
                      )}
                    </span>
                  ) : locked ? (
                    <span className="text-xs text-muted-foreground">Not returned</span>
                  ) : (
                    <span className="flex items-center gap-1.5">
                      <button
                        onClick={() => setChecking({ kitId: k.kit_id, label: k.label, phase: "post" })}
                        className="text-[11px] text-muted-foreground hover:text-foreground underline"
                      >
                        Report missing components
                      </button>
                      <button
                        onClick={() => markReturned.mutate({ kitIds: [k.kit_id], later: true })}
                        className="text-[11px] text-muted-foreground hover:text-foreground underline"
                      >
                        Return later
                      </button>
                      <Button
                        size="sm" variant="outline"
                        disabled={markReturned.isPending}
                        onClick={() => markReturned.mutate({ kitIds: [k.kit_id], later: false })}
                      >
                        Returned
                      </Button>
                    </span>
                  )
                )}
              </div>
            </div>
          ))}
        </div>

        {stage === "post" && !data.can_finish && (
          <Button size="sm" variant="outline" disabled={checkAll.isPending} onClick={() => checkAll.mutate()}>
            {checkAll.isPending ? "Checking…" : "Check all kits"}
          </Button>
        )}

        {stage === "post" && returnableOut.length > 0 && (
          <div className="flex flex-col gap-2 border-t border-border pt-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Also taken pre-session
            </p>
            {returnableOut.map((l) => (
              <div
                key={l.item_id}
                className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/50 px-3 py-2"
              >
                <span className="text-sm text-foreground min-w-0 truncate">
                  {l.item_name} <span className="text-xs text-muted-foreground">× {l.qty_taken}</span>
                </span>
                {l.outstanding <= 0 ? (
                  <span className="flex items-center gap-2 shrink-0">
                    <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                      <Check size={14} /> Returned
                    </span>
                    {!locked && (
                      <button
                        onClick={() => flagEquipmentLater.mutate(l.item_id)}
                        disabled={flagEquipmentLater.isPending}
                        className="text-[11px] text-muted-foreground hover:text-foreground underline"
                      >
                        Return later instead
                      </button>
                    )}
                  </span>
                ) : l.later ? (
                  <span className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px] text-muted-foreground">Returning later</span>
                    {!locked && (
                      <Button
                        size="sm" variant="outline"
                        disabled={returnOneEquipment.isPending}
                        onClick={() => returnOneEquipment.mutate(l.item_id)}
                      >
                        Mark returned instead
                      </Button>
                    )}
                  </span>
                ) : locked ? (
                  <span className="text-[11px] text-muted-foreground shrink-0">Not returned</span>
                ) : (
                  <span className="flex items-center gap-1.5 shrink-0">
                    <Button
                      size="sm" variant="outline"
                      disabled={returnOneEquipment.isPending}
                      onClick={() => returnOneEquipment.mutate(l.item_id)}
                    >
                      Returned
                    </Button>
                    <button
                      onClick={() => flagEquipmentLater.mutate(l.item_id)}
                      disabled={flagEquipmentLater.isPending}
                      className="text-[11px] text-muted-foreground hover:text-foreground underline px-1"
                    >
                      Return later
                    </button>
                  </span>
                )}
              </div>
            ))}
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
                className="!w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
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
