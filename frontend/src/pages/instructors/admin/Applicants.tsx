import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { listApplicantsApi } from "@/api/instructors/admin"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

const PAGE_SIZE = 10

// Order/labels mirror the legacy admin console's status filter dropdown.
const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "All Statuses" },
  { value: "in_progress", label: "In Progress" },
  { value: "under_review", label: "Under Review" },
  { value: "research_approved", label: "Research Approved" },
  { value: "phase_1_approved", label: "Phase 1 Approved" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
]

export default function InstructorsAdminApplicants() {
  const navigate = useNavigate()
  const { data: applicants, isLoading } = useQuery({ queryKey: ["admin-applicants"], queryFn: listApplicantsApi })

  const [statusFilter, setStatusFilter] = useState("all")
  const [page, setPage] = useState(1)

  const filtered = useMemo(() => {
    const all = applicants ?? []
    return statusFilter === "all" ? all : all.filter((a) => a.status === statusFilter)
  }, [applicants, statusFilter])

  const total = filtered.length
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const startNode = total === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1
  const endNode = Math.min(currentPage * PAGE_SIZE, total)

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Applicants" subtitle="Review and manage the instructor scholarship pipeline." />

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-sm text-muted-foreground">
          {total} applicant{total === 1 ? "" : "s"}
          {statusFilter !== "all" ? ` · ${STATUS_FILTERS.find((s) => s.value === statusFilter)?.label}` : ""}
        </p>
        <select
          className="rounded-lg border border-border bg-background text-foreground text-sm px-3 py-2 outline-none focus:border-ring focus:ring-1 focus:ring-ring"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(1)
          }}
        >
          {STATUS_FILTERS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {total === 0 ? (
        <EmptyState title="No applicants found" />
      ) : (
        <div className="rounded-xl border border-border/60 bg-card overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-3 px-4 font-semibold">Applicant Name</th>
                  <th className="py-3 px-4 font-semibold">City</th>
                  <th className="py-3 px-4 font-semibold">Status</th>
                  <th className="py-3 px-4 font-semibold">Application Start Date</th>
                  <th className="py-3 px-4 font-semibold">Submission Date</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((a) => (
                  <tr
                    key={a.id}
                    onClick={() => void navigate({ to: "/instructors/admin/applicants/$userId", params: { userId: a.id } })}
                    className="border-b border-border/40 last:border-0 hover:bg-muted/40 transition-colors cursor-pointer group"
                  >
                    <td className="py-3.5 px-4">
                      <p className="font-semibold text-foreground group-hover:text-primary transition-colors">{a.full_name}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-[240px]">{a.email}</p>
                    </td>
                    <td className="py-3.5 px-4 text-muted-foreground">{a.city_of_residence || "—"}</td>
                    <td className="py-3.5 px-4"><StatusPill status={a.status} /></td>
                    <td className="py-3.5 px-4 text-muted-foreground whitespace-nowrap">
                      {a.created_at ? new Date(a.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="py-3.5 px-4 text-muted-foreground whitespace-nowrap">
                      {a.submitted_at ? new Date(a.submitted_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-border/60 flex-wrap">
            <p className="text-xs text-muted-foreground">
              Showing {startNode}-{endNode} of {total}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="rounded-lg border border-border bg-background text-foreground text-sm px-3 py-1.5 hover:bg-muted/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                Prev
              </button>
              <button
                type="button"
                className="rounded-lg border border-border bg-background text-foreground text-sm px-3 py-1.5 hover:bg-muted/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                disabled={currentPage >= pageCount}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
