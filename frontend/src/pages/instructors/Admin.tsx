import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, Plus, Trash2, X } from "lucide-react"
import {
  createFacilitatorApi, createInvitationApi, deleteInvitationApi, getApplicantDetailApi,
  listAdminFacilitatorsApi, listAdminInstructorsApi, listApplicantsApi, listInvitationsApi,
  reviewApplicantApi, updateInvitationApi, uploadAdminSignatureApi, upsertSettingApi, getSettingsApi,
} from "@/api/instructors/admin"
import {
  addAddonApi, addSessionApi, bulkImportConfirmApi, bulkImportPreviewApi, createLetterApi,
  downloadBulkImportTemplateApi, generateLetterPdfApi, listAdminLettersApi, listCertificatesApi,
  markPaidApi, paymentsInstructorDropdownApi, publishLetterApi,
} from "@/api/instructors/payments_admin"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, Spinner, StatusPill } from "@/pages/instructors/components/common"
import { cn } from "@/lib/utils"

type Tab = "applications" | "invitations" | "instructors" | "payments" | "settings"
const TABS: { id: Tab; label: string }[] = [
  { id: "applications", label: "Applications" },
  { id: "invitations", label: "Invitations" },
  { id: "instructors", label: "Instructors" },
  { id: "payments", label: "Payments" },
  { id: "settings", label: "Settings" },
]

export default function InstructorsAdmin() {
  const [tab, setTab] = useState<Tab>("applications")

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Instructors Admin</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Manage the scholarship pipeline, instructors, and payments.</p>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2 -mb-px",
              tab === t.id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "applications" && <ApplicationsPanel />}
      {tab === "invitations" && <InvitationsPanel />}
      {tab === "instructors" && <InstructorsPanel />}
      {tab === "payments" && <PaymentsPanel />}
      {tab === "settings" && <SettingsPanel />}
    </div>
  )
}

/* ================================================================== */
/* Applications panel                                                  */

function ApplicationsPanel() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [feedback, setFeedback] = useState("")

  const { data: applicants, isLoading } = useQuery({ queryKey: ["admin-applicants"], queryFn: listApplicantsApi })
  const { data: detail } = useQuery({
    queryKey: ["admin-applicant-detail", selectedId],
    queryFn: () => getApplicantDetailApi(selectedId!),
    enabled: !!selectedId,
  })

  const review = useMutation({
    mutationFn: (status: string) => reviewApplicantApi(selectedId!, status, feedback || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-applicants"] })
      qc.invalidateQueries({ queryKey: ["admin-applicant-detail", selectedId] })
      qc.invalidateQueries({ queryKey: ["admin-overview"] })
      setFeedback("")
    },
  })

  if (isLoading) return <Spinner />

  return (
    <div>
      {(applicants ?? []).length === 0 ? (
        <EmptyState title="No applicants yet" />
      ) : (
        <div className="space-y-2">
          {applicants!.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedId(a.id)}
              className="w-full flex items-center justify-between gap-3 p-3 rounded-lg border bg-card hover:bg-muted text-left transition-colors"
            >
              <div>
                <p className="text-sm font-medium">{a.full_name}</p>
                <p className="text-xs text-muted-foreground">{a.email} {a.university ? `· ${a.university}` : ""}</p>
              </div>
              <StatusPill status={a.status} />
            </button>
          ))}
        </div>
      )}

      <Dialog open={!!selectedId} onOpenChange={(open) => !open && setSelectedId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{detail?.full_name}</DialogTitle></DialogHeader>
          {detail ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{detail.email}</p>
              <StatusPill status={detail.review?.status ?? "in_progress"} />
              {detail.profile && (
                <p className="text-sm text-muted-foreground">
                  {[detail.profile.university, detail.profile.city_of_residence, detail.profile.country]
                    .filter(Boolean).join(" — ")}
                </p>
              )}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Videos submitted</p>
                <p className="text-sm">{detail.videos?.filter((v: any) => v.status === "submitted").length ?? 0} / 3</p>
              </div>
              {detail.presentation_link && (
                <p className="text-sm">Presentation: <a href={detail.presentation_link} target="_blank" rel="noreferrer" className="text-primary underline">{detail.presentation_link}</a></p>
              )}
              {detail.review?.status === "under_review" && (
                <div className="pt-2 border-t space-y-2">
                  <textarea
                    className="input" placeholder="Feedback (optional)" value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => review.mutate("phase_1_approved")} disabled={review.isPending}>
                      <Check size={14} className="mr-1" /> Approve Phase 1
                    </Button>
                    <Button size="sm" onClick={() => review.mutate("approved")} disabled={review.isPending}>
                      <Check size={14} className="mr-1" /> Final approve
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => review.mutate("rejected")} disabled={review.isPending}>
                      <X size={14} className="mr-1" /> Reject
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ) : <Spinner />}
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* ================================================================== */
/* Invitations panel                                                   */

