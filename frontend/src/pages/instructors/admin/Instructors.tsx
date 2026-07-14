import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { listAdminInstructorsApi } from "@/api/instructors/admin"
import { UserProfileModal } from "@/components/UserProfileModal"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function InstructorsAdminInstructors() {
  const { data: instructors, isLoading } = useQuery({ queryKey: ["admin-instructors"], queryFn: listAdminInstructorsApi })
  const [profileUserId, setProfileUserId] = useState<string | null>(null)

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Instructors" subtitle="Directory of approved instructors." />

      {(instructors ?? []).length === 0 ? (
        <EmptyState title="No approved instructors yet" />
      ) : (
        <div className="space-y-2">
          {instructors!.map((i) => (
            <button
              key={i.id}
              onClick={() => setProfileUserId(i.id)}
              className="w-full flex items-center justify-between p-3 rounded-lg border bg-card text-left hover:border-muted-foreground/30 transition-colors"
            >
              <div>
                <p className="text-sm font-medium">{i.full_name}</p>
                <p className="text-xs text-muted-foreground">{i.email}</p>
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
