import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react"
import {
  addAddonApi,
  addSessionApi,
  billSessionsApi,
  getBillableSessionsApi,
  updateLetterApi,
  deleteAddonApi,
  deleteSessionApi,
  updateAddonApi,
  updateSessionApi,
} from "@/api/instructors/payments_admin"
import { Button } from "@/components/ui/button"
import { getDeliveryRolesApi } from "@/api/sessions/openings"
import type { PaymentAddon, PaymentLetter, PaymentSession } from "@/types/instructors"

/**
 * The payment letter's table, editable (I5-1).
 *
 * `PaymentSession` always carried every column the generated document prints.
 * The old UI exposed three of them on the *add* form — with the role
 * hardcoded to "Facilitator" — and rendered existing rows as a read-only
 * paragraph, so date, location and duration could never be set from the
 * portal at all. That is why the finished letter was being generated here and
 * then hand-fixed in Microsoft Word every time.
 *
 * No migration: this is the model catching up with itself.
 *
 * Cells save on blur rather than behind a Save button. The letter is built by
 * someone reading numbers off another screen, and a per-row save step is one
 * more thing to forget before generating the PDF.
 *
 * A **signed** letter is read-only. It is what the instructor put their name
 * to, and the stored signed PDF would otherwise start disagreeing with the
 * table the certificates are generated from.
 */

const cell =
  "w-full h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"