function InvitationsPanel() {
  const qc = useQueryClient()
  const [code, setCode] = useState("")
  const [maxUses, setMaxUses] = useState(20)

  const { data: invitations, isLoading } = useQuery({ queryKey: ["admin-invitations"], queryFn: listInvitationsApi })

  const create = useMutation({
    mutationFn: () => createInvitationApi({ code, max_uses: maxUses }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-invitations"] }); setCode("") },
  })
  const toggleActive = useMutation({
    mutationFn: (params: { id: string; is_active: boolean }) => updateInvitationApi(params.id, { is_active: params.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-invitations"] }),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteInvitationApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-invitations"] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div>
      <Card className="mb-4">
        <CardContent className="p-5 flex flex-col sm:flex-row gap-3">
          <div className="flex-1"><input className="input" placeholder="Invitation code" value={code} onChange={(e) => setCode(e.target.value)} /></div>
          <div className="w-32"><input className="input" type="number" placeholder="Max uses" value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value))} /></div>
          <Button onClick={() => create.mutate()} disabled={!code || create.isPending}>
            <Plus size={14} className="mr-1" /> Create
          </Button>
        </CardContent>
      </Card>

      {(invitations ?? []).length === 0 ? (
        <EmptyState title="No invitation codes yet" />
      ) : (
        <div className="space-y-2">
          {invitations!.map((i) => (
            <div key={i.id} className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-card">
              <div>
                <p className="text-sm font-mono font-medium">{i.code}</p>
                <p className="text-xs text-muted-foreground">{i.used_count} / {i.max_uses} used</p>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => toggleActive.mutate({ id: i.id, is_active: !i.is_active })}>
                  {i.is_active ? "Active" : "Inactive"}
                </Button>
                <button onClick={() => remove.mutate(i.id)} className="p-2 text-muted-foreground hover:text-destructive">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ================================================================== */
/* Instructors panel (directory + facilitator accounts)                */

function InstructorsPanel() {
  const qc = useQueryClient()
  const [facilitatorOpen, setFacilitatorOpen] = useState(false)
  const [form, setForm] = useState({ full_name: "", email: "", password: "" })

  const { data: instructors, isLoading } = useQuery({ queryKey: ["admin-instructors"], queryFn: listAdminInstructorsApi })
  const { data: facilitators } = useQuery({ queryKey: ["admin-facilitators"], queryFn: listAdminFacilitatorsApi })

  const createFacilitator = useMutation({
    mutationFn: () => createFacilitatorApi(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-facilitators"] })
      setFacilitatorOpen(false)
      setForm({ full_name: "", email: "", password: "" })
    },
  })

  if (isLoading) return <Spinner />

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold">Facilitators</h2>
          <Button size="sm" onClick={() => setFacilitatorOpen(true)}><Plus size={14} className="mr-1" /> New facilitator</Button>
        </div>
        <div className="space-y-2">
          {(facilitators ?? []).map((f) => (
            <div key={f.id} className="flex items-center justify-between p-3 rounded-lg border bg-card">
              <p className="text-sm font-medium">{f.full_name}</p>
              <p className="text-xs text-muted-foreground">{f.email}</p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold mb-3">Instructor directory</h2>
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

      <Dialog open={facilitatorOpen} onOpenChange={setFacilitatorOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New facilitator account</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <input className="input" placeholder="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            <input className="input" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <input className="input" placeholder="Temporary password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <Button onClick={() => createFacilitator.mutate()} disabled={!form.email || !form.password || createFacilitator.isPending}>
              {createFacilitator.isPending ? "Creating…" : "Create account"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* ================================================================== */
/* Payments panel                                                       */

function PaymentsPanel() {
  const qc = useQueryClient()
  const importInputRef = useRef<HTMLInputElement>(null)
  const [newLetterOpen, setNewLetterOpen] = useState(false)
  const [selectedInstructor, setSelectedInstructor] = useState("")
  const [importPreview, setImportPreview] = useState<Awaited<ReturnType<typeof bulkImportPreviewApi>> | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)

  const { data: letters, isLoading } = useQuery({ queryKey: ["admin-payment-letters"], queryFn: () => listAdminLettersApi() })
  const { data: instructorOptions } = useQuery({ queryKey: ["payments-instructor-options"], queryFn: paymentsInstructorDropdownApi })
  const { data: certificates } = useQuery({ queryKey: ["admin-certificates"], queryFn: listCertificatesApi })

  const createLetter = useMutation({
    mutationFn: () => createLetterApi({ instructor_user_id: selectedInstructor }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
      setNewLetterOpen(false)
    },
  })

  const generatePdf = useMutation({
    mutationFn: (id: string) => generateLetterPdfApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-payment-letters"] }),
  })
  const publish = useMutation({
    mutationFn: (id: string) => publishLetterApi(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-payment-letters"] }); qc.invalidateQueries({ queryKey: ["admin-overview"] }) },
  })
  const markPaid = useMutation({
    mutationFn: (id: string) => markPaidApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-payment-letters"] }),
  })

  const handlePreview = async (file: File) => {
    setImportFile(file)
    setImportPreview(await bulkImportPreviewApi(file))
  }
  const handleConfirm = useMutation({
    mutationFn: () => bulkImportConfirmApi(importFile!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
      setImportPreview(null)
      setImportFile(null)
    },
  })

  const [manageLetterId, setManageLetterId] = useState<string | null>(null)
  const manageLetter = (letters ?? []).find((l) => l.id === manageLetterId) ?? null
  const [sessionForm, setSessionForm] = useState({ workshop_description: "", role: "Facilitator" as const, compensation_aed: 0 })
  const [addonForm, setAddonForm] = useState({ description: "", amount_aed: 0 })

  const addSession = useMutation({
    mutationFn: () => addSessionApi(manageLetterId!, sessionForm),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
      setSessionForm({ workshop_description: "", role: "Facilitator", compensation_aed: 0 })
    },
  })
  const addAddon = useMutation({
    mutationFn: () => addAddonApi(manageLetterId!, addonForm),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
      setAddonForm({ description: "", amount_aed: 0 })
    },
  })

  if (isLoading) return <Spinner />

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Excel bulk import</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => downloadBulkImportTemplateApi()}>Download template</Button>
            <input
              ref={importInputRef} type="file" accept=".xlsx" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePreview(f) }}
            />
            <Button size="sm" onClick={() => importInputRef.current?.click()}>Choose file…</Button>
          </div>
          {importPreview && (
            <div className="text-sm space-y-1 p-3 rounded-lg border bg-background">
              <p>{importPreview.instructor_count} instructors, {importPreview.session_count} sessions, {importPreview.addon_count} add-ons</p>
              {importPreview.unmatched_emails.length > 0 && (
                <p className="text-destructive">Unmatched emails: {importPreview.unmatched_emails.join(", ")}</p>
              )}
              {importPreview.errors.length > 0 && <p className="text-destructive">{importPreview.errors.join("; ")}</p>}
              <Button size="sm" onClick={() => handleConfirm.mutate()} disabled={handleConfirm.isPending}>
                {handleConfirm.isPending ? "Importing…" : "Confirm import"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold">Payment letters</h2>
          <Button size="sm" onClick={() => setNewLetterOpen(true)}><Plus size={14} className="mr-1" /> New letter</Button>
        </div>
        {(letters ?? []).length === 0 ? (
          <EmptyState title="No payment letters yet" />
        ) : (
          <div className="space-y-2">
            {letters!.map((l) => (
              <div key={l.id} className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-card">
                <button className="text-left" onClick={() => setManageLetterId(l.id)}>
                  <p className="text-sm font-medium hover:underline">{l.instructor_name}</p>
                  <p className="text-xs text-muted-foreground">{l.sessions.length} session(s) · {l.reference}</p>
                </button>
                <div className="flex items-center gap-2">
                  <StatusPill status={l.status} />
                  {!l.pdf_url && <Button size="sm" variant="outline" onClick={() => generatePdf.mutate(l.id)}>Generate PDF</Button>}
                  {l.pdf_url && l.status === "draft" && <Button size="sm" onClick={() => publish.mutate(l.id)}>Publish</Button>}
                  {l.status === "signed" && <Button size="sm" onClick={() => markPaid.mutate(l.id)}>Mark paid</Button>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-sm font-semibold mb-3">Certificates</h2>
        {(certificates ?? []).length === 0 ? (
          <EmptyState title="No certificates generated yet" />
        ) : (
          <div className="space-y-2">
            {certificates!.map((c) => (
              <a key={c.id} href={c.file_url} target="_blank" rel="noreferrer" className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-muted">
                <p className="text-sm">{c.instructor_name} — {c.workshop_name}</p>
                <p className="text-xs text-muted-foreground">{c.workshop_date}</p>
              </a>
            ))}
          </div>
        )}
      </div>

      <Dialog open={newLetterOpen} onOpenChange={setNewLetterOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New payment letter</DialogTitle></DialogHeader>
          <select className="input mb-3" value={selectedInstructor} onChange={(e) => setSelectedInstructor(e.target.value)}>
            <option value="">Select instructor…</option>
            {(instructorOptions ?? []).map((o) => <option key={o.id} value={o.id}>{o.full_name}</option>)}
          </select>
          <Button onClick={() => createLetter.mutate()} disabled={!selectedInstructor || createLetter.isPending}>
            {createLetter.isPending ? "Creating…" : "Create letter"}
          </Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!manageLetterId} onOpenChange={(open) => !open && setManageLetterId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{manageLetter?.instructor_name} — {manageLetter?.reference}</DialogTitle></DialogHeader>
          {manageLetter && (
            <div className="space-y-4">
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-2">Sessions</p>
                <div className="space-y-1 mb-2">
                  {manageLetter.sessions.map((s) => (
                    <p key={s.id} className="text-sm">{s.workshop_description} — {s.role} — AED {s.compensation_aed}</p>
                  ))}
                </div>
                <div className="flex gap-2">
                  <div className="flex-1"><input className="input" placeholder="Workshop description" value={sessionForm.workshop_description}
                    onChange={(e) => setSessionForm({ ...sessionForm, workshop_description: e.target.value })} /></div>
                  <div className="w-24"><input className="input" type="number" placeholder="AED" value={sessionForm.compensation_aed}
                    onChange={(e) => setSessionForm({ ...sessionForm, compensation_aed: Number(e.target.value) })} /></div>
                  <Button size="sm" onClick={() => addSession.mutate()} disabled={!sessionForm.workshop_description || addSession.isPending}>
                    <Plus size={14} />
                  </Button>
                </div>
              </div>

              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-2">Add-ons</p>
                <div className="space-y-1 mb-2">
                  {manageLetter.addons.map((a) => (
                    <p key={a.id} className="text-sm">{a.description} — AED {a.amount_aed}</p>
                  ))}
                </div>
                <div className="flex gap-2">
                  <div className="flex-1"><input className="input" placeholder="Description" value={addonForm.description}
                    onChange={(e) => setAddonForm({ ...addonForm, description: e.target.value })} /></div>
                  <div className="w-24"><input className="input" type="number" placeholder="AED" value={addonForm.amount_aed}
                    onChange={(e) => setAddonForm({ ...addonForm, amount_aed: Number(e.target.value) })} /></div>
                  <Button size="sm" onClick={() => addAddon.mutate()} disabled={!addonForm.description || addAddon.isPending}>
                    <Plus size={14} />
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* ================================================================== */
/* Settings panel                                                       */

function SettingsPanel() {
  const qc = useQueryClient()
  const { data: settings, isLoading } = useQuery({ queryKey: ["admin-settings"], queryFn: getSettingsApi })
  const [signatoryName, setSignatoryName] = useState("")
  const [loaded, setLoaded] = useState(false)

  if (settings && !loaded) {
    setSignatoryName(settings.admin_signatory_name ?? "")
    setLoaded(true)
  }

  const saveSignatory = useMutation({
    mutationFn: () => upsertSettingApi("admin_signatory_name", signatoryName),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-settings"] }),
  })
  const uploadSignature = useMutation({
    mutationFn: (file: File) => uploadAdminSignatureApi(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-settings"] }),
  })

  if (isLoading) return <Spinner />

  return (
    <Card className="max-w-md">
      <CardHeader><CardTitle>Signatory defaults</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1 block">Signatory name</label>
          <input className="input" value={signatoryName} onChange={(e) => setSignatoryName(e.target.value)} />
        </div>
        <Button size="sm" onClick={() => saveSignatory.mutate()} disabled={saveSignatory.isPending}>Save</Button>

        <div className="pt-3 border-t">
          <label className="text-xs font-medium text-muted-foreground mb-1 block">Admin signature image</label>
          <input
            type="file" accept="image/*" className="input"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadSignature.mutate(f) }}
          />
          {settings?.admin_signature_url && (
            <img src={settings.admin_signature_url} alt="Admin signature" className="mt-2 h-12 object-contain" />
          )}
        </div>
      </CardContent>
    </Card>
  )
}
