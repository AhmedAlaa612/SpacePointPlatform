import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import type { Session } from "@/types/sessions"
import { updateSessionApi } from "@/api/sessions/cohorts"
import { getLocationsApi } from "@/api/inventory"
import { Modal, Field } from "@/pages/admin/components/common"
import { QuickCreateLocationModal } from "@/pages/admin/components/QuickCreateLocationModal"
import { useToast } from "@/components/ui/toast"

export function EditSessionModal({
  cohortId,
  session,
  onClose,
  onSaved,
  canEditDuration = true,
  hideLogistics: _hideLogistics = false,
}: {
  cohortId: string
  session: Session
  onClose: () => void
  onSaved?: () => void
  canEditDuration?: boolean
  hideLogistics?: boolean
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(session.title ?? "")
  const [meetingDate, setMeetingDate] = useState(session.meeting_date ?? "")
  const [startsAt, setStartsAt] = useState(session.starts_at ? session.starts_at.slice(0, 5) : "")
  const [durationHours, setDurationHours] = useState(session.duration_hours != null ? String(session.duration_hours) : "")
  const [locationId, setLocationId] = useState(session.location_id ?? "")
  const [newLocOpen, setNewLocOpen] = useState(false)
  const [error, setError] = useState("")

  const { data: locations = [] } = useQuery({
    queryKey: ["locations"],
    queryFn: () => getLocationsApi(false),
  })

  const updateMutation = useMutation({
    mutationFn: () => {
      const payload: Parameters<typeof updateSessionApi>[2] = {
        title: title.trim() || null,
        meeting_date: meetingDate,
        starts_at: startsAt || null,
      }
      if (locationId !== (session.location_id ?? "")) {
        payload.location_id = locationId || null
      }
      if (canEditDuration) {
        payload.duration_hours = durationHours.trim() ? Number(durationHours) : null
      }
      return updateSessionApi(cohortId, session.id, payload)
    },
    onSuccess: () => {
      toast.success("Session updated")
      queryClient.invalidateQueries({ queryKey: ["cohort-sessions", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["session-detail", cohortId, session.id] })
      onSaved?.()
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not update session"),
  })

  const currentLocMissing =
    Boolean(locationId) && !locations.some((loc) => loc.id === locationId)

  return (
    <>
    <Modal title="Edit Session" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          updateMutation.mutate()
        }}
        className="flex flex-col gap-4"
      >
        <Field label="Session Title">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Intro to Orbits / Workshop Day 1"
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Meeting Date">
            <input
              type="date"
              required
              value={meetingDate}
              onChange={(e) => setMeetingDate(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Start Time">
            <input
              type="time"
              value={startsAt}
              onChange={(e) => setStartsAt(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>

        <Field label="Location Override (optional)">
          <div className="flex items-center gap-2">
            <select
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              className="flex-1 h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            >
              <option value="">Inherit from cohort</option>
              {currentLocMissing && (
                <option value={locationId}>
                  {session.effective_location_name ?? "Current session venue"}
                </option>
              )}
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name}{loc.city_name ? ` — ${loc.city_name}` : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setNewLocOpen(true)}
              className="h-10 px-2.5 inline-flex items-center gap-1 rounded-xl border border-border bg-background text-xs font-medium hover:bg-muted transition-colors shrink-0"
            >
              <Plus size={13} /> New
            </button>
          </div>
        </Field>

        {canEditDuration && (
          <Field label="Duration Override (hours, optional)">
            <input
              type="number" step="0.5" min="0"
              value={durationHours}
              onChange={(e) => setDurationHours(e.target.value)}
              placeholder="Leave blank to use the cohort's duration"
              className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        )}

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={updateMutation.isPending}
            className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
          >
            {updateMutation.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
    {newLocOpen && (
      <QuickCreateLocationModal
        onClose={() => setNewLocOpen(false)}
        onCreated={(loc) => setLocationId(loc.id)}
      />
    )}
    </>
  )
}
