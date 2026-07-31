import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, Plus } from "lucide-react"
import {
  createDeliveryRoleApi,
  getDeliveryRolesApi,
  getResponsibilitiesApi,
  setResponsibilitiesApi,
  updateDeliveryRoleApi,
} from "@/api/sessions/openings"
import { Spinner } from "@/pages/admin/components/common"

/**
 * Delivery roles and the responsibilities text (I5-3, I5-5).
 *
 * Roles are data rather than an enum, which is what let staffing and payment
 * letters share one vocabulary. Two rules worth knowing while editing here:
 *
 * - **Order is seniority.** "The lead" is whatever sits at the top, so moving
 *   a role changes who kits are issued to and who is assigned by default.
 * - **Renaming is safe.** Payment letters snapshot the role's name at the time
 *   they were written, so a signed letter keeps saying what it said.
 *
 * There is no delete: a role that has ever been assigned is part of the
 * record. Deactivating stops new assignments and leaves history readable.
 */
export default function DeliverySettings() {
  const qc = useQueryClient()
  const [newRole, setNewRole] = useState("")
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState("")

  const { data: roles = [], isLoading } = useQuery({
    queryKey: ["delivery-roles-all"], queryFn: () => getDeliveryRolesApi(true),
  })
  const { data: responsibilities } = useQuery({
    queryKey: ["responsibilities"], queryFn: getResponsibilitiesApi,
  })

  useEffect(() => {
    if (text === null && responsibilities) setText(responsibilities.text)
  }, [responsibilities, text])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["delivery-roles-all"] })
    qc.invalidateQueries({ queryKey: ["delivery-roles"] })
  }
  const onError = (e: any) => setError(e?.response?.data?.detail ?? "Could not save that")

  const create = useMutation({
    mutationFn: () => createDeliveryRoleApi({ name: newRole }),
    onSuccess: () => { setError(""); setNewRole(""); invalidate() },
    onError,
  })
  const update = useMutation({
    mutationFn: updateDeliveryRoleApi, onSuccess: () => { setError(""); invalidate() }, onError,
  })
  const saveText = useMutation({
    mutationFn: () => setResponsibilitiesApi(text ?? ""),
    onSuccess: () => {
      setError("")
      qc.invalidateQueries({ queryKey: ["responsibilities"] })
    },
    onError,
  })

  /** Swap sort_order with the neighbour — seniority is the column, so nothing
   *  else has to know about ordering. */
  const swap = (i: number, j: number) => {
    const a = roles[i], b = roles[j]
    if (!a || !b) return
    update.mutate({ id: a.id, sort_order: b.sort_order })
    update.mutate({ id: b.id, sort_order: a.sort_order })
  }

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Delivery settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          The roles people are assigned in, and what they agree to when accepting a session
        </p>
      </div>

      <section className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">Roles</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Order is seniority — the top one is treated as the lead, including for handing
            out kits. Renaming is safe: signed payment letters keep the wording they were
            written with.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          {roles.map((r, i) => (
            <div key={r.id} className="flex flex-col gap-1.5 p-2.5 border border-border rounded-xl">
              <div className="flex items-center gap-2">
                <input
                  defaultValue={r.name}
                  onBlur={(e) => e.target.value !== r.name &&
                    update.mutate({ id: r.id, name: e.target.value })}
                  className="flex-1 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
                />
                <button
                  disabled={i === 0} onClick={() => swap(i, i - 1)}
                  className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                  aria-label="Move up"
                ><ArrowUp size={14} /></button>
                <button
                  disabled={i === roles.length - 1} onClick={() => swap(i, i + 1)}
                  className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                  aria-label="Move down"
                ><ArrowDown size={14} /></button>
                <button
                  onClick={() => update.mutate({ id: r.id, is_active: !r.is_active })}
                  className={`h-8 px-3 text-xs font-medium rounded-lg border transition-colors ${
                    r.is_active
                      ? "border-border text-muted-foreground hover:bg-muted"
                      : "border-amber-400/40 bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"
                  }`}
                >
                  {r.is_active ? "Active" : "Inactive"}
                </button>
              </div>
              <textarea
                defaultValue={r.description ?? ""}
                placeholder="What an instructor is agreeing to when they pick this role — shown on the invite."
                rows={2}
                onBlur={(e) => e.target.value !== (r.description ?? "") &&
                  update.mutate({ id: r.id, description: e.target.value || null })}
                className="w-full px-2 py-1.5 border border-border bg-background text-foreground rounded-lg text-xs resize-y"
              />
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <input
            placeholder="e.g. Observer" value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            className="flex-1 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm"
          />
          <button
            onClick={() => { setError(""); create.mutate() }}
            disabled={!newRole || create.isPending}
            className="h-9 px-3 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40"
          ><Plus size={14} className="inline mr-1" /> Add role</button>
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">Responsibilities</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Shown on every invite with a read-and-agree tick. Editing this makes a new version:
            anyone who already agreed stays recorded against the wording they actually read.
          </p>
        </div>
        <textarea
          value={text ?? ""} onChange={(e) => setText(e.target.value)} rows={8}
          placeholder="Arrive 30 minutes before the session starts…"
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={() => { setError(""); saveText.mutate() }}
            disabled={saveText.isPending}
            className="h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:opacity-90 disabled:opacity-40"
          >
            {saveText.isPending ? "Saving…" : "Save responsibilities"}
          </button>
          {responsibilities && (
            <span className="text-xs text-muted-foreground">
              {responsibilities.payment_terms_note}
            </span>
          )}
        </div>
      </section>

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
