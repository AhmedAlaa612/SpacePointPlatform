import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { listApplicantsApi } from "@/api/instructors/admin"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function InstructorsAdminApplicants() {
  const navigate = useNavigate()
  const { data: applicants, isLoading } = useQuery({ queryKey: ["admin-applicants"], queryFn: listApplicantsApi })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Applicants" subtitle="Review and manage the instructor scholarship pipeline." />

      {(applicants ?? []).length === 0 ? (
        <EmptyState title="No applicants yet" />
      ) : (
        <div className="space-y-2.5">
          {applicants!.map((a) => (
            <div
              key={a.id}
              onClick={() => void navigate({ to: "/instructors/admin/applicants/$userId", params: { userId: a.id } })}
              className="w-full flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl border border-border/60 bg-card hover:bg-muted/40 transition-all cursor-pointer group shadow-sm hover:shadow animate-fade-in"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-foreground group-hover:text-primary transition-colors">{a.full_name}</p>
                <p className="text-xs text-muted-foreground mt-0.5 truncate">
                  {a.email} {a.university ? `· ${a.university}` : ""}
                </p>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <StatusPill status={a.status} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
