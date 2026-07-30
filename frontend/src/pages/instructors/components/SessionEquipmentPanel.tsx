import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Backpack, Plus, Search, X } from "lucide-react"
import {
  getLocationsApi,
  getSessionEquipmentApi,
  returnEquipmentApi,
  searchEquipmentApi,
  takeEquipmentApi,
  type EquipmentSearchResult,
} from "@/api/inventory"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"

/**
 * Non-kit equipment an instructor takes to a session (I2-7) — a mic speaker,
 * a battery charger, a roll of stickers, a bag of T-shirts.
 *
 * Today this is WhatsApp photos and never reaches a system. Three things make
 * the difference between a form that gets filled in and one that doesn't:
 *
 * - **It starts empty, with a search box.** A co-working space may hold forty
 *   item types and most sessions take nothing extra. Scrolling forty rows on a
 *   phone to tick two is exactly how a form stops being filled.
 * - **Nobody is asked where they collected from.** Ops moves the kits to the
 *   session's warehouse first, so the kits' location already *is* the
 *   collection point. The dropdown appears only when there is nothing to
 *   derive from — no kits, or kits in more than one place.
 * - **"Returning later" is a real answer**, recorded as the line staying
 *   outstanding rather than as a state nobody will come back and correct.
 *
 * Unlike the kits panel this renders even with nothing taken, because taking
 * something is the action being offered. It stays one collapsed line until
 * there is something to show.
 */
