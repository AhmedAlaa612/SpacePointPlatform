import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { UserCog, Users, X } from "lucide-react"
import { getOrgCoordinatorsApi } from "@/api/organizationPrograms"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"
import { getErrorMessage } from "@/lib/utils"

interface CoordinatorAccessPickerProps {
  organizationId?: string | null
  mode: "general" | "assigned"
  onModeChange: (next: "general" | "assigned") => void
  selectedUserIds: string[]
  onSelectedUserIdsChange: (next: string[]) => void
  disabled?: boolean
  lockedUserId?: string | null
}

export function CoordinatorAccessBadge({
  mode,
  coordinators,
}: {
  mode?: "general" | "assigned" | string | null
  coordinators?: { id: string; full_name: string }[] | null
}) {
  const isAssigned = mode === "assigned"
  const list = coordinators ?? []
  const names = list.map((c) => c.full_name).filter(Boolean)
  const title = isAssigned
    ? names.length > 0
      ? `Assigned coordinators: ${names.join(", ")}`
      : "Assigned coordinators only (Organization owner only)"
    : "Shared with all coordinators in this organization"

  if (isAssigned) {
    return (
      <span
        title={title}
        className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-600 dark:text-indigo-300 border border-indigo-500/30 inline-flex items-center gap-1"
      >
        <UserCog className="w-2.5 h-2.5 shrink-0" />
        Assigned ({list.length})
      </span>
    )
  }
  return (
    <span
      title={title}
      className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border inline-flex items-center gap-1"
    >
      <Users className="w-2.5 h-2.5 shrink-0" />
      All coordinators
    </span>
  )
}

export function CoordinatorAccessPicker({
  organizationId,
  mode,
  onModeChange,
  selectedUserIds,
  onSelectedUserIdsChange,
  disabled = false,
  lockedUserId = null,
}: CoordinatorAccessPickerProps) {
  const { data: coordinators = [] } = useQuery({
    queryKey: ["org-coordinators", organizationId ?? "me"],
    queryFn: () => getOrgCoordinatorsApi(organizationId ?? undefined),
  })

  const toggleId = (id: string) => {
    if (disabled || (lockedUserId && id === lockedUserId)) return
    onSelectedUserIdsChange(
      selectedUserIds.includes(id)
        ? selectedUserIds.filter((x) => x !== id)
        : [...selectedUserIds, id],
    )
  }

  return (
    <div className="rounded-xl border border-border bg-muted/20 p-3 space-y-2.5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <span className="text-xs font-semibold text-foreground block">
            Coordinator Access
          </span>
          <span className="text-[11px] text-muted-foreground block">
            Control which organization coordinators can see and manage this cohort.
          </span>
        </div>
        <select
          value={mode}
          disabled={disabled}
          onChange={(e) => onModeChange(e.target.value as "general" | "assigned")}
          className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs font-medium text-foreground cursor-pointer disabled:opacity-60"
        >
          <option value="general">All Coordinators (General)</option>
          <option value="assigned">Assigned Coordinators Only</option>
        </select>
      </div>

      {mode === "assigned" && (
        <div className="space-y-1.5 pt-1 border-t border-border/60">
          <span className="text-[11px] font-medium text-muted-foreground block">
            Select coordinators who can access this cohort (org owner always has access):
          </span>
          {coordinators.length === 0 ? (
            <p className="text-[11px] text-muted-foreground italic">
              No coordinators found in this organization yet.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-36 overflow-y-auto pr-1">
              {coordinators.map((c) => {
                const isSelfLocked = Boolean(lockedUserId && c.id === lockedUserId)
                const checked = selectedUserIds.includes(c.id) || isSelfLocked
                return (
                  <label
                    key={c.id}
                    className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs transition ${
                      isSelfLocked ? "cursor-default opacity-80" : "cursor-pointer"
                    } ${
                      checked
                        ? "border-primary/50 bg-primary/10 text-foreground"
                        : "border-border bg-background text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled || isSelfLocked}
                      onChange={() => toggleId(c.id)}
                      className="rounded border-border text-primary"
                    />
                    <span className="truncate">
                      {c.full_name}
                      {c.is_owner ? " (Owner)" : ""}
                    </span>
                  </label>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function CohortCoordinatorsModal({
  cohort,
  organizationId,
  onSave,
  onClose,
  onSaved,
}: {
  cohort: {
    id: string
    name: string
    coordinator_access_mode?: "general" | "assigned" | string | null
    coordinators?: { id: string; full_name: string; email?: string }[] | null
  }
  organizationId?: string | null
  onSave: (payload: {
    coordinator_access_mode: "general" | "assigned"
    coordinator_user_ids: string[]
  }) => Promise<unknown>
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const { user, activeRole, activeOrgRole } = useAuth()
  const lockedUserId =
    activeRole === "organization" && activeOrgRole === "coordinator" ? (user?.id ?? null) : null
  const [mode, setMode] = useState<"general" | "assigned">(
    cohort.coordinator_access_mode === "assigned" ? "assigned" : "general",
  )
  const [userIds, setUserIds] = useState<string[]>(() => {
    const base = (cohort.coordinators ?? []).map((c) => c.id)
    return lockedUserId && !base.includes(lockedUserId) ? [...base, lockedUserId] : base
  })

  const mut = useMutation({
    mutationFn: () =>
      onSave({
        coordinator_access_mode: mode,
        coordinator_user_ids: mode === "assigned" ? userIds : [],
      }),
    onSuccess: () => {
      toast.success(`Updated coordinator access for "${cohort.name}"`)
      onSaved()
      onClose()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to update coordinator access")),
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div>
            <h2 className="text-base font-bold text-foreground">Cohort Coordinator Access</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Choose whether <strong className="text-foreground">{cohort.name}</strong> is shared with all coordinators or assigned to specific coordinators.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <CoordinatorAccessPicker
          organizationId={organizationId}
          mode={mode}
          onModeChange={setMode}
          selectedUserIds={userIds}
          onSelectedUserIdsChange={setUserIds}
          lockedUserId={lockedUserId}
        />

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" size="sm" disabled={mut.isPending} onClick={() => mut.mutate()}>
            {mut.isPending ? "Saving..." : "Save Coordinators"}
          </Button>
        </div>
      </div>
    </div>
  )
}
