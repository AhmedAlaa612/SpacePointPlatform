import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { listAdminInstructorsApi } from "@/api/instructors/admin"
import { UserProfileModal } from "@/components/UserProfileModal"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function InstructorsAdminInstructors() {
  const { data: instructors, isLoading } = useQuery({ queryKey: ["admin-instructors"], queryFn: listAdminInstructorsApi })
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [search, setSearch] = useState("")

  const filteredInstructors = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return instructors ?? []
    return (instructors ?? []).filter((i) => i.full_name.toLowerCase().includes(q))
  }, [instructors, search])

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Instructors" subtitle="Directory of approved instructors." />

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by name…"
        className="h-9 px-3 w-full sm:w-64 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
      />

      {filteredInstructors.length === 0 ? (
        <EmptyState title={(instructors ?? []).length === 0 ? "No approved instructors yet" : "No instructors match your search"} />
      ) : (
        <div className="space-y-2">
          {filteredInstructors.map((i) => (
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
