import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import type { Session } from "@/types/sessions"
import { updateSessionApi } from "@/api/sessions/cohorts"
import { Modal, Field } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"

export function EditSessionModal({
  cohortId,
  session,
  onClose,
  onSaved,
}: {
  cohortId: string
  session: Session
  onClose: () => void
  onSaved?: () => void
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(session.title ?? "")
  const [meetingDate, setMeetingDate] = useState(session.meeting_date ?? "")
  const [startsAt, setStartsAt] = useState(session.starts_at ? session.starts_at.slice(0, 5) : "")
  const [price, setPrice] = useState(session.price != null ? String(session.price) : "")
  const [error, setError] = useState("")

  const updateMutation = useMutation({
    mutationFn: () =>
      updateSessionApi(cohortId, session.id, {
        title: title.trim() || null,
        meeting_date: meetingDate,
        starts_at: startsAt || null,
        price: price.trim() ? Number(price) : null,
      }),
    onSuccess: () => {
      toast.success("Session updated")
      queryClient.invalidateQueries({ queryKey: ["cohort-sessions", cohortId] })
      queryClient.invalidateQueries({ queryKey: ["session-detail", cohortId, session.id] })
      onSaved?.()
      onClose()
    },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not update session"),
  })

  return (
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

        <Field label="Price Override (AED, optional)">
          <input
            type="number"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="Leave blank to use program price"
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>

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
  )
}
