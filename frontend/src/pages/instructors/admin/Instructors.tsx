import { useMemo, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, Banknote, CheckCircle2, LineChart, MapPin } from "lucide-react"
import { getAdminInstructorBankDetailsApi, listAdminInstructorsApi } from "@/api/instructors/admin"
import { UserProfileModal } from "@/components/UserProfileModal"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

function BankDetailsDialog({ userId, name, onClose }: { userId: string; name: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-instructor-bank-details", userId],
    queryFn: () => getAdminInstructorBankDetailsApi(userId),
  })
  const rows: [string, string | null][] = [
    ["Account holder name", data?.account_holder_name ?? null],
    ["Bank name", data?.bank_name ?? null],
    ["IBAN", data?.iban ?? null],
    ["SWIFT/BIC", data?.swift_bic ?? null],
    ["Bank location", data?.bank_location ?? null],
  ]
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Bank Details — {name}</DialogTitle></DialogHeader>
        {isLoading ? (
          <Spinner />
        ) : (
          <div className="flex flex-col gap-2.5">
            {rows.map(([label, value]) => (
              <div key={label}>
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-0.5">{label}</p>
                <p className="text-sm text-foreground">{value?.trim() || <span className="text-muted-foreground italic">Not set</span>}</p>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default function InstructorsAdminInstructors() {
  const navigate = useNavigate()
  const { data: instructors, isLoading } = useQuery({ queryKey: ["admin-instructors"], queryFn: listAdminInstructorsApi })
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [bankDetailsFor, setBankDetailsFor] = useState<{ id: string; name: string } | null>(null)
  const [search, setSearch] = useState("")
  const [cityId, setCityId] = useState("")
  const [deliverCityId, setDeliverCityId] = useState("")
  const [bankFilter, setBankFilter] = useState<"" | "missing" | "complete">("")

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
      if (bankFilter === "missing" && i.bank_details_complete) return false
      if (bankFilter === "complete" && !i.bank_details_complete) return false
      return true
    })
  }, [instructors, search, cityId, deliverCityId, bankFilter])

  const filtersActive = !!(search.trim() || cityId || deliverCityId || bankFilter)

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
        <select
          value={bankFilter}
          onChange={(e) => setBankFilter(e.target.value as "" | "missing" | "complete")}
          className="h-9 px-3 w-full sm:w-52 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        >
          <option value="">Any bank details status</option>
          <option value="missing">Bank details missing</option>
          <option value="complete">Bank details on file</option>
        </select>
        {filtersActive && (
          <button
            onClick={() => { setSearch(""); setCityId(""); setDeliverCityId(""); setBankFilter("") }}
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
            <div
              key={i.id}
              role="button"
              tabIndex={0}
              onClick={() => setProfileUserId(i.id)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setProfileUserId(i.id) } }}
              className="w-full flex items-center justify-between gap-3 p-3 rounded-lg border bg-card text-left hover:border-muted-foreground/30 transition-colors cursor-pointer"
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
                  {i.bank_details_complete ? (
                    <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 size={11} /> Bank details on file
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                      <AlertTriangle size={11} /> Bank details missing
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={(e) => { e.stopPropagation(); void navigate({ to: `/instructors/admin/instructors/${i.id}/performance` }) }}
                >
                  <LineChart size={14} className="mr-1.5" /> Performance
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={(e) => { e.stopPropagation(); setBankDetailsFor({ id: i.id, name: i.full_name }) }}
                >
                  <Banknote size={14} className="mr-1.5" /> View bank details
                </Button>
                <StatusPill status={i.status} />
              </div>
            </div>
          ))}
        </div>
      )}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
      {bankDetailsFor && (
        <BankDetailsDialog
          userId={bankDetailsFor.id}
          name={bankDetailsFor.name}
          onClose={() => setBankDetailsFor(null)}
        />
      )}
    </div>
  )
}
