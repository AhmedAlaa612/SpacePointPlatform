/** Shared pieces of an instructor's "apply for this" form — used by both
 *  CohortCallCard (a whole cohort's worth of days, one decision) and
 *  AvailableSessions.tsx's single-session card (2026-08-30, replacing two
 *  copies of the same three blocks that had quietly drifted apart: the
 *  single-session one never got the operations process doc §2 support
 *  questions the cohort form gained on 2026-08-24, and its responsibilities
 *  block was a plain always-open text box instead of the collapsible one).
 */
import type { ReactNode } from "react"

export interface RoleOpening {
  role_id: string
  role_name: string
  notes?: string | null
  slots: number
  remaining: number
  amount_aed?: number | null
}

/** The role picker — a radio group before applying, a plain read-out once
 *  `myInterest` is set (the choice is locked in by then). */
export function RoleOpeningsPicker({
  openings, myInterest, roleId, onSelect, groupName,
}: {
  openings: RoleOpening[]
  myInterest: boolean
  roleId: string | null
  onSelect: (roleId: string) => void
  groupName: string
}) {
  if (openings.length === 0) return null
  return (
    <div className="mb-3 flex flex-col gap-1.5">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Role</p>
      {openings.map((o) => {
        const full = o.remaining <= 0
        return (
          <label
            key={o.role_id}
            className={`flex items-start justify-between gap-3 text-sm rounded-lg px-2 py-1.5 -mx-2 transition-colors ${
              !myInterest && !full ? "cursor-pointer hover:bg-muted" : ""
            } ${!myInterest && roleId === o.role_id ? "bg-primary/5 ring-1 ring-primary/20" : ""}`}
          >
            <div className="flex items-start gap-2 min-w-0">
              {!myInterest && (
                <input
                  type="radio" name={groupName} className="mt-1 shrink-0"
                  checked={roleId === o.role_id} disabled={full}
                  onChange={() => onSelect(o.role_id)}
                />
              )}
              <div className="min-w-0">
                <span className="text-foreground">
                  {o.role_name}
                  <span className="text-xs text-muted-foreground">
                    {" "}&middot; {o.remaining > 0 ? `${o.remaining} of ${o.slots} left` : "full — waitlist"}
                  </span>
                </span>
                {o.notes && <p className="text-xs text-muted-foreground italic">{o.notes}</p>}
              </div>
            </div>
            {o.amount_aed != null && (
              <span className="text-sm font-semibold tabular-nums shrink-0">
                AED {o.amount_aed.toLocaleString()}<span className="text-xs font-normal text-muted-foreground">/session</span>
              </span>
            )}
          </label>
        )
      })}
    </div>
  )
}

/** Operations process doc §2 — the same three questions on every apply form,
 *  whichever shape the offer being applied to is. `needs_ops_support` has no
 *  control here on purpose: nothing in the product sets it from this form
 *  today (mirrors the cohort form, which has always sent it as `false`). */
export function SupportQuestionsPanel({
  needsTransport, onNeedsTransportChange,
  travelling, onTravellingChange,
  concerns, onConcernsChange,
}: {
  needsTransport: boolean
  onNeedsTransportChange: (v: boolean) => void
  travelling: boolean
  onTravellingChange: (v: boolean) => void
  concerns: string
  onConcernsChange: (v: string) => void
}) {
  return (
    <div className="rounded-xl border border-border bg-background/50 p-3 flex flex-col gap-2">
      <p className="text-xs font-semibold text-foreground">Anything we should know?</p>
      <div className="flex flex-col gap-1.5">
        {([
          ["I need transport", needsTransport, onNeedsTransportChange],
          ["I'm travelling from another city", travelling, onTravellingChange],
        ] as const).map(([label, value, onChange]) => (
          <label key={label} className="flex items-center gap-2 text-xs cursor-pointer select-none">
            <input
              type="checkbox" checked={value}
              onChange={(e) => onChange(e.target.checked)}
              className="rounded text-primary focus:ring-primary border-border bg-background"
            />
            {label}
          </label>
        ))}
      </div>
      <textarea
        className="input min-h-[3rem] resize-y text-xs"
        placeholder="Clarify any constraints or support needed…"
        value={concerns}
        onChange={(e) => onConcernsChange(e.target.value)}
      />
    </div>
  )
}

/** The collapsible "Responsibilities" block — closed by default, forced open
 *  and highlighted amber when a submit attempt is blocked on it. */
export function ResponsibilitiesDetails({
  text, roleName, agreed, onAgreedChange, open, onOpenChange, hasError,
}: {
  text: string
  roleName?: string | null
  agreed: boolean
  onAgreedChange: (v: boolean) => void
  open: boolean
  onOpenChange: (open: boolean) => void
  hasError: boolean
}) {
  return (
    <details
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className={`rounded-xl border transition-colors group ${
        hasError ? "border-amber-500/50 bg-amber-500/5" : "border-border bg-background/50"
      }`}
    >
      <summary className="px-3 py-2.5 flex items-center justify-between text-xs font-semibold text-foreground cursor-pointer select-none list-none">
        <span>Responsibilities{roleName ? ` — ${roleName}` : ""}</span>
        <span className="text-[10px] text-primary group-open:hidden">View responsibilities ▾</span>
        <span className="text-[10px] text-muted-foreground hidden group-open:inline">Hide ▴</span>
      </summary>
      <div className="px-3 pb-3 pt-1 border-t border-border flex flex-col gap-2">
        <p className="text-xs text-muted-foreground whitespace-pre-line max-h-40 overflow-y-auto">{text}</p>
        <label className="flex items-center gap-2 text-xs text-foreground font-medium cursor-pointer select-none pt-1">
          <input
            type="checkbox" checked={agreed}
            onChange={(e) => onAgreedChange(e.target.checked)}
            className="rounded text-primary focus:ring-primary border-border bg-background"
          />
          I agree to the Responsibilities
        </label>
      </div>
    </details>
  )
}

/** The cover-letter textarea + submit button row shared by every apply form. */
export function ApplyFooter({
  note, onNoteChange, ready, pending, pendingLabel, onApply, extra,
}: {
  note: string
  onNoteChange: (v: string) => void
  ready: boolean
  pending: boolean
  pendingLabel: string
  onApply: () => void
  /** Rendered above the cover-letter row — e.g. the "pick a role" hint. */
  extra?: ReactNode
}) {
  return (
    <>
      <div className="flex flex-col sm:flex-row gap-3 items-center">
        <textarea
          className="input flex-1 min-h-[4.5rem] resize-y text-xs sm:text-sm"
          placeholder="Optional cover letter (why you'd like this one)…"
          value={note}
          onChange={(e) => onNoteChange(e.target.value)}
        />
        <button
          type="button"
          disabled={pending}
          onClick={onApply}
          className={`h-11 px-6 rounded-xl text-sm font-semibold shrink-0 transition-all ${
            ready
              ? "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
              : "bg-muted/80 text-muted-foreground border border-border/80 hover:bg-muted hover:text-foreground"
          }`}
        >
          {pending ? pendingLabel : "Register interest"}
        </button>
      </div>
      {extra}
    </>
  )
}
