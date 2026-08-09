import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { MapPin } from "lucide-react"
import { listAdminInstructorsApi } from "@/api/instructors/admin"
import { UserProfileModal } from "@/components/UserProfileModal"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function InstructorsAdminInstructors() {
  const { data: instructors, isLoading } = useQuery({ queryKey: ["admin-instructors"], queryFn: listAdminInstructorsApi })
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [cityId, setCityId] = useState("")
  const [deliverCityId, setDeliverCityId] = useState("")

  // Options come from the loaded rows rather than /public/cities: the point of
  // these filters is to narrow THIS list, so offering cities no instructor is
  // in would only produce guaranteed-empty results.
  const { cityOptions, deliverOptions } = useMemo(() => {
    const cities = new Map<string, string>()
    const deliver = new Map<string, string>()
    for (const i of instructors ?? []) {
      if (i.city_id && i.city_name) cities.set(i.city_id, i.city_name)
      i.deliver_city_ids.forEach((id, idx) => deliver.set(id, i.deliver_city_names[idx]))
    }
    const byName = (a: [string, string], b: [string, string]) => a[1].localeCompare(b[1])
    return {
      cityOptions: [...cities.entries()].sort(byName),
      deliverOptions: [...deliver.entries()].sort(byName),
    }
  }, [instructors])

  const filteredInstructors = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (instructors ?? []).filter((i) => {
      if (q && !i.full_name.toLowerCase().includes(q)) return false
      if (cityId && i.city_id !== cityId) return false
      // Matched by id, never by name — same rule as staffing city-matching.
      if (deliverCityId && !i.deliver_city_ids.includes(deliverCityId)) return false
      return true
    })
  }, [instructors, search, cityId, deliverCityId])

  const filtersActive = !!(search.trim() || cityId || deliverCityId)

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Instructors" subtitle="Directory of approved instructors." />

      <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name…"
          className="h-9 px-3 w-full sm:w-64 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
        <select
          value={cityId}
          onChange={(e) => setCityId(e.target.value)}
          className="h-9 px-3 w-full sm:w-52 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        >
          <option value="">All cities</option>
          {cityOptions.map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>
        <select
          value={deliverCityId}
          onChange={(e) => setDeliverCityId(e.target.value)}
          className="h-9 px-3 w-full sm:w-60 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        >
          <option value="">Open to work anywhere</option>
          {deliverOptions.map(([id, name]) => (
            <option key={id} value={id}>Open to work in {name}</option>
          ))}
        </select>
        {filtersActive && (
          <button
            onClick={() => { setSearch(""); setCityId(""); setDeliverCityId("") }}
            className="h-9 px-3 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {filteredInstructors.length === 0 ? (
        <EmptyState title={(instructors ?? []).length === 0 ? "No approved instructors yet" : "No instructors match your filters"} />
      ) : (
        <div className="space-y-2">
          {filteredInstructors.map((i) => (
            <button
              key={i.id}
              onClick={() => setProfileUserId(i.id)}
              className="w-full flex items-center justify-between gap-3 p-3 rounded-lg border bg-card text-left hover:border-muted-foreground/30 transition-colors"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">{i.full_name}</p>
                <p className="text-xs text-muted-foreground truncate">{i.email}</p>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1.5 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <MapPin size={11} />
                    {i.city_name ?? <span className="italic">No city</span>}
                  </span>
                  {i.deliver_city_names.length > 0 && (
                    <span className="truncate">· Works in {i.deliver_city_names.join(", ")}</span>
                  )}
                </div>
              </div>
              <StatusPill status={i.status} />
            </button>
          ))}
        </div>
      )}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}
