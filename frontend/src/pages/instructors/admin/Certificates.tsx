import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, ClipboardList, FileEdit, Mail, RefreshCcw, Ticket, Trash2, XCircle } from "lucide-react"
import { listApplicantsApi, listInvitationsApi } from "@/api/instructors/admin"
import {
  createCertificateApi, deleteCertificateApi, listCertificatesApi, paymentsInstructorDropdownApi,
} from "@/api/instructors/payments_admin"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner, StatCard } from "@/pages/instructors/components/common"

/**
 * Certificates admin page — faithful port of the reference app's
 * tab-certificates + modal-create-certificate (literal table + "Issue
 * Certificate" modal that creates a new ad-hoc workshop-delivery certificate),
 * not a link-out to the Documents Hub.
 */
export default function InstructorsAdminCertificates() {
  const qc = useQueryClient()

  // Persistent 5-stat quick bar — same computation as Overview.tsx, duplicated
  // locally per instructions (avoid importing from a concurrently-edited file).
  const { data: applicants, isLoading: loadingApplicants } = useQuery({
    queryKey: ["admin-applicants"],
    queryFn: listApplicantsApi,
  })
  const { data: invitations, isLoading: loadingInvitations } = useQuery({
    queryKey: ["admin-invitations"],
    queryFn: listInvitationsApi,
  })

  const { data: certificates, isLoading: loadingCertificates } = useQuery({
    queryKey: ["admin-certificates"],
    queryFn: listCertificatesApi,
  })
  const { data: instructorOptions } = useQuery({
    queryKey: ["payments-instructor-options"],
    queryFn: paymentsInstructorDropdownApi,
  })

  const [issueOpen, setIssueOpen] = useState(false)
  const [form, setForm] = useState({
    instructor_user_id: "", workshop_name: "", workshop_date: "", location: "", send_email: false,
  })
  const [error, setError] = useState<string | null>(null)

  const createCertificate = useMutation({
    mutationFn: () => createCertificateApi(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-certificates"] })
      setIssueOpen(false)
      setForm({ instructor_user_id: "", workshop_name: "", workshop_date: "", location: "", send_email: false })
      setError(null)
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? "Failed to issue certificate.")
    },
  })

  const removeCertificate = useMutation({
    mutationFn: (id: string) => deleteCertificateApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-certificates"] }),
  })

  if (loadingApplicants || loadingInvitations || loadingCertificates) return <Spinner />

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

  const allCertificates = certificates ?? []

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

      <PageHeader
        title="Certificates of Achievement"
        subtitle="View, download, manually issue, and email achievement certificates for instructors."
        action={<Button onClick={() => setIssueOpen(true)}>+ Issue Certificate</Button>}
      />

      <div className="rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl overflow-hidden">
        <div className="flex items-center gap-3 px-5 py-3 border-b border-border/60 justify-between flex-wrap">
          <span className="text-sm text-muted-foreground font-semibold">
            {allCertificates.length} Certificates Issued
          </span>
          <Button
            size="sm" variant="outline"
            onClick={() => qc.invalidateQueries({ queryKey: ["admin-certificates"] })}
          >
            <RefreshCcw size={14} className="mr-1.5" /> Refresh
          </Button>
        </div>

        {allCertificates.length === 0 ? (
          <EmptyState title="No certificates issued yet" hint="Use “+ Issue Certificate” to create one." />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/60 text-muted-foreground uppercase text-xs tracking-wider">
                <th className="text-left font-semibold px-5 py-2.5">Instructor</th>
                <th className="text-left font-semibold px-5 py-2.5">Workshop/Course</th>
                <th className="text-left font-semibold px-5 py-2.5">Date</th>
                <th className="text-left font-semibold px-5 py-2.5">Location</th>
                <th className="text-center font-semibold px-5 py-2.5">PDF</th>
                <th className="text-right font-semibold px-5 py-2.5">Actions</th>
              </tr>
            </thead>
            <tbody>
              {allCertificates.map((c) => (
                <tr key={c.id} className="border-b border-border/40 last:border-0">
                  <td className="px-5 py-3">
                    <p className="font-medium">{c.instructor_name ?? "Unknown"}</p>
                    <p className="text-xs text-muted-foreground">{c.instructor_email ?? "—"}</p>
                  </td>
                  <td className="px-5 py-3">{c.workshop_name ?? c.type.replace(/_/g, " ")}</td>
                  <td className="px-5 py-3">{c.workshop_date ?? "—"}</td>
                  <td className="px-5 py-3">{c.location ?? "—"}</td>
                  <td className="px-5 py-3 text-center">
                    {c.file_url ? (
                      <a href={c.file_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                        View
                      </a>
                    ) : (
                      <span className="italic text-muted-foreground">No PDF</span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Button size="sm" variant="outline" disabled title="Email delivery not yet implemented">
                        <Mail size={14} className="mr-1.5" /> Email
                      </Button>
                      <Button
                        size="sm" variant="destructive"
                        onClick={() => removeCertificate.mutate(c.id)}
                        disabled={removeCertificate.isPending}
                      >
                        <Trash2 size={14} className="mr-1.5" /> Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Dialog open={issueOpen} onOpenChange={setIssueOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Issue Certificate of Achievement</DialogTitle></DialogHeader>
          <form
            className="space-y-3"
            onSubmit={(e) => { e.preventDefault(); createCertificate.mutate() }}
          >
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Instructor</label>
              <select
                className="input mt-1" required value={form.instructor_user_id}
                onChange={(e) => setForm({ ...form, instructor_user_id: e.target.value })}
              >
                <option value="">Select Instructor...</option>
                {(instructorOptions ?? []).map((o) => (
                  <option key={o.id} value={o.id}>{o.full_name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground">Workshop Description</label>
              <input
                className="input mt-1" type="text" required
                placeholder="e.g. Advanced Cubesat Systems Workshop"
                value={form.workshop_name}
                onChange={(e) => setForm({ ...form, workshop_name: e.target.value })}
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground">Workshop Date(s)</label>
              <input
                className="input mt-1" type="text" required
                placeholder="e.g. 30 October 2025"
                value={form.workshop_date}
                onChange={(e) => setForm({ ...form, workshop_date: e.target.value })}
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground">Location</label>
              <input
                className="input mt-1" type="text" required
                placeholder="e.g. GEMS Metropole School, Dubai"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
              />
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox" checked={form.send_email}
                onChange={(e) => setForm({ ...form, send_email: e.target.checked })}
              />
              Deliver via email immediately
            </label>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex gap-3 mt-6">
              <Button type="button" variant="outline" className="flex-1" onClick={() => setIssueOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" className="flex-1" disabled={createCertificate.isPending}>
                {createCertificate.isPending ? "Issuing…" : "Issue"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
