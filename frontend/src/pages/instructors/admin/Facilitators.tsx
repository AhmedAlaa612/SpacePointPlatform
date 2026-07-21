import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, ClipboardList, FileEdit, Plus, Ticket, XCircle } from "lucide-react"
import { createFacilitatorApi, listAdminFacilitatorsApi, listApplicantsApi, listInvitationsApi } from "@/api/instructors/admin"
import { UserProfileModal } from "@/components/UserProfileModal"
import { Button } from "@/components/ui/button"
import { EmptyState, Spinner, StatCard } from "@/pages/instructors/components/common"

/**
 * Facilitators — literal port of the reference app's "Manage Facilitators"
 * tab (admin_dashboard.html: tab-facs + modal-add-fac). Includes the same
 * persistent 5-stat quick bar shown above every admin sub-page in the
 * reference, computed the same way Overview.tsx does (duplicated locally
 * since Overview.tsx is being edited concurrently elsewhere).
 */
export default function InstructorsAdminFacilitators() {
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [search, setSearch] = useState("")

  const { data: facilitators, isLoading: loadingFacilitators } = useQuery({
    queryKey: ["admin-facilitators"],
    queryFn: listAdminFacilitatorsApi,
  })

  const filteredFacilitators = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return facilitators ?? []
    return (facilitators ?? []).filter((f) => f.full_name.toLowerCase().includes(q))
  }, [facilitators, search])
  const { data: applicants, isLoading: loadingApplicants } = useQuery({
    queryKey: ["admin-applicants"],
    queryFn: listApplicantsApi,
  })
  const { data: invitations, isLoading: loadingInvitations } = useQuery({
    queryKey: ["admin-invitations"],
    queryFn: listInvitationsApi,
  })

  const create = useMutation({
    mutationFn: () => createFacilitatorApi({ full_name: fullName, email, password }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-facilitators"] })
      setFullName(""); setEmail(""); setPassword("")
      setShowModal(false)
    },
  })

  if (loadingFacilitators || loadingApplicants || loadingInvitations) return <Spinner />

  const allApplicants = applicants ?? []
  const totalStarted = allApplicants.length
  const totalApproved = allApplicants.filter((a) => a.status === "approved").length
  const totalRejected = allApplicants.filter((a) => a.status === "rejected").length
  const totalDraft = allApplicants.filter((a) => a.status === "in_progress").length

  type Invitation = NonNullable<typeof invitations>[number]
  const topCode = (invitations ?? []).reduce<Invitation | null>((top, i) => {
    if (!top || i.used_count > top.used_count) return i
    return top
  }, null)

  function closeModal() {
    setShowModal(false)
    create.reset()
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard icon={<ClipboardList size={18} />} label="Total Started" value={totalStarted} />
        <StatCard icon={<CheckCircle2 size={18} />} label="Approved" value={totalApproved} />
        <StatCard icon={<XCircle size={18} />} label="Rejected" value={totalRejected} />
        <StatCard icon={<FileEdit size={18} />} label="Draft Apps" value={totalDraft} />
        <StatCard
          icon={<Ticket size={18} />}
          label="Top Code"
          value={topCode ? topCode.code : "—"}
          sub={topCode ? `${topCode.used_count} use(s)` : undefined}
        />
      </div>

      <div className="flex justify-between items-center gap-3 flex-wrap">
        <h2 className="text-2xl font-bold tracking-tight">Manage Facilitators</h2>
        <Button onClick={() => setShowModal(true)}>
          <Plus size={14} className="mr-1" /> New Facilitator
        </Button>
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by name…"
        className="h-9 px-3 w-full sm:w-64 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
      />

      <div className="w-full rounded-2xl overflow-hidden border border-border bg-card/70 backdrop-blur-xl ring-1 ring-black/5 dark:bg-card/60 dark:ring-white/10 shadow-xl">
        <div className="p-4 bg-muted/50 border-b border-border text-sm text-muted-foreground text-center">
          Facilitators can access their own dashboard to add modules, slides, and manage instructor content.
        </div>

        {filteredFacilitators.length === 0 ? (
          <EmptyState title={(facilitators ?? []).length === 0 ? "No facilitators yet" : "No facilitators match your search"} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[600px]">
              <thead>
                <tr className="bg-muted/40 border-b border-border text-sm tracking-wide text-muted-foreground uppercase">
                  <th className="py-4 px-6 font-semibold">Name</th>
                  <th className="py-4 px-6 font-semibold">Email</th>
                  <th className="py-4 px-6 font-semibold">Added Date</th>
                </tr>
              </thead>
              <tbody>
                {filteredFacilitators.map((f) => (
                  <tr
                    key={f.id}
                    onClick={() => setProfileUserId(f.id)}
                    className="border-b border-border/50 last:border-0 cursor-pointer hover:bg-muted/40 transition-colors"
                  >
                    <td className="py-4 px-6 font-bold">{f.full_name}</td>
                    <td className="py-4 px-6 text-muted-foreground">{f.email}</td>
                    <td className="py-4 px-6 text-muted-foreground">{new Date(f.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-popover/95 backdrop-blur-2xl p-6 ring-1 ring-black/5 dark:ring-white/10 shadow-xl">
            <h3 className="text-xl font-bold mb-4">Add Facilitator</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                create.mutate()
              }}
              className="flex flex-col gap-4"
            >
              <div>
                <label className="block text-sm font-medium mb-1">Full Name</label>
                <input
                  className="input"
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Email</label>
                <input
                  className="input"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Password</label>
                <input
                  className="input"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              {create.isError && (
                <p className="text-sm text-destructive">
                  {create.error instanceof Error ? create.error.message : "Failed to create facilitator."}
                </p>
              )}

              <div className="flex gap-3 mt-2">
                <Button type="button" variant="outline" className="flex-1" onClick={closeModal}>
                  Cancel
                </Button>
                <Button type="submit" className="flex-1" disabled={create.isPending}>
                  Create
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}
