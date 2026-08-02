import * as React from "react"
import { Toast as ToastPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { HugeiconsIcon } from "@hugeicons/react"
import { Cancel01Icon } from "@hugeicons/core-free-icons"

type ToastVariant = "success" | "error"
type ToastItem = { id: number; message: string; variant: ToastVariant }

const ToastContext = React.createContext<{
  success: (message: string) => void
  error: (message: string) => void
} | null>(null)

let nextId = 0

/** Mount once, near the app root (see main.tsx) — every useToast() caller
 *  underneath shares this one queue/viewport. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([])

  const push = React.useCallback((variant: ToastVariant, message: string) => {
    setItems((prev) => [...prev, { id: nextId++, message, variant }])
  }, [])

  // Delay the state removal past onOpenChange(false) so the data-closed
  // exit transition has time to play instead of the toast just vanishing.
  const dismiss = React.useCallback((id: number) => {
    setTimeout(() => setItems((prev) => prev.filter((i) => i.id !== id)), 150)
  }, [])

  const api = React.useMemo(
    () => ({
      success: (message: string) => push("success", message),
      error: (message: string) => push("error", message),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={api}>
      <ToastPrimitive.Provider swipeDirection="right" duration={4000}>
        {children}
        {items.map((item) => (
          <ToastPrimitive.Root
            key={item.id}
            onOpenChange={(open) => { if (!open) dismiss(item.id) }}
            className={cn(
              "flex items-center justify-between gap-3 rounded-2xl bg-popover/95 backdrop-blur-2xl p-3 pl-4 text-xs/relaxed shadow-2xl ring-1 data-open:animate-in data-open:slide-in-from-bottom-2 data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0 data-swipe-end:animate-out",
              item.variant === "success" ? "ring-emerald-500/30" : "ring-red-500/30",
            )}
          >
            <ToastPrimitive.Description
              className={cn(
                "font-medium",
                item.variant === "success" ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400",
              )}
            >
              {item.message}
            </ToastPrimitive.Description>
            <ToastPrimitive.Close asChild>
              <Button variant="ghost" size="icon-sm">
                <HugeiconsIcon icon={Cancel01Icon} strokeWidth={2} />
                <span className="sr-only">Dismiss</span>
              </Button>
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed bottom-0 right-0 z-[100] flex w-full max-w-sm flex-col gap-2 p-4 outline-none sm:bottom-4 sm:right-4" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = React.useContext(ToastContext)
  if (!ctx) throw new Error("useToast must be used within a ToastProvider")
  return ctx
}