export function SessionEquipmentPanel({
  sessionId,
  onChanged,
}: {
  sessionId: string
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [returning, setReturning] = useState(false)

  const { data } = useQuery({
    queryKey: ["session-equipment", sessionId],
    queryFn: () => getSessionEquipmentApi(sessionId),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["session-equipment", sessionId] })
    onChanged()
  }

  if (!data) return null

  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Backpack size={15} /> Anything else you took?
          </p>
          {data.outstanding_count > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
              {data.outstanding_count} still out
            </span>
          )}
        </div>

        {data.lines.length === 0 ? (
          <p className="text-xs text-muted-foreground -mt-1">
            Stickers, a speaker, a charger, T-shirts — anything that isn&apos;t a kit.
            {data.location_name && ` Picked up from ${data.location_name}.`}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {data.lines.map((line) => (
              <div
                key={line.item_id}
                className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/50 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{line.item_name}</p>
                  <p className="text-xs text-muted-foreground">
                    Took {line.qty_taken}
                    {line.qty_returned > 0 && ` · brought back ${line.qty_returned}`}
                  </p>
                </div>
                <span className="text-xs shrink-0 font-medium">
                  {line.outstanding > 0 ? (
                    <span className="text-amber-700 dark:text-amber-400">
                      {line.outstanding} with you
                    </span>
                  ) : (
                    <span className="text-emerald-600 dark:text-emerald-400">All back</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus size={14} className="mr-1.5" /> Add something
          </Button>
          {data.outstanding_count > 0 && (
            <Button size="sm" variant="outline" onClick={() => setReturning(true)}>
              Bring it back
            </Button>
          )}
        </div>
      </CardContent>

      {adding && (
        <TakeModal
          sessionId={sessionId}
          locationId={data.location_id}
          locationName={data.location_name}
          onClose={() => setAdding(false)}
          onDone={() => { setAdding(false); refresh() }}
        />
      )}
      {returning && (
        <ReturnModal
          sessionId={sessionId}
          lines={data.lines.filter((l) => l.outstanding > 0)}
          locationId={data.location_id}
          locationName={data.location_name}
          onClose={() => setReturning(false)}
          onDone={() => { setReturning(false); refresh() }}
        />
      )}
    </Card>
  )
}

/** Search first, always. The list of what's on the shelf is never rendered
 *  unprompted — see the panel docblock. */
function TakeModal({ sessionId, locationId, locationName, onClose, onDone }: {
  sessionId: string
  locationId: string | null
  locationName: string | null
  onClose: () => void
  onDone: () => void
}) {
  const [q, setQ] = useState("")
  const [picked, setPicked] = useState<Record<string, { row: EquipmentSearchResult; qty: number }>>({})
  const [chosenLocation, setChosenLocation] = useState("")
  const [error, setError] = useState("")

  // Only asked when there was nothing to derive from — the uncommon path.
  const needsLocation = locationId === null
  const effectiveLocation = locationId ?? (chosenLocation || null)

  const { data: locations = [] } = useQuery({
    queryKey: ["inv-locations"],
    queryFn: () => getLocationsApi(),
    enabled: needsLocation,
  })

  const { data: results = [], isFetching } = useQuery({
    queryKey: ["equipment-search", sessionId, q, effectiveLocation],
    queryFn: () => searchEquipmentApi({ sessionId, q, locationId: effectiveLocation }),
    enabled: q.trim().length >= 2 && !!effectiveLocation,
  })

  const submit = useMutation({
    mutationFn: takeEquipmentApi,
    onSuccess: onDone,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record that"),
  })

  const chosen = Object.values(picked)

  return (
    <Modal title="What else did you take?" onClose={onClose} maxWidth="max-w-md">
      {needsLocation ? (
        <Field label="Where did you collect it from?">
          <select
            value={chosenLocation}
            onChange={(e) => { setChosenLocation(e.target.value); setPicked({}) }}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          >
            <option value="">Choose…</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </Field>
      ) : (
        <p className="text-xs text-muted-foreground -mt-1">
          From {locationName}, where this session&apos;s kits are.
        </p>
      )}

      <Field label="Search for it">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="speaker, charger, stickers…"
            disabled={!effectiveLocation}
            className="w-full h-10 pl-9 pr-3 border border-border bg-background text-foreground rounded-xl text-sm disabled:opacity-50"
          />
        </div>
      </Field>

      {q.trim().length >= 2 && effectiveLocation && (
        <div className="flex flex-col gap-1 max-h-[30vh] overflow-y-auto">
          {results.map((row) => (
            <button
              key={row.item_id}
              onClick={() =>
                setPicked((p) => ({
                  ...p,
                  [row.item_id]: { row, qty: p[row.item_id]?.qty ?? 1 },
                }))
              }
              className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-left hover:bg-muted/60"
            >
              <span className="text-sm text-foreground truncate">{row.item_name}</span>
              <span className="text-xs text-muted-foreground shrink-0">{row.available} there</span>
            </button>
          ))}
          {results.length === 0 && !isFetching && (
            <p className="text-sm text-muted-foreground py-2">
              Nothing matching that is on record here. Ask operations to add it.
            </p>
          )}
        </div>
      )}

      {chosen.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t border-border pt-3">
          {chosen.map(({ row, qty }) => (
            <div key={row.item_id} className="flex items-center justify-between gap-3">
              <span className="text-sm text-foreground truncate">{row.item_name}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                <input
                  type="number" min={1} max={row.available} value={qty}
                  onChange={(e) =>
                    setPicked((p) => ({
                      ...p,
                      [row.item_id]: {
                        row,
                        qty: Math.min(row.available, Math.max(1, Number(e.target.value) || 1)),
                      },
                    }))
                  }
                  className="w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
                />
                <button
                  onClick={() =>
                    setPicked((p) => {
                      const { [row.item_id]: _drop, ...rest } = p
                      return rest
                    })
                  }
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`Remove ${row.item_name}`}
                >
                  <X size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          submit.mutate({
            sessionId,
            locationId: effectiveLocation,
            lines: chosen.map(({ row, qty }) => ({ item_id: row.item_id, qty })),
          })
        }}
        loading={submit.isPending}
        disabled={chosen.length === 0}
        label="Record it"
      />
    </Modal>
  )
}

/** "Did you bring it back?" per line. Leaving a line at zero is the
 *  "returning later" answer — it stays outstanding, which is the truth. */
function ReturnModal({ sessionId, lines, locationId, locationName, onClose, onDone }: {
  sessionId: string
  lines: { item_id: string; item_name: string; outstanding: number }[]
  locationId: string | null
  locationName: string | null
  onClose: () => void
  onDone: () => void
}) {
  const [qtys, setQtys] = useState<Record<string, number>>(
    Object.fromEntries(lines.map((l) => [l.item_id, l.outstanding])),
  )
  const [chosenLocation, setChosenLocation] = useState("")
  const [error, setError] = useState("")

  const needsLocation = locationId === null
  const effectiveLocation = locationId ?? (chosenLocation || null)

  const { data: locations = [] } = useQuery({
    queryKey: ["inv-locations"],
    queryFn: () => getLocationsApi(),
    enabled: needsLocation,
  })

  const submit = useMutation({
    mutationFn: returnEquipmentApi,
    onSuccess: onDone,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Could not record the return"),
  })

  const returning = lines
    .map((l) => ({ item_id: l.item_id, qty: qtys[l.item_id] ?? 0 }))
    .filter((l) => l.qty > 0)

  return (
    <Modal title="Did you bring it back?" onClose={onClose} maxWidth="max-w-md">
      <p className="text-xs text-muted-foreground -mt-1">
        Set anything you still have to zero — it stays on your list rather than being
        recorded as returned.
      </p>

      {needsLocation && (
        <Field label="Where are you leaving it?">
          <select
            value={chosenLocation} onChange={(e) => setChosenLocation(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm"
          >
            <option value="">Choose…</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </Field>
      )}

      <div className="flex flex-col gap-1.5">
        {lines.map((l) => (
          <div key={l.item_id} className="flex items-center justify-between gap-3">
            <span className="text-sm text-foreground truncate">
              {l.item_name}
              <span className="text-xs text-muted-foreground"> / {l.outstanding}</span>
            </span>
            <input
              type="number" min={0} max={l.outstanding} value={qtys[l.item_id] ?? 0}
              onChange={(e) =>
                setQtys((q) => ({
                  ...q,
                  [l.item_id]: Math.min(l.outstanding, Math.max(0, Number(e.target.value) || 0)),
                }))
              }
              className="w-16 h-9 px-2 border border-border bg-background text-foreground rounded-lg text-sm text-right tabular-nums"
            />
          </div>
        ))}
      </div>

      {!needsLocation && (
        <p className="text-xs text-muted-foreground">Going back to {locationName}.</p>
      )}
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => {
          setError("")
          submit.mutate({ sessionId, lines: returning, toLocationId: effectiveLocation })
        }}
        loading={submit.isPending}
        disabled={returning.length === 0 || !effectiveLocation}
        label="Record it"
      />
    </Modal>
  )
}