export function PaymentLetterTable({ letter }: { letter: PaymentLetter }) {
  const qc = useQueryClient()
  const [error, setError] = useState("")
  // I5-3: roles are configurable, so the options come from the API. The
  // *stored* value stays the role's name — a signed letter has to keep saying
  // what it said even if someone renames the role later.
  const { data: deliveryRoles = [] } = useQuery({
    queryKey: ["delivery-roles"], queryFn: () => getDeliveryRolesApi(),
  })
  const roleNames = deliveryRoles.map((r) => r.name)
  const locked = letter.status === "signed" || letter.status === "paid"

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
  const onError = (e: any) =>
    setError(e?.response?.data?.detail ?? "Could not save that change")

  const saveSession = useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Parameters<typeof updateSessionApi>[1]) =>
      updateSessionApi(id, data),
    onSuccess: () => { setError(""); refresh() },
    onError,
  })
  const saveAddon = useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Parameters<typeof updateAddonApi>[1]) =>
      updateAddonApi(id, data),
    onSuccess: () => { setError(""); refresh() },
    onError,
  })
  const removeSession = useMutation({
    mutationFn: deleteSessionApi, onSuccess: refresh, onError,
  })
  const removeAddon = useMutation({
    mutationFn: deleteAddonApi, onSuccess: refresh, onError,
  })
  const newSession = useMutation({
    mutationFn: () => addSessionApi(letter.id, {
      workshop_description: "", role: "Facilitator", compensation_aed: 0,
      sort_order: (letter.sessions.at(-1)?.sort_order ?? 0) + 1,
    }),
    onSuccess: refresh, onError,
  })
  const newAddon = useMutation({
    mutationFn: () => addAddonApi(letter.id, {
      description: "", amount_aed: 0,
      sort_order: (letter.addons.at(-1)?.sort_order ?? 0) + 1,
    } as any),
    onSuccess: refresh, onError,
  })

  /** Reorder by swapping the two rows' sort_order — the document reads that
   *  column, so nothing else has to know about ordering. */
  const swapSessions = (a: PaymentSession, b: PaymentSession) => {
    saveSession.mutate({ id: a.id, sort_order: b.sort_order })
    saveSession.mutate({ id: b.id, sort_order: a.sort_order })
  }
  const swapAddons = (a: PaymentAddon, b: PaymentAddon) => {
    saveAddon.mutate({ id: a.id, sort_order: b.sort_order })
    saveAddon.mutate({ id: b.id, sort_order: a.sort_order })
  }

  // I5-8: completed sessions with no payment line yet.
  const { data: billable = [] } = useQuery({
    queryKey: ["billable", letter.id],
    queryFn: () => getBillableSessionsApi(letter.id),
    enabled: !locked,
  })
  const bill = useMutation({
    mutationFn: (ids: string[]) => billSessionsApi({ letterId: letter.id, sessionIds: ids }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billable", letter.id] })
      refresh()
    },
    onError,
  })
  // I5-7: certificates are opt-out, set here and honoured at signing. Editable
  // even on a signed letter — it changes nothing the instructor agreed to.
  const setCertificates = useMutation({
    mutationFn: (on: boolean) => updateLetterApi({ id: letter.id, issue_certificates: on }),
    onSuccess: refresh,
    onError,
  })

  const total =
    letter.sessions.reduce((s, x) => s + (x.compensation_aed || 0), 0) +
    letter.addons.reduce((s, x) => s + (x.amount_aed || 0), 0)

  return (
    <div className="space-y-4">
      {locked && (
        <p className="text-xs text-muted-foreground">
          This letter is {letter.status}. Its lines can&apos;t be changed — issue a corrected
          letter instead.
        </p>
      )}

      <div>
        <p className="text-xs font-semibold text-muted-foreground mb-2">Sessions</p>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="text-xs text-muted-foreground text-left">
                <th className="font-medium pb-1 pr-2 w-[7.5rem]">Date</th>
                <th className="font-medium pb-1 pr-2">Workshop</th>
                <th className="font-medium pb-1 pr-2 w-44">Role</th>
                <th className="font-medium pb-1 pr-2 w-36">Location</th>
                <th className="font-medium pb-1 pr-2 w-20">Hours</th>
                <th className="font-medium pb-1 pr-2 w-24">AED</th>
                <th className="pb-1 w-20" />
              </tr>
            </thead>
            <tbody>
              {letter.sessions.map((s, i) => (
                <tr key={s.id}>
                  <td className="pr-2 py-1">
                    <input
                      className={cell} defaultValue={s.session_date ?? ""} disabled={locked}
                      placeholder="12/07/2026"
                      onBlur={(e) => e.target.value !== (s.session_date ?? "") &&
                        saveSession.mutate({ id: s.id, session_date: e.target.value || null })}
                    />
                  </td>
                  <td className="pr-2 py-1">
                    <input
                      className={cell} defaultValue={s.workshop_description} disabled={locked}
                      placeholder="CubeSat workshop"
                      onBlur={(e) => e.target.value !== s.workshop_description &&
                        saveSession.mutate({ id: s.id, workshop_description: e.target.value })}
                    />
                  </td>
                  <td className="pr-2 py-1">
                    <select
                      className={cell} value={s.role} disabled={locked}
                      onChange={(e) =>
                        saveSession.mutate({ id: s.id, role: e.target.value })}
                    >
                      {/* The row's own value first, so a role that has since
                          been renamed or retired still renders its snapshot. */}
                      {[s.role, ...roleNames.filter((r) => r !== s.role)]
                        .map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td className="pr-2 py-1">
                    <input
                      className={cell} defaultValue={s.location ?? ""} disabled={locked}
                      placeholder="Dubai"
                      onBlur={(e) => e.target.value !== (s.location ?? "") &&
                        saveSession.mutate({ id: s.id, location: e.target.value || null })}
                    />
                  </td>
                  <td className="pr-2 py-1">
                    <input
                      type="number" step="0.5" min={0} className={`${cell} text-right tabular-nums`}
                      defaultValue={s.duration_hours ?? ""} disabled={locked}
                      onBlur={(e) => {
                        const v = e.target.value === "" ? null : Number(e.target.value)
                        if (v !== (s.duration_hours ?? null)) {
                          saveSession.mutate({ id: s.id, duration_hours: v })
                        }
                      }}
                    />
                  </td>
                  <td className="pr-2 py-1">
                    <input
                      type="number" min={0} className={`${cell} text-right tabular-nums`}
                      defaultValue={s.compensation_aed} disabled={locked}
                      onBlur={(e) => Number(e.target.value) !== s.compensation_aed &&
                        saveSession.mutate({ id: s.id, compensation_aed: Number(e.target.value) || 0 })}
                    />
                  </td>
                  <td className="py-1">
                    <div className="flex items-center gap-0.5">
                      <button
                        disabled={locked || i === 0}
                        onClick={() => swapSessions(s, letter.sessions[i - 1])}
                        className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                        aria-label="Move up"
                      ><ArrowUp size={14} /></button>
                      <button
                        disabled={locked || i === letter.sessions.length - 1}
                        onClick={() => swapSessions(s, letter.sessions[i + 1])}
                        className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                        aria-label="Move down"
                      ><ArrowDown size={14} /></button>
                      <button
                        disabled={locked}
                        onClick={() => removeSession.mutate(s.id)}
                        className="p-1 text-muted-foreground hover:text-red-600 disabled:opacity-30"
                        aria-label="Remove row"
                      ><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {letter.sessions.length === 0 && (
                <tr><td colSpan={7} className="py-2 text-sm text-muted-foreground">
                  No sessions on this letter yet.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        {!locked && (
          <Button size="sm" variant="outline" className="mt-2"
            onClick={() => newSession.mutate()} disabled={newSession.isPending}>
            <Plus size={14} className="mr-1.5" /> Add a session
          </Button>
        )}
      </div>

      <div>
        <p className="text-xs font-semibold text-muted-foreground mb-2">Add-ons</p>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="text-xs text-muted-foreground text-left">
                <th className="font-medium pb-1 pr-2">Description</th>
                <th className="font-medium pb-1 pr-2 w-40">Notes</th>
                <th className="font-medium pb-1 pr-2 w-24">AED</th>
                <th className="pb-1 w-20" />
              </tr>
            </thead>
            <tbody>
              {letter.addons.map((a, i) => (
                <tr key={a.id}>
                  <td className="pr-2 py-1">
                    <input
                      className={cell} defaultValue={a.description} disabled={locked}
                      placeholder="Poster printing"
                      onBlur={(e) => e.target.value !== a.description &&
                        saveAddon.mutate({ id: a.id, description: e.target.value })}
                    />
                  </td>
                  <td className="pr-2 py-1">
                    <input
                      className={cell} defaultValue={a.notes ?? ""} disabled={locked}
                      onBlur={(e) => e.target.value !== (a.notes ?? "") &&
                        saveAddon.mutate({ id: a.id, notes: e.target.value || null })}
                    />
                  </td>
                  <td className="pr-2 py-1">
                    <input
                      type="number" min={0} className={`${cell} text-right tabular-nums`}
                      defaultValue={a.amount_aed} disabled={locked}
                      onBlur={(e) => Number(e.target.value) !== a.amount_aed &&
                        saveAddon.mutate({ id: a.id, amount_aed: Number(e.target.value) || 0 })}
                    />
                  </td>
                  <td className="py-1">
                    <div className="flex items-center gap-0.5">
                      <button
                        disabled={locked || i === 0}
                        onClick={() => swapAddons(a, letter.addons[i - 1])}
                        className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                        aria-label="Move up"
                      ><ArrowUp size={14} /></button>
                      <button
                        disabled={locked || i === letter.addons.length - 1}
                        onClick={() => swapAddons(a, letter.addons[i + 1])}
                        className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                        aria-label="Move down"
                      ><ArrowDown size={14} /></button>
                      <button
                        disabled={locked}
                        onClick={() => removeAddon.mutate(a.id)}
                        className="p-1 text-muted-foreground hover:text-red-600 disabled:opacity-30"
                        aria-label="Remove row"
                      ><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {letter.addons.length === 0 && (
                <tr><td colSpan={4} className="py-2 text-sm text-muted-foreground">
                  No add-ons.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        {!locked && (
          <Button size="sm" variant="outline" className="mt-2"
            onClick={() => newAddon.mutate()} disabled={newAddon.isPending}>
            <Plus size={14} className="mr-1.5" /> Add an add-on
          </Button>
        )}
      </div>

      {billable.length > 0 && (
        <div className="rounded-xl border border-dashed border-border p-3 flex flex-col gap-2">
          <p className="text-xs font-semibold text-foreground">
            {billable.length} delivered session{billable.length === 1 ? "" : "s"} not on any letter
          </p>
          <div className="flex flex-col gap-1">
            {billable.map((b) => (
              <div key={b.session_id} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-foreground truncate">
                  {b.session_date} · {b.workshop_description}
                  <span className="text-xs text-muted-foreground">
                    {" "}· {b.role}{b.location ? ` · ${b.location}` : ""}
                  </span>
                </span>
                <button
                  onClick={() => bill.mutate([b.session_id])}
                  disabled={bill.isPending}
                  className="h-7 px-2.5 text-xs border border-border rounded-lg hover:bg-muted shrink-0 disabled:opacity-40"
                >
                  Add
                </button>
              </div>
            ))}
          </div>
          <button
            onClick={() => bill.mutate(billable.map((b) => b.session_id))}
            disabled={bill.isPending}
            className="self-start h-8 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 disabled:opacity-40"
          >
            {bill.isPending ? "Adding…" : "Add all"}
          </button>
          <p className="text-xs text-muted-foreground">
            Date, workshop, role, location and hours are filled in from the session. The
            amount stays blank — that&apos;s yours to set.
          </p>
        </div>
      )}

      <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
        <input
          type="checkbox"
          checked={letter.issue_certificates ?? true}
          onChange={(e) => setCertificates.mutate(e.target.checked)}
          className="rounded text-primary focus:ring-primary border-border bg-background"
        />
        Issue a workshop-delivery certificate per session when this is signed
      </label>

      <div className="flex items-center justify-between border-t border-border pt-2">
        <span className="text-xs text-muted-foreground">
          {locked ? "Locked" : "Changes save as you leave each box."}
        </span>
        <span className="text-sm font-semibold text-foreground tabular-nums">
          Total AED {total.toLocaleString()}
        </span>
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
