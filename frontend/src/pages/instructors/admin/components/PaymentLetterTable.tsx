import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, Ban, Plus, Trash2 } from "lucide-react"
import {
  addAddonApi,
  addSessionApi,
  billSessionsApi,
  deleteAddonApi,
  deleteSessionApi,
  getBillableSessionsApi,
  listBatchesApi,
  updateAddonApi,
  updateLetterApi,
  updateSessionApi,
} from "@/api/instructors/payments_admin"
import { getDeliveryRolesApi } from "@/api/sessions/openings"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { PaymentAddon, PaymentLetter, PaymentSession } from "@/types/instructors"

const cell =
  "w-full h-9 px-2.5 rounded-[10px] text-xs sm:text-sm text-foreground"

export function PaymentLetterTable({
  letter,
  onIgnoreDraft,
}: {
  letter: PaymentLetter
  onIgnoreDraft?: () => void
}) {
  const qc = useQueryClient()
  const [error, setError] = useState("")
  const { data: deliveryRoles = [] } = useQuery({
    queryKey: ["delivery-roles"],
    queryFn: () => getDeliveryRolesApi(),
  })
  const roleNames = deliveryRoles.map((r) => r.name)
  const locked = letter.status === "signed" || letter.status === "paid"
  const isDraft = letter.status === "draft"

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-cohorts"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-analytics"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-batches"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-todo"] })
    qc.invalidateQueries({ queryKey: ["admin-overview"] })
    qc.invalidateQueries({ queryKey: ["instructor-payment-history"] })
  }

  const onError = (e: any) =>
    setError(e?.response?.data?.detail ?? "Could not save that change")

  const saveSession = useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Parameters<typeof updateSessionApi>[1]) =>
      updateSessionApi(id, data),
    onSuccess: () => {
      setError("")
      refresh()
    },
    onError,
  })

  const saveAddon = useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Parameters<typeof updateAddonApi>[1]) =>
      updateAddonApi(id, data),
    onSuccess: () => {
      setError("")
      refresh()
    },
    onError,
  })

  const removeSession = useMutation({
    mutationFn: deleteSessionApi,
    onSuccess: () => {
      setError("")
      qc.invalidateQueries({ queryKey: ["billable", letter.id] })
      refresh()
    },
    onError,
  })

  const removeAddon = useMutation({
    mutationFn: deleteAddonApi,
    onSuccess: () => {
      setError("")
      refresh()
    },
    onError,
  })

  const newSession = useMutation({
    mutationFn: () =>
      addSessionApi(letter.id, {
        workshop_description: "",
        role: "Facilitator",
        compensation_aed: 0,
        sort_order: (letter.sessions.at(-1)?.sort_order ?? 0) + 1,
      } as any),
    onSuccess: refresh,
    onError,
  })

  const newAddon = useMutation({
    mutationFn: () =>
      addAddonApi(letter.id, {
        description: "",
        amount_aed: 0,
        sort_order: (letter.addons.at(-1)?.sort_order ?? 0) + 1,
      } as any),
    onSuccess: refresh,
    onError,
  })

  const swapSessions = (a: PaymentSession, b: PaymentSession) => {
    saveSession.mutate({ id: a.id, sort_order: b.sort_order })
    saveSession.mutate({ id: b.id, sort_order: a.sort_order })
  }

  const swapAddons = (a: PaymentAddon, b: PaymentAddon) => {
    saveAddon.mutate({ id: a.id, sort_order: b.sort_order })
    saveAddon.mutate({ id: b.id, sort_order: a.sort_order })
  }

  const { data: billable = [] } = useQuery({
    queryKey: ["billable", letter.id],
    queryFn: () => getBillableSessionsApi(letter.id),
    enabled: !locked,
  })

  const bill = useMutation({
    mutationFn: (ids: string[]) => billSessionsApi({ letterId: letter.id, lineIds: ids }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["billable", letter.id] })
      refresh()
    },
    onError,
  })

  const { data: batches = [] } = useQuery({
    queryKey: ["admin-payment-batches"],
    queryFn: listBatchesApi,
  })

  const setBatch = useMutation({
    mutationFn: (batch_id: string | null) => updateLetterApi({ id: letter.id, batch_id }),
    onSuccess: refresh,
    onError,
  })

  const setCertificates = useMutation({
    mutationFn: (on: boolean) => updateLetterApi({ id: letter.id, issue_certificates: on }),
    onSuccess: refresh,
    onError,
  })

  const setAdminNotes = useMutation({
    mutationFn: (admin_notes: string | null) =>
      updateLetterApi({ id: letter.id, admin_notes }),
    onSuccess: refresh,
    onError,
  })

  const total =
    letter.sessions.reduce((s, x) => s + (x.compensation_aed || 0), 0) +
    letter.addons.reduce((s, x) => s + (x.amount_aed || 0), 0)

  const handleSessionsBlur = (s: PaymentSession, raw: string) => {
    const nextCount = raw === "" ? null : Math.max(0, Number(raw))
    if (nextCount === (s.session_count ?? null)) return
    if (nextCount !== null && s.rate_aed != null) {
      saveSession.mutate({
        id: s.id,
        session_count: nextCount,
        compensation_aed: Math.round(nextCount * s.rate_aed * 100) / 100,
      })
    } else {
      saveSession.mutate({ id: s.id, session_count: nextCount })
    }
  }

  const handleRateBlur = (s: PaymentSession, raw: string) => {
    const nextRate = raw === "" ? null : Math.max(0, Number(raw))
    if (nextRate === (s.rate_aed ?? null)) return
    if (nextRate !== null && s.session_count != null) {
      saveSession.mutate({
        id: s.id,
        rate_aed: nextRate,
        compensation_aed: Math.round(s.session_count * nextRate * 100) / 100,
      })
    } else {
      saveSession.mutate({ id: s.id, rate_aed: nextRate })
    }
  }

  return (
    <div className="space-y-5">
      {/* Top Batch & Reference Row */}
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-border flex-wrap">
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Batch
          </span>
          <select
            className="h-9 px-3 rounded-[10px] text-xs font-semibold text-foreground cursor-pointer"
            value={letter.batch_id ?? ""}
            disabled={locked || setBatch.isPending}
            onChange={(e) => setBatch.mutate(e.target.value || null)}
          >
            <option value="" className="bg-popover text-popover-foreground">
              No batch
            </option>
            {batches.map((b) => (
              <option key={b.id} value={b.id} className="bg-popover text-popover-foreground">
                {b.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="text-xs font-mono text-muted-foreground">{letter.reference}</span>
          <span
            className={cn(
              "inline-flex items-center rounded-[10px] px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide",
              letter.status === "paid"
                ? "bg-emerald-600/15 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-600/35"
                : letter.status === "signed"
                  ? "bg-[#653F84] text-white"
                  : letter.status === "published"
                    ? "bg-[#653F84]/12 text-[#653F84] dark:bg-purple-500/20 dark:text-purple-200 border border-[#653F84]/30"
                    : "bg-muted/70 text-foreground border border-border",
            )}
          >
            {letter.status}
          </span>
        </div>
      </div>

      {/* Work Entries */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
            Work Entries ({letter.sessions.length})
          </p>
          {!locked && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => newSession.mutate()}
              disabled={newSession.isPending}
              className="h-8 px-3 rounded-[10px] border-border text-xs font-semibold"
            >
              <Plus size={13} className="mr-1" /> Add Entry
            </Button>
          )}
        </div>

        {/* Mobile card layout */}
        <div className="block md:hidden space-y-3">
          {letter.sessions.map((s, i) => (
            <div
              key={`${s.id}-${s.session_count}-${s.rate_aed}-${s.compensation_aed}-${s.duration_hours}-${s.sort_order}`}
              className="p-3 rounded-[10px] border border-border bg-background space-y-2.5"
            >
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                    Date
                  </label>
                  <input
                    className={cell}
                    defaultValue={s.session_date ?? ""}
                    disabled={locked}
                    placeholder="12/07/2026"
                    onBlur={(e) =>
                      e.target.value !== (s.session_date ?? "") &&
                      saveSession.mutate({ id: s.id, session_date: e.target.value || null })
                    }
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                    Workshop
                  </label>
                  <input
                    className={cell}
                    defaultValue={s.workshop_description}
                    disabled={locked}
                    placeholder="Workshop"
                    onBlur={(e) =>
                      e.target.value !== s.workshop_description &&
                      saveSession.mutate({ id: s.id, workshop_description: e.target.value })
                    }
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                    Role
                  </label>
                  <select
                    className={cell}
                    value={s.role}
                    disabled={locked}
                    onChange={(e) => saveSession.mutate({ id: s.id, role: e.target.value })}
                  >
                    {[s.role, ...roleNames.filter((r) => r !== s.role)].map((r) => (
                      <option key={r} value={r} className="bg-popover text-popover-foreground">
                        {r}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                    Location
                  </label>
                  <input
                    className={cell}
                    defaultValue={s.location ?? ""}
                    disabled={locked}
                    placeholder="Location"
                    onBlur={(e) =>
                      e.target.value !== (s.location ?? "") &&
                      saveSession.mutate({ id: s.id, location: e.target.value || null })
                    }
                  />
                </div>
              </div>

              <div className="grid grid-cols-4 gap-2 items-end">
                <div>
                  <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                    Sess.
                  </label>
                  <input
                    type="number"
                    min={0}
                    step={1}
                    className={`${cell} text-right tabular-nums`}
                    defaultValue={s.session_count ?? ""}
                    disabled={locked}
                    onBlur={(e) => handleSessionsBlur(s, e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                    Hours
                  </label>
                  <input
                    type="number"
                    step={0.5}
                    min={0}
                    className={`${cell} text-right tabular-nums`}
                    defaultValue={s.duration_hours ?? ""}
                    disabled={locked}
                    onBlur={(e) => {
                      const v = e.target.value === "" ? null : Number(e.target.value)
                      if (v !== (s.duration_hours ?? null)) {
                        saveSession.mutate({ id: s.id, duration_hours: v })
                      }
                    }}
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                    Rate
                  </label>
                  <input
                    type="number"
                    min={0}
                    className={`${cell} text-right tabular-nums`}
                    defaultValue={s.rate_aed ?? ""}
                    disabled={locked}
                    onBlur={(e) => handleRateBlur(s, e.target.value)}
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold uppercase text-muted-foreground block mb-1">
                    AED
                  </label>
                  <input
                    type="number"
                    min={0}
                    className={`${cell} text-right font-bold tabular-nums`}
                    defaultValue={s.compensation_aed}
                    disabled={locked}
                    onBlur={(e) =>
                      Number(e.target.value) !== s.compensation_aed &&
                      saveSession.mutate({
                        id: s.id,
                        compensation_aed: Number(e.target.value) || 0,
                      })
                    }
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-1.5 pt-1">
                <button
                  type="button"
                  disabled={locked || i === 0}
                  onClick={() => swapSessions(s, letter.sessions[i - 1])}
                  className="p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                  aria-label="Move up"
                >
                  <ArrowUp size={15} />
                </button>
                <button
                  type="button"
                  disabled={locked || i === letter.sessions.length - 1}
                  onClick={() => swapSessions(s, letter.sessions[i + 1])}
                  className="p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                  aria-label="Move down"
                >
                  <ArrowDown size={15} />
                </button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={locked || removeSession.isPending}
                  onClick={() => removeSession.mutate(s.id)}
                  className="h-8 px-2.5 rounded-[10px] border-rose-600/35 text-rose-600 text-xs font-semibold"
                >
                  <Trash2 size={13} className="mr-1" /> Drop
                </Button>
              </div>
            </div>
          ))}
          {letter.sessions.length === 0 && (
            <p className="text-xs text-muted-foreground py-3">No entries on this letter yet.</p>
          )}
        </div>

        {/* Desktop table layout */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full min-w-[820px] text-xs border-collapse">
            <thead>
              <tr className="border-b border-border text-left text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                <th className="py-2 pr-2 w-28">Date</th>
                <th className="py-2 pr-2">Workshop</th>
                <th className="py-2 pr-2 w-40">Role</th>
                <th className="py-2 pr-2 w-36">Location</th>
                <th className="py-2 pr-2 w-16 text-right">Sess.</th>
                <th className="py-2 pr-2 w-16 text-right">Hrs</th>
                <th className="py-2 pr-2 w-20 text-right">Rate</th>
                <th className="py-2 pr-2 w-24 text-right">AED</th>
                <th className="py-2 w-28 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {letter.sessions.map((s, i) => (
                <tr
                  key={`${s.id}-${s.session_count}-${s.rate_aed}-${s.compensation_aed}-${s.duration_hours}-${s.sort_order}`}
                >
                  <td className="pr-2 py-1.5">
                    <input
                      className={cell}
                      defaultValue={s.session_date ?? ""}
                      disabled={locked}
                      placeholder="12/07/2026"
                      onBlur={(e) =>
                        e.target.value !== (s.session_date ?? "") &&
                        saveSession.mutate({ id: s.id, session_date: e.target.value || null })
                      }
                    />
                  </td>
                  <td className="pr-2 py-1.5">
                    <input
                      className={`${cell} font-semibold`}
                      defaultValue={s.workshop_description}
                      disabled={locked}
                      placeholder="Workshop"
                      onBlur={(e) =>
                        e.target.value !== s.workshop_description &&
                        saveSession.mutate({ id: s.id, workshop_description: e.target.value })
                      }
                    />
                  </td>
                  <td className="pr-2 py-1.5">
                    <select
                      className={cell}
                      value={s.role}
                      disabled={locked}
                      onChange={(e) => saveSession.mutate({ id: s.id, role: e.target.value })}
                    >
                      {[s.role, ...roleNames.filter((r) => r !== s.role)].map((r) => (
                        <option key={r} value={r} className="bg-popover text-popover-foreground">
                          {r}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="pr-2 py-1.5">
                    <input
                      className={cell}
                      defaultValue={s.location ?? ""}
                      disabled={locked}
                      placeholder="Location"
                      onBlur={(e) =>
                        e.target.value !== (s.location ?? "") &&
                        saveSession.mutate({ id: s.id, location: e.target.value || null })
                      }
                    />
                  </td>
                  <td className="pr-2 py-1.5">
                    <input
                      type="number"
                      min={0}
                      step={1}
                      className={`${cell} text-right tabular-nums`}
                      defaultValue={s.session_count ?? ""}
                      disabled={locked}
                      onBlur={(e) => handleSessionsBlur(s, e.target.value)}
                    />
                  </td>
                  <td className="pr-2 py-1.5">
                    <input
                      type="number"
                      step={0.5}
                      min={0}
                      className={`${cell} text-right tabular-nums`}
                      defaultValue={s.duration_hours ?? ""}
                      disabled={locked}
                      onBlur={(e) => {
                        const v = e.target.value === "" ? null : Number(e.target.value)
                        if (v !== (s.duration_hours ?? null)) {
                          saveSession.mutate({ id: s.id, duration_hours: v })
                        }
                      }}
                    />
                  </td>
                  <td className="pr-2 py-1.5">
                    <input
                      type="number"
                      min={0}
                      className={`${cell} text-right tabular-nums`}
                      defaultValue={s.rate_aed ?? ""}
                      disabled={locked}
                      onBlur={(e) => handleRateBlur(s, e.target.value)}
                    />
                  </td>
                  <td className="pr-2 py-1.5">
                    <input
                      type="number"
                      min={0}
                      className={`${cell} text-right font-bold tabular-nums`}
                      defaultValue={s.compensation_aed}
                      disabled={locked}
                      onBlur={(e) =>
                        Number(e.target.value) !== s.compensation_aed &&
                        saveSession.mutate({
                          id: s.id,
                          compensation_aed: Number(e.target.value) || 0,
                        })
                      }
                    />
                  </td>
                  <td className="py-1.5 text-right">
                    <div className="inline-flex items-center gap-1">
                      <button
                        type="button"
                        disabled={locked || i === 0}
                        onClick={() => swapSessions(s, letter.sessions[i - 1])}
                        className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                        aria-label="Move up"
                      >
                        <ArrowUp size={13} />
                      </button>
                      <button
                        type="button"
                        disabled={locked || i === letter.sessions.length - 1}
                        onClick={() => swapSessions(s, letter.sessions[i + 1])}
                        className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                        aria-label="Move down"
                      >
                        <ArrowDown size={13} />
                      </button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={locked || removeSession.isPending}
                        onClick={() => removeSession.mutate(s.id)}
                        className="h-8 px-2 rounded-[10px] border-rose-600/35 text-rose-600 text-xs font-semibold"
                      >
                        <Trash2 size={12} className="mr-1" /> Drop
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {letter.sessions.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-4 text-center text-xs text-muted-foreground">
                    No entries on this letter yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add-ons */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
            Add-ons ({letter.addons.length})
          </p>
          {!locked && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => newAddon.mutate()}
              disabled={newAddon.isPending}
              className="h-8 px-3 rounded-[10px] border-border text-xs font-semibold"
            >
              <Plus size={13} className="mr-1" /> Add Add-on
            </Button>
          )}
        </div>

        <div className="space-y-2">
          {letter.addons.map((a, i) => (
            <div
              key={`${a.id}-${a.amount_aed}-${a.sort_order}`}
              className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_110px_auto] gap-2 items-center"
            >
              <input
                className={cell}
                defaultValue={a.description}
                disabled={locked}
                placeholder="Description"
                onBlur={(e) =>
                  e.target.value !== a.description &&
                  saveAddon.mutate({ id: a.id, description: e.target.value })
                }
              />
              <input
                className={cell}
                defaultValue={a.notes ?? ""}
                disabled={locked}
                placeholder="Notes"
                onBlur={(e) =>
                  e.target.value !== (a.notes ?? "") &&
                  saveAddon.mutate({ id: a.id, notes: e.target.value || null })
                }
              />
              <input
                type="number"
                min={0}
                className={`${cell} text-right font-bold tabular-nums`}
                defaultValue={a.amount_aed}
                disabled={locked}
                onBlur={(e) =>
                  Number(e.target.value) !== a.amount_aed &&
                  saveAddon.mutate({ id: a.id, amount_aed: Number(e.target.value) || 0 })
                }
              />
              <div className="flex items-center justify-end gap-1">
                <button
                  type="button"
                  disabled={locked || i === 0}
                  onClick={() => swapAddons(a, letter.addons[i - 1])}
                  className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                  aria-label="Move up"
                >
                  <ArrowUp size={13} />
                </button>
                <button
                  type="button"
                  disabled={locked || i === letter.addons.length - 1}
                  onClick={() => swapAddons(a, letter.addons[i + 1])}
                  className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
                  aria-label="Move down"
                >
                  <ArrowDown size={13} />
                </button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={locked || removeAddon.isPending}
                  onClick={() => removeAddon.mutate(a.id)}
                  className="h-8 px-2 rounded-[10px] border-rose-600/35 text-rose-600"
                >
                  <Trash2 size={13} />
                </Button>
              </div>
            </div>
          ))}
          {letter.addons.length === 0 && (
            <p className="text-xs text-muted-foreground">No add-ons.</p>
          )}
        </div>
      </div>

      {/* Legacy unbilled lines picker if any session exists outside cohort flow */}
      {billable.length > 0 && (
        <div className="rounded-[10px] border border-dashed border-border p-3.5 space-y-2.5">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
              Unbilled Delivered Work ({billable.length})
            </p>
            <Button
              size="sm"
              onClick={() => bill.mutate(billable.map((b) => b.line_id))}
              disabled={bill.isPending}
              className="h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
            >
              {bill.isPending ? "Adding..." : "Add All"}
            </Button>
          </div>
          <div className="space-y-1.5">
            {billable.map((b) => (
              <div
                key={b.line_id}
                className="flex items-center justify-between gap-3 text-xs py-1"
              >
                <div className="flex items-center gap-2 flex-wrap text-foreground">
                  <span className="font-bold">{b.workshop_description}</span>
                  <span className="text-muted-foreground">{b.session_date}</span>
                  <span className="rounded-[10px] border border-border px-2 py-0.5 text-[11px]">
                    {b.role}
                  </span>
                  {b.location && <span className="text-muted-foreground">{b.location}</span>}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => bill.mutate([b.line_id])}
                  disabled={bill.isPending}
                  className="h-7 px-2.5 rounded-[10px] border-border text-xs font-semibold shrink-0"
                >
                  Add
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Certificate toggle, Admin notes, & Total */}
      <div className="space-y-3 pt-3 border-t border-border">
        <label className="inline-flex items-center gap-2 text-xs sm:text-sm text-foreground cursor-pointer select-none">
          <input
            type="checkbox"
            checked={letter.issue_certificates ?? true}
            onChange={(e) => setCertificates.mutate(e.target.checked)}
            className="h-4 w-4 rounded-[10px]"
          />
          <span>Issue delivery certificates on sign</span>
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
          <div>
            <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">
              Admin Notes
            </label>
            <input
              key={`${letter.id}-${letter.admin_notes ?? ""}`}
              defaultValue={letter.admin_notes ?? ""}
              placeholder="Internal notes..."
              className="w-full h-9 px-3 rounded-[10px] text-xs"
              onBlur={(e) => {
                const val = e.target.value.trim() || null
                if (val !== (letter.admin_notes ?? null)) {
                  setAdminNotes.mutate(val)
                }
              }}
            />
          </div>
          <div className="text-right">
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
              Letter Total
            </p>
            <p className="font-display text-2xl font-extrabold text-foreground tabular-nums">
              AED {total.toLocaleString()}
            </p>
          </div>
        </div>
      </div>

      {/* Footer actions */}
      <div className="flex items-center justify-between gap-2 pt-2 border-t border-border flex-wrap">
        <span className="text-xs text-muted-foreground">
          {locked ? "Locked" : "Saves on blur"}
        </span>
        {isDraft && onIgnoreDraft && (
          <Button
            variant="outline"
            size="lg"
            onClick={onIgnoreDraft}
            className="h-9 px-3.5 rounded-[10px] border-rose-600/40 text-rose-600 text-xs font-bold"
          >
            <Ban size={14} className="mr-1.5" /> Ignore Draft
          </Button>
        )}
      </div>

      {error && <p className="text-xs font-semibold text-rose-600">{error}</p>}
    </div>
  )
}
