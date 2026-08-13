import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate, useSearch } from "@tanstack/react-router"
import { Search } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { listInviteCodesApi, searchStudentsApi } from "@/api/lms_admin"

/** Student management list (2026-08-12) — the operator's ask was somewhere
 * to see every student, their nickname, and drill into what they're
 * enrolled in, distinct from the per-cohort Progress Grid a prior pass
 * mistakenly built instead. Search-first rather than a full unpaginated
 * roster — the backend caps results at 50 rows.
 *
 * The batch filter (2026-08-13) reads `invite_code` from the URL so the
 * invite-codes page can deep-link into "the students on this code". */
export default function LmsStudents() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as { invite_code?: string }
  const [query, setQuery] = useState("")
  const inviteCode = search.invite_code ?? ""

  const { data: students = [], isLoading } = useQuery({
    queryKey: ["lms-admin-students", query, inviteCode],
    queryFn: () => searchStudentsApi({ q: query || undefined, invite_code: inviteCode || undefined }),
  })
  const { data: codes = [] } = useQuery({
    queryKey: ["lms-admin-invite-codes"],
    queryFn: listInviteCodesApi,
  })

  const setInviteCode = (value: string) =>
    void navigate({
      to: "/lms-authoring/students",
      search: (value ? { invite_code: value } : {}) as never,
      replace: true,
    })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Students" subtitle="Search students, view their profile, and manage what they're enrolled in." />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative max-w-md flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name or email..."
            className="w-full h-10 pl-8 pr-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </div>
        <select
          value={inviteCode}
          onChange={(e) => setInviteCode(e.target.value)}
          className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">All batches</option>
          {codes.map((c) => (
            <option key={c.id} value={c.code}>{c.label ? `${c.label} (${c.code})` : c.code}</option>
          ))}
          {/* Students who signed up before the invite gate existed have no
              code at all — without this they'd be unreachable by filter. */}
          <option value="none">No code</option>
        </select>
      </div>

      {isLoading ? (
        <Spinner />
      ) : students.length === 0 ? (
        <EmptyState
          title="No students found"
          hint={query || inviteCode ? "Try a different search or batch." : "No student accounts exist yet."}
        />
      ) : (
        <div className="flex flex-col gap-2">
          {students.map((s) => (
            <button
              key={s.id}
              onClick={() => void navigate({ to: `/lms-authoring/students/${s.id}` })}
              className="flex items-center justify-between gap-3 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors text-left"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground truncate">{s.full_name}</p>
                <p className="text-xs text-muted-foreground truncate">{s.email}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {s.invite_code && (
                  <span
                    className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground"
                    title={`Signed up with ${s.invite_code}`}
                  >
                    {s.invite_label ?? s.invite_code}
                  </span>
                )}
                {s.nickname && (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                    {s.nickname}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
