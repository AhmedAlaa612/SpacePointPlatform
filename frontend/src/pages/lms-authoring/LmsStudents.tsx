import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate, useSearch } from "@tanstack/react-router"
import { Search } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { listInviteCodesApi, searchStudentsApi } from "@/api/lms_admin"
import { UserProfileModal } from "@/components/UserProfileModal"

/** Student management list (2026-08-12) — the operator's ask was somewhere
 * to see every student, their nickname, and drill into what they're
 * enrolled in, distinct from the per-cohort Progress Grid a prior pass
 * mistakenly built instead. Search-first rather than a full unpaginated
 * roster — the backend caps results at 50 rows.
 *
 * The batch filter (2026-08-13) reads `invite_code` from the URL so the
 * invite-codes page can deep-link into "the students on this code".
 *
 * **A table, not cards (2026-08-14).** The card list showed a name, an email
 * and a nickname pill, which meant identifying anyone — which school, which
 * grade, which intake, joined when — required opening their page one at a
 * time. Those are columns you scan down a roster, which is what the
 * operator's own prior tooling did and why they asked for it back.
 *
 * Two destinations per row, because they are genuinely different questions:
 * the **name** opens the profile (who is this, what have they done), and
 * **Manage** opens the detail page (change what they're enrolled in).
 */
export default function LmsStudents() {
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as { invite_code?: string }
  const [query, setQuery] = useState("")
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [loginStatus, setLoginStatus] = useState<"all" | "never" | "has_logged_in">("all")
  const [rosterMode, setRosterMode] = useState<"student" | "observer">("student")
  const inviteCode = search.invite_code ?? ""

  const { data: students = [], isLoading } = useQuery({
    queryKey: ["lms-admin-students", query, inviteCode, loginStatus, rosterMode],
    queryFn: () => searchStudentsApi({ q: query || undefined, invite_code: inviteCode || undefined, login_status: loginStatus, mode: rosterMode }),
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
        <div className="flex rounded-xl bg-card border border-border p-0.5">
          <button
            type="button"
            onClick={() => setRosterMode("student")}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
              rosterMode === "student" ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Students
          </button>
          <button
            type="button"
            onClick={() => setRosterMode("observer")}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors cursor-pointer ${
              rosterMode === "observer" ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Observers
          </button>
        </div>
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
          className="w-auto shrink-0 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">All batches</option>
          {codes.map((c) => (
            <option key={c.id} value={c.code}>{c.label ? `${c.label} (${c.code})` : c.code}</option>
          ))}
          {/* Students who signed up before the invite gate existed have no
              code at all — without this they'd be unreachable by filter. */}
          <option value="none">No code</option>
        </select>
        <select
          value={loginStatus}
          onChange={(e) => setLoginStatus(e.target.value as "all" | "never" | "has_logged_in")}
          className="w-auto shrink-0 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="all">Any login status</option>
          <option value="never">Never logged in</option>
          <option value="has_logged_in">Has logged in</option>
        </select>
      </div>

      {isLoading ? (
        <Spinner />
      ) : students.length === 0 ? (
        <EmptyState
          title={rosterMode === "observer" ? "No observers found" : "No students found"}
          hint={
            query || inviteCode
              ? "Try a different search or batch."
              : rosterMode === "observer"
              ? "No observer accounts exist yet."
              : "No student accounts exist yet."
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-2xl ring-1 ring-border">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                {["Name", "Code used", "Joined", "Login", ""].map((header, i) => (
                  <th
                    key={i}
                    className="text-left font-medium text-muted-foreground px-4 py-2.5 whitespace-nowrap text-xs uppercase tracking-wider"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3 whitespace-nowrap">
                    <button
                      onClick={() => setProfileUserId(s.id)}
                      className="font-semibold text-foreground hover:text-primary hover:underline transition-colors text-left"
                      title="Open profile"
                    >
                      {s.full_name}
                    </button>
                    <span className="block text-xs text-muted-foreground">{s.email}</span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {s.invite_code ? (
                      <span className="text-xs font-semibold text-primary" title={s.invite_label ?? undefined}>
                        {s.invite_label ?? s.invite_code}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                    {s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {s.last_login_at ? (
                      <span className="text-muted-foreground">{new Date(s.last_login_at).toLocaleDateString()}</span>
                    ) : (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400">
                        NEVER LOGGED IN
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-right">
                    <button
                      onClick={() => {
                        const from = typeof window !== "undefined" ? (window.location.pathname + window.location.search) : undefined
                        void navigate({
                          to: `/lms-authoring/students/${s.id}`,
                          search: (from ? { from } : {}) as never,
                        })
                      }}
                      className="text-xs font-medium text-muted-foreground hover:text-primary transition-colors cursor-pointer"
                      title="Manage enrollments"
                    >
                      Manage
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}
