import { Check, Crown } from "lucide-react"
import {
  ORG_ASSIGNABLE_ROLES,
  ORG_OWNER_EXTRA_ROLES,
  type OrgSandboxRole,
} from "@/api/websiteEvents"
import { cn } from "@/lib/utils"

interface OrgRoleToggleRowProps {
  isOwner: boolean
  roles: OrgSandboxRole[]
  disabled?: boolean
  compact?: boolean
  onChange: (nextRoles: OrgSandboxRole[]) => void
}

export function OrgRoleToggleRow({
  isOwner,
  roles,
  disabled = false,
  compact = false,
  onChange,
}: OrgRoleToggleRowProps) {
  const toggleRole = (role: Exclude<OrgSandboxRole, "owner">) => {
    const has = roles.includes(role)
    if (isOwner) {
      const next = has ? roles.filter((r) => r !== role) : [...roles, role]
      const ordered = (["owner", "instructor", "judge", "observer"] as const).filter(
        (r) => r === "owner" || next.includes(r),
      )
      onChange(ordered)
      return
    }
    if (has && roles.length <= 1) return
    const next = has ? roles.filter((r) => r !== role) : [...roles, role]
    const ordered = ORG_ASSIGNABLE_ROLES.map((r) => r.value).filter((r) => next.includes(r))
    if (ordered.length > 0) onChange(ordered)
  }

  const options = isOwner ? ORG_OWNER_EXTRA_ROLES : ORG_ASSIGNABLE_ROLES

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {isOwner && (
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/15 font-semibold text-amber-700 dark:text-amber-300",
            compact ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-0.5 text-[11px]",
          )}
          title="Primary Owner is permanent and includes Coordinator access"
        >
          <Crown className="h-2.5 w-2.5" /> {compact ? "Owner" : "Primary Owner"}
        </span>
      )}
      {options.map((role) => {
        const active = roles.includes(role.value)
        const lastNonOwnerRole = !isOwner && active && roles.length <= 1
        return (
          <button
            key={role.value}
            type="button"
            disabled={disabled || lastNonOwnerRole}
            onClick={() => toggleRole(role.value)}
            title={
              lastNonOwnerRole
                ? "Members must keep at least one role"
                : `${active ? "Remove" : "Grant"} ${role.label} role — ${role.hint}`
            }
            className={cn(
              "inline-flex items-center gap-1 rounded-full border font-semibold transition",
              compact ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-0.5 text-[11px]",
              active
                ? "border-primary/40 bg-primary/15 text-primary hover:bg-primary/20"
                : "border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground",
              (disabled || lastNonOwnerRole) && "cursor-not-allowed opacity-70",
            )}
          >
            {active && <Check className="h-2.5 w-2.5" />}
            <span>{isOwner && !compact ? `+ ${role.label}` : role.label}</span>
          </button>
        )
      })}
    </div>
  )
}

interface OrgRolePickerGridProps {
  value: Exclude<OrgSandboxRole, "owner">[]
  onChange: (next: Exclude<OrgSandboxRole, "owner">[]) => void
}

export function OrgRolePickerGrid({ value, onChange }: OrgRolePickerGridProps) {
  const toggle = (role: Exclude<OrgSandboxRole, "owner">) => {
    const has = value.includes(role)
    if (has && value.length <= 1) return
    const next = has ? value.filter((r) => r !== role) : [...value, role]
    const ordered = ORG_ASSIGNABLE_ROLES.map((r) => r.value).filter((r) => next.includes(r))
    if (ordered.length > 0) onChange(ordered)
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {ORG_ASSIGNABLE_ROLES.map((role) => {
        const selected = value.includes(role.value)
        const lockedLast = selected && value.length <= 1
        return (
          <button
            key={role.value}
            type="button"
            disabled={lockedLast}
            onClick={() => toggle(role.value)}
            className={cn(
              "flex flex-col items-start gap-1 rounded-xl border p-2.5 text-left transition",
              selected
                ? "border-primary bg-primary/10 text-foreground"
                : "border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground",
              lockedLast && "cursor-not-allowed",
            )}
          >
            <div className="flex w-full items-center justify-between gap-2">
              <span className="text-xs font-semibold text-foreground">{role.label}</span>
              <span
                className={cn(
                  "flex h-4 w-4 items-center justify-center rounded border",
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-card",
                )}
              >
                {selected && <Check className="h-3 w-3" />}
              </span>
            </div>
            <span className="text-[11px] leading-snug text-muted-foreground">{role.hint}</span>
          </button>
        )
      })}
    </div>
  )
}

