import { useQuery } from "@tanstack/react-query"
import { listAdminInstructorsApi } from "@/api/instructors/admin"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function InstructorsAdminInstructors() {
  const { data: instructors, isLoading } = useQuery({ queryKey: ["admin-instructors"], queryFn: listAdminInstructorsApi })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Instructors" subtitle="Directory of approved instructors." />

      {(instructors ?? []).length === 0 ? (
        <EmptyState title="No approved instructors yet" />
      ) : (
        <div className="space-y-2">
          {instructors!.map((i) => (
            <div key={i.id} className="flex items-center justify-between p-3 rounded-lg border bg-card">
              <div>
                <p className="text-sm font-medium">{i.full_name}</p>
                <p className="text-xs text-muted-foreground">{i.email}</p>
              </div>
              <StatusPill status={i.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
