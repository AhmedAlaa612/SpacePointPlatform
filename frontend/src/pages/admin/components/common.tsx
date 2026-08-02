import { X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Dialog, DialogClose, DialogContent, DialogTitle } from "@/components/ui/dialog"

export { Spinner, PageHeader, EmptyState } from "@/components/ui/primitives"

export function Modal({ title, onClose, children, maxWidth = "sm:max-w-lg max-w-lg" }: { title: string; onClose: () => void; children: React.ReactNode; maxWidth?: string }) {
  // Radix Dialog underneath (previously a hand-rolled portal): gets us
  // Escape-to-close, backdrop-click-to-close, a focus trap and proper
  // role="dialog"/aria wiring for free, app-wide, from this one file.
  // Callers already only ever conditionally render <Modal>, so `open` is
  // always true while mounted — closing happens by the parent unmounting us.
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent
        showCloseButton={false}
        className={cn(
          "w-full flex flex-col gap-4 bg-card border border-border rounded-2xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto text-sm text-foreground",
          maxWidth,
        )}
      >
        <div className="flex items-center justify-between">
          <DialogTitle className="text-base font-semibold text-foreground">{title}</DialogTitle>
          <DialogClose asChild>
            <button className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
              <X size={16} />
            </button>
          </DialogClose>
        </div>
        {children}
      </DialogContent>
    </Dialog>
  )
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">{label}</label>
      {children}
    </div>
  )
}

/** Generalizes the delete-registration confirm pattern: a Modal with a
 *  description, optional extra content (e.g. a checkbox), and a Cancel /
 *  destructive-or-primary Confirm pair — for replacing native confirm(). */
export function ConfirmDialog({ title, description, confirmLabel = "Confirm", cancelLabel = "Cancel", destructive = false, pending = false, error, onCancel, onConfirm, children }: {
  title: string
  description?: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  pending?: boolean
  error?: string | null
  onCancel: () => void
  onConfirm: () => void
  children?: React.ReactNode
}) {
  return (
    <Modal title={title} onClose={onCancel} maxWidth="max-w-md">
      <div className="flex flex-col gap-4">
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
        {children}
        {error && (
          <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={pending}
            className={`h-9 px-4 rounded-xl text-sm font-medium transition-colors disabled:opacity-50 ${
              destructive ? "bg-red-600 text-white hover:opacity-90" : "bg-primary text-primary-foreground hover:opacity-90"
            }`}
          >
            {pending ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  )
}

export function ModalActions({ onCancel, onConfirm, loading, disabled, label }: {
  onCancel: () => void; onConfirm: () => void; loading: boolean; disabled: boolean; label: string
}) {
  return (
    <div className="flex gap-2 mt-1">
      <button onClick={onCancel}
        className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
        Cancel
      </button>
      <button onClick={onConfirm} disabled={disabled || loading}
        className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50">
        {loading ? "…" : label}
      </button>
    </div>
  )
}
