import { useMemo, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  Award,
  CheckCircle2,
  CreditCard,
  Globe,
  MapPin,
  Search,
  Sparkles,
  Star,
  UserCheck,
} from "lucide-react"
import { isAxiosError } from "axios"
import {
  getOpsInstructorIdCardApi,
  listOpsInstructorsApi,
  setInstructorCertifiedApi,
} from "@/api/instructor_assessment"
import type { OpsInstructorRosterItem } from "@/types/instructor_assessment"
import { PageHeader, Spinner, StatCard } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { EmptyState, Modal } from "@/pages/admin/components/common"
import { cn } from "@/lib/utils"

type SortKey = "unrated" | "rating" | "sessions" | "reliability" | "name"

/** Single read-only compliance chip exposed to Ops (never reveals doc list or files). */
export function DocsComplianceChip({ complete }: { complete: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
        complete
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
      )}
    >
      {complete ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
      {complete ? "Docs completed" : "Docs incomplete"}
    </span>
  )
}

/** CR80 Front & Back ID card modal fetched from Ops-safe endpoint. */
export function OpsIdCardModal({
  userId,
  instructorName,
  onClose,
}: {
  userId: string
  instructorName: string
  onClose: () => void
}) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ops-instructor-id-card", userId],
    queryFn: () => getOpsInstructorIdCardApi(userId),
    retry: false,
  })

  const errorMsg =
    isAxiosError(error) && typeof error.response?.data?.detail === "string"
      ? error.response.data.detail
      : "ID card could not be loaded for this instructor."

  return (
    <Modal title={`Instructor ID Card — ${instructorName}`} onClose={onClose} maxWidth="max-w-2xl">
      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <div className="rounded-xl border border-border bg-muted/30 p-6 text-center text-sm text-muted-foreground">
          {errorMsg}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between rounded-xl border border-border bg-muted/30 px-3.5 py-2.5 text-xs">
            <span className="text-muted-foreground">Card ID</span>
            <span className="font-mono font-semibold text-foreground">{data.card_id ?? "—"}</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {data.front_b64 && (
              <div className="flex flex-col gap-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Front Side
                </span>
                <img
                  src={`data:image/png;base64,${data.front_b64}`}
                  alt={`${instructorName} ID Card Front`}
                  className="w-full rounded-xl border border-border shadow-md"
                />
              </div>
            )}
            {data.back_b64 && (
              <div className="flex flex-col gap-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Back Side
                </span>
                <img
                  src={`data:image/png;base64,${data.back_b64}`}
                  alt={`${instructorName} ID Card Back`}
                  className="w-full rounded-xl border border-border shadow-md"
                />
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  )
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return "?"
  return parts
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()
}

export default function OpsInstructors() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()

  const { data: roster = [], isLoading } = useQuery({
    queryKey: ["ops-instructors"],
    queryFn: listOpsInstructorsApi,
  })

  const [search, setSearch] = useState("")
  const [deliverCity, setDeliverCity] = useState("all")
  const [livesInCity, setLivesInCity] = useState("all")
  const [certFilter, setCertFilter] = useState<"all" | "certified" | "standard">("all")
  const [docsFilter, setDocsFilter] = useState<"all" | "complete" | "incomplete">("all")
  const [transportFilter, setTransportFilter] = useState<"all" | "own_car" | "needs_transport">("all")
  const [perfFilter, setPerfFilter] = useState<"all" | "unrated" | "exceptional" | "concern">("all")
  const [sortBy, setSortBy] = useState<SortKey>("unrated")
  const [idCardTarget, setIdCardTarget] = useState<{ userId: string; name: string } | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)

  const toggleCertified = useMutation({
    mutationFn: ({ userId, certified }: { userId: string; certified: boolean }) => {
      setTogglingId(userId)
      return setInstructorCertifiedApi(userId, certified)
    },
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ["ops-instructors"] })
      qc.invalidateQueries({ queryKey: ["instructor-performance", vars.userId] })
      toast.success(vars.certified ? "Instructor marked as Certified." : "Certified label removed.")
    },
    onError: (err) => {
      const msg =
        isAxiosError(err) && typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : "Could not update certification label."
      toast.error(msg)
    },
    onSettled: () => setTogglingId(null),
  })

  const { deliverCities, homeCities, summary } = useMemo(() => {
    const dSet = new Set<string>()
    const hSet = new Set<string>()
    let certified = 0
    let docsComplete = 0
    let needRating = 0
    for (const r of roster) {
      for (const c of r.deliver_city_names) dSet.add(c)
      if (r.city_name) hSet.add(r.city_name)
      if (r.is_certified) certified += 1
      if (r.docs_complete) docsComplete += 1
      if (r.unrated_cohorts_count > 0) needRating += 1
    }
    return {
      deliverCities: Array.from(dSet).sort((a, b) => a.localeCompare(b)),
      homeCities: Array.from(hSet).sort((a, b) => a.localeCompare(b)),
      summary: { total: roster.length, certified, docsComplete, needRating },
    }
  }, [roster])

  const hasActiveFilters =
    search.trim() !== "" ||
    deliverCity !== "all" ||
    livesInCity !== "all" ||
    certFilter !== "all" ||
    docsFilter !== "all" ||
    transportFilter !== "all" ||
    perfFilter !== "all"

  const resetFilters = () => {
    setSearch("")
    setDeliverCity("all")
    setLivesInCity("all")
    setCertFilter("all")
    setDocsFilter("all")
    setTransportFilter("all")
    setPerfFilter("all")
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const matches = roster.filter((r) => {
      if (q) {
        const hay = `${r.full_name} ${r.email} ${r.card_id ?? ""}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      if (deliverCity !== "all" && !r.deliver_city_names.includes(deliverCity)) return false
      if (livesInCity !== "all" && r.city_name !== livesInCity) return false
      if (certFilter === "certified" && !r.is_certified) return false
      if (certFilter === "standard" && r.is_certified) return false
      if (docsFilter === "complete" && !r.docs_complete) return false
      if (docsFilter === "incomplete" && r.docs_complete) return false
      if (transportFilter === "own_car" && !r.has_own_transportation) return false
      if (transportFilter === "needs_transport" && r.has_own_transportation) return false
      if (perfFilter === "unrated" && r.unrated_cohorts_count === 0) return false
      if (perfFilter === "exceptional" && !r.flags.includes("exceptional")) return false
      if (perfFilter === "concern" && !r.flags.includes("concern")) return false
      return true
    })

    const copy = [...matches]
    copy.sort((a, b) => {
      if (sortBy === "unrated") {
        if (b.unrated_cohorts_count !== a.unrated_cohorts_count) {
          return b.unrated_cohorts_count - a.unrated_cohorts_count
        }
        return (b.average_rating ?? -1) - (a.average_rating ?? -1)
      }
      if (sortBy === "rating") return (b.average_rating ?? -1) - (a.average_rating ?? -1)
      if (sortBy === "sessions") return b.total_sessions_delivered - a.total_sessions_delivered
      if (sortBy === "reliability") return (b.reliability_ratio ?? -1) - (a.reliability_ratio ?? -1)
      return a.full_name.localeCompare(b.full_name)
    })
    return copy
  }, [roster, search, deliverCity, livesInCity, certFilter, docsFilter, transportFilter, perfFilter, sortBy])

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Instructors"
        subtitle="Operations roster, delivery readiness, certifications, Card IDs, and cohort performance reviews"
      />

      {/* KPI Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard icon={<UserCheck size={18} />} label="Total Instructors" value={summary.total} />
        <StatCard icon={<Award size={18} />} label="Certified" value={summary.certified} />
        <StatCard icon={<CheckCircle2 size={18} />} label="Docs Completed" value={summary.docsComplete} />
        <StatCard
          icon={<Star size={18} />}
          label="Need Cohort Rating"
          value={summary.needRating}
        />
      </div>

      {/* Filters & Search */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search instructor name, email, or Card ID (SP-####-UAE)…"
              className="w-full h-9 pl-9 pr-3 rounded-xl border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground whitespace-nowrap">Sort by</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm text-foreground focus:outline-none focus:border-primary"
            >
              <option value="unrated">Unrated cohorts first</option>
              <option value="rating">Highest rating</option>
              <option value="sessions">Most sessions delivered</option>
              <option value="reliability">Highest reliability</option>
              <option value="name">Name (A–Z)</option>
            </select>
            {hasActiveFilters && (
              <Button size="sm" variant="outline" onClick={resetFilters} className="h-9 text-xs whitespace-nowrap">
                Clear filters
              </Button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
          <select
            aria-label="Filter by delivery city"
            value={deliverCity}
            onChange={(e) => setDeliverCity(e.target.value)}
            className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground"
          >
            <option value="all">Delivers in: All cities</option>
            {deliverCities.map((c) => (
              <option key={c} value={c}>
                Delivers in: {c}
              </option>
            ))}
          </select>

          <select
            aria-label="Filter by home city"
            value={livesInCity}
            onChange={(e) => setLivesInCity(e.target.value)}
            className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground"
          >
            <option value="all">Lives in: All cities</option>
            {homeCities.map((c) => (
              <option key={c} value={c}>
                Lives in: {c}
              </option>
            ))}
          </select>

          <select
            aria-label="Filter by certification"
            value={certFilter}
            onChange={(e) => setCertFilter(e.target.value as typeof certFilter)}
            className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground"
          >
            <option value="all">Certification: All</option>
            <option value="certified">Certified only</option>
            <option value="standard">Not tagged Certified</option>
          </select>

          <select
            aria-label="Filter by docs status"
            value={docsFilter}
            onChange={(e) => setDocsFilter(e.target.value as typeof docsFilter)}
            className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground"
          >
            <option value="all">Docs: All</option>
            <option value="complete">Docs completed</option>
            <option value="incomplete">Docs incomplete</option>
          </select>

          <select
            aria-label="Filter by transport"
            value={transportFilter}
            onChange={(e) => setTransportFilter(e.target.value as typeof transportFilter)}
            className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground"
          >
            <option value="all">Transport: All</option>
            <option value="own_car">Has own car</option>
            <option value="needs_transport">Needs transport</option>
          </select>

          <select
            aria-label="Filter by performance"
            value={perfFilter}
            onChange={(e) => setPerfFilter(e.target.value as typeof perfFilter)}
            className="h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground"
          >
            <option value="all">Performance: All</option>
            <option value="unrated">Has unrated cohorts</option>
            <option value="exceptional">Flagged Exceptional</option>
            <option value="concern">Flagged Concern</option>
          </select>
        </div>
      </div>

      {/* Results count */}
      <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
        <span>
          Showing <strong className="text-foreground">{filtered.length}</strong> of {roster.length} instructors
        </span>
      </div>

      {/* Roster Cards */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<UserCheck size={28} />}
          title="No matching instructors"
          description={
            hasActiveFilters
              ? "Try adjusting or clearing your filters."
              : "Active instructors will appear here once approved."
          }
        />
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map((item) => (
            <InstructorRosterRow
              key={item.id}
              item={item}
              toggling={togglingId === item.id}
              onToggleCertified={() => toggleCertified.mutate({ userId: item.id, certified: !item.is_certified })}
              onOpenIdCard={() => setIdCardTarget({ userId: item.id, name: item.full_name })}
              onOpenProfile={() => void navigate({ to: `/operations/instructors/${item.id}` })}
            />
          ))}
        </div>
      )}

      {idCardTarget && (
        <OpsIdCardModal
          userId={idCardTarget.userId}
          instructorName={idCardTarget.name}
          onClose={() => setIdCardTarget(null)}
        />
      )}
    </div>
  )
}

function InstructorRosterRow({
  item,
  toggling,
  onToggleCertified,
  onOpenIdCard,
  onOpenProfile,
}: {
  item: OpsInstructorRosterItem
  toggling: boolean
  onToggleCertified: () => void
  onOpenIdCard: () => void
  onOpenProfile: () => void
}) {
  const reliabilityPct = item.reliability_ratio != null ? `${Math.round(item.reliability_ratio * 100)}%` : "—"

  return (
    <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-4 sm:p-5 flex flex-col gap-4 hover:ring-primary/30 transition-all">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        {/* Identity */}
        <div className="flex items-start gap-3.5 min-w-0">
          <div className="w-12 h-12 rounded-full bg-muted border border-border overflow-hidden flex items-center justify-center font-semibold text-sm text-foreground shrink-0">
            {item.photo_url ? (
              <img src={item.photo_url} alt={item.full_name} className="w-full h-full object-cover" />
            ) : (
              initialsOf(item.full_name)
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={onOpenProfile}
                className="text-base font-bold text-foreground hover:text-primary hover:underline text-left"
              >
                {item.full_name}
              </button>
              {item.card_id ? (
                <button
                  type="button"
                  onClick={onOpenIdCard}
                  title="Preview Instructor ID Card"
                  className="inline-flex items-center gap-1 rounded-full border border-primary/25 bg-primary/10 px-2.5 py-0.5 text-[11px] font-mono font-semibold text-primary hover:bg-primary/20 transition-colors"
                >
                  <CreditCard size={11} />
                  {item.card_id}
                </button>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                  <CreditCard size={10} /> No Card ID
                </span>
              )}
              {item.flags.includes("exceptional") && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">
                  <Sparkles size={10} /> Exceptional
                </span>
              )}
              {item.flags.includes("concern") && (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-500/15 border border-red-500/30 px-2 py-0.5 text-[10px] font-semibold text-red-700 dark:text-red-300">
                  <AlertTriangle size={10} /> Concern
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground break-words mt-0.5">{item.email}</p>
            <div className="flex flex-wrap items-center gap-3 mt-1.5 text-[11px] text-muted-foreground">
              {item.nationality && (
                <span className="inline-flex items-center gap-1">
                  <Globe size={11} /> {item.nationality}
                </span>
              )}
              {item.fluent_languages.length > 0 && <span>Languages: {item.fluent_languages.join(", ")}</span>}
            </div>
          </div>
        </div>

        {/* Right Controls & Compliance */}
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <DocsComplianceChip complete={item.docs_complete} />

          <button
            type="button"
            disabled={toggling}
            onClick={onToggleCertified}
            title={
              item.is_certified
                ? "Click to remove the Certified Instructor label"
                : "Click to grant the Certified Instructor label"
            }
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-all disabled:opacity-50",
              item.is_certified
                ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/25"
                : "border-border bg-background text-foreground hover:border-primary/50 hover:text-primary",
            )}
          >
            <Award size={13} />
            {item.is_certified ? "Certified" : "+ Certify"}
          </button>

          <Button
            size="sm"
            variant={item.unrated_cohorts_count > 0 ? "default" : "outline"}
            onClick={onOpenProfile}
            className="h-8 text-xs font-semibold"
          >
            {item.unrated_cohorts_count > 0 ? "View Profile & Rate" : "View Profile"}
          </Button>
        </div>
      </div>

      {/* Bottom Row: Readiness + Metrics */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pt-3 border-t border-border/70">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1 rounded-lg bg-muted/60 px-2.5 py-1 text-muted-foreground">
            <MapPin size={12} className="shrink-0" />
            Lives in: <strong className="text-foreground font-medium">{item.city_name ?? "Not set"}</strong>
          </span>

          <span className="inline-flex items-center gap-1 rounded-lg bg-muted/60 px-2.5 py-1 text-muted-foreground">
            Delivers in:{" "}
            <strong className="text-foreground font-medium">
              {item.deliver_city_names.length > 0 ? item.deliver_city_names.join(", ") : "Not set"}
            </strong>
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Sessions:</span>
            <span className="font-semibold tabular-nums text-foreground">
              {item.total_sessions_delivered}/{item.total_sessions_assigned}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Hours:</span>
            <span className="font-semibold tabular-nums text-foreground">{item.total_hours_delivered}h</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Reliability:</span>
            <span className="font-semibold tabular-nums text-foreground">{reliabilityPct}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Star size={12} className="text-primary fill-primary/30" />
            <span className="font-semibold tabular-nums text-foreground">
              {item.average_rating != null ? `${item.average_rating.toFixed(1)} / 5` : "—"}
            </span>
          </div>
          {item.unrated_cohorts_count > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 border border-primary/30 px-2.5 py-0.5 text-[11px] font-semibold text-primary">
              {item.unrated_cohorts_count} Unrated Cohort{item.unrated_cohorts_count === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
