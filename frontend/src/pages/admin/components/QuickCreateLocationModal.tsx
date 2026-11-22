import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MapPin, X } from "lucide-react"

import { createLocationApi, getCitiesApi } from "@/api/inventory"
import type { Location } from "@/types/inventory"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"

interface Props {
  onClose: () => void
  onCreated: (location: Location) => void
}

export function QuickCreateLocationModal({ onClose, onCreated }: Props) {
  const qc = useQueryClient()
  const toast = useToast()

  const { data: cities = [], isLoading: loadingCities } = useQuery({
    queryKey: ["cities"],
    queryFn: () => getCitiesApi(false),
  })

  const [name, setName] = useState("")
  const [cityId, setCityId] = useState("")
  const [address, setAddress] = useState("")
  const [mapsUrl, setMapsUrl] = useState("")
  const [notes, setNotes] = useState("")

  const mut = useMutation({
    mutationFn: () =>
      createLocationApi({
        name: name.trim(),
        city_id: cityId,
        address: address.trim() || null,
        maps_url: mapsUrl.trim() || null,
        notes: notes.trim() || undefined,
      }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["locations"] })
      qc.invalidateQueries({ queryKey: ["inv-locations"] })
      toast.success(`Location added: ${created.name}`)
      onCreated(created)
      onClose()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Couldn't create location")
    },
  })

  const canSubmit = name.trim().length > 0 && cityId.length > 0 && !mut.isPending

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-border bg-background shadow-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <MapPin size={16} className="text-primary" />
            <h2 className="text-sm font-semibold">New Location</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (canSubmit) mut.mutate()
          }}
          className="p-5 space-y-3.5"
        >
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Location Name <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Innovation Lab — Room 204"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              City <span className="text-destructive">*</span>
            </label>
            <select
              required
              value={cityId}
              onChange={(e) => setCityId(e.target.value)}
              disabled={loadingCities}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="">{loadingCities ? "Loading cities..." : "Select a city"}</option>
              {cities.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.country})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Street Address / Directions
            </label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Optional building, floor or room notes"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Maps URL
            </label>
            <input
              type="url"
              value={mapsUrl}
              onChange={(e) => setMapsUrl(e.target.value)}
              placeholder="https://maps.google.com/..."
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Notes
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optional entry/parking notes"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!canSubmit}>
              {mut.isPending ? "Saving..." : "Create Location"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
