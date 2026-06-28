import { X } from "lucide-react"

export { Spinner } from "@/components/ui/primitives"

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-6 flex flex-col gap-4 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <p className="text-base font-semibold text-foreground">{title}</p>
          <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
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
