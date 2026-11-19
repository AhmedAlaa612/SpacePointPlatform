import { useEffect, useState } from "react"
import { MessageSquare } from "lucide-react"

interface ChecklistJustificationProps {
  note: string | null | undefined
  locked?: boolean
  pending?: boolean
  onSave: (note: string) => void | Promise<unknown>
}

/** Inline justification comment display/editor for instructor and internal
 *  session checklists. */
export function ChecklistJustification({
  note,
  locked = false,
  pending = false,
  onSave,
}: ChecklistJustificationProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(note ?? "")

  useEffect(() => {
    if (!editing) setDraft(note ?? "")
  }, [note, editing])

  const submit = async (next: string) => {
    try {
      await onSave(next)
      setEditing(false)
    } catch {
      // Error surfaced by caller's mutation onError handler.
    }
  }

  const trimmedDraft = draft.trim()
  const trimmedNote = (note ?? "").trim()
  const canSave = Boolean(trimmedDraft) && trimmedDraft !== trimmedNote

  if (editing) {
    return (
      <div className="mt-1.5 flex flex-col gap-1.5 min-w-0">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          placeholder="Add justification…"
          className="w-full min-w-0 px-2.5 py-1.5 text-xs border border-border bg-background text-foreground rounded-lg focus:outline-none focus:border-primary resize-y"
        />
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            disabled={pending || !canSave}
            onClick={() => void submit(draft)}
            className="h-7 px-2.5 rounded-md bg-primary text-primary-foreground text-[11px] font-medium hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            {pending ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => {
              setDraft(note ?? "")
              setEditing(false)
            }}
            className="h-7 px-2.5 rounded-md border border-border text-[11px] text-muted-foreground hover:text-foreground cursor-pointer"
          >
            Cancel
          </button>
          {note && (
            <button
              type="button"
              disabled={pending}
              onClick={() => void submit("")}
              className="h-7 px-2 text-[11px] text-red-500 hover:underline ml-auto cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>
      </div>
    )
  }

  if (note) {
    return (
      <div className="mt-1.5 flex items-start justify-between gap-2 rounded-lg bg-muted/40 border border-border/60 px-2.5 py-1.5 text-xs min-w-0">
        <p className="text-muted-foreground whitespace-pre-wrap [overflow-wrap:anywhere] min-w-0">
          <span className="font-medium text-foreground">Justification:</span> {note}
        </p>
        {!locked && (
          <button
            type="button"
            onClick={() => {
              setDraft(note)
              setEditing(true)
            }}
            className="text-[11px] text-primary hover:underline shrink-0 cursor-pointer"
          >
            Edit
          </button>
        )}
      </div>
    )
  }

  if (locked) return null

  return (
    <button
      type="button"
      onClick={() => {
        setDraft("")
        setEditing(true)
      }}
      className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors w-fit cursor-pointer"
    >
      <MessageSquare size={11} /> Add justification
    </button>
  )
}
