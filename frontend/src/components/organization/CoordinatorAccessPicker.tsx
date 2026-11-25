import { useQuery } from "@tanstack/react-query"
import { getOrgCoordinatorsApi } from "@/api/organizationPrograms"

interface CoordinatorAccessPickerProps {
  organizationId?: string | null
  mode: "general" | "assigned"
  onModeChange: (next: "general" | "assigned") => void
  selectedUserIds: string[]
  onSelectedUserIdsChange: (next: string[]) => void
  disabled?: boolean
}

export function CoordinatorAccessPicker({
  organizationId,
  mode,
  onModeChange,
  selectedUserIds,
  onSelectedUserIdsChange,
  disabled = false,
}: CoordinatorAccessPickerProps) {
  const { data: coordinators = [] } = useQuery({
    queryKey: ["org-coordinators", organizationId ?? "me"],
    queryFn: () => getOrgCoordinatorsApi(organizationId ?? undefined),
  })

  const toggleId = (id: string) => {
    if (disabled) return
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
                const checked = selectedUserIds.includes(c.id)
                return (
                  <label
                    key={c.id}
                    className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-xs cursor-pointer transition ${
                      checked
                        ? "border-primary/50 bg-primary/10 text-foreground"
                        : "border-border bg-background text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
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
