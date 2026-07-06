import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Plus, Trash2 } from "lucide-react"
import {
  addAddonApi, addSessionApi, bulkImportConfirmApi, bulkImportPreviewApi, createBatchApi, createLetterApi,
  deleteBatchApi, deleteLetterApi, downloadBulkImportTemplateApi, generateLetterPdfApi, listAdminLettersApi,
  listBatchesApi, markPaidApi, paymentsInstructorDropdownApi, publishLetterApi,
} from "@/api/instructors/payments_admin"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"
import { UserProfileModal } from "@/components/UserProfileModal"

export default function InstructorsAdminPayments() {
  const qc = useQueryClient()
  const importInputRef = useRef<HTMLInputElement>(null)
  const [newLetterOpen, setNewLetterOpen] = useState(false)
  const [selectedInstructor, setSelectedInstructor] = useState("")
  const [importPreview, setImportPreview] = useState<Awaited<ReturnType<typeof bulkImportPreviewApi>> | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [selectedBatch, setSelectedBatch] = useState("")   // new-letter batch assignment
  const [importBatch, setImportBatch] = useState("")       // bulk-import batch assignment
  const [batchFilter, setBatchFilter] = useState("all")    // letters list filter
  const [newBatchName, setNewBatchName] = useState("")
  const [newBatchDesc, setNewBatchDesc] = useState("")

  const { data: letters, isLoading } = useQuery({ queryKey: ["admin-payment-letters"], queryFn: () => listAdminLettersApi() })
  const { data: instructorOptions } = useQuery({ queryKey: ["payments-instructor-options"], queryFn: paymentsInstructorDropdownApi })
  const { data: batches } = useQuery({ queryKey: ["admin-payment-batches"], queryFn: listBatchesApi })

  const createLetter = useMutation({
    mutationFn: () => createLetterApi({ instructor_user_id: selectedInstructor, batch_id: selectedBatch || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
      qc.invalidateQueries({ queryKey: ["admin-payment-batches"] })
      setNewLetterOpen(false)
      setSelectedBatch("")
    },
  })

  const createBatch = useMutation({
    mutationFn: () => createBatchApi({ name: newBatchName, description: newBatchDesc || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-payment-batches"] })
      setNewBatchName(""); setNewBatchDesc("")
    },
  })
  const removeBatch = useMutation({
    mutationFn: (id: string) => deleteBatchApi(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-payment-batches"] })
      qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
    },
  })
  const removeLetter = useMutation({
    mutationFn: (id: string) => deleteLetterApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-payment-letters"] }),
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
    mutationFn: () => bulkImportConfirmApi(importFile!, importBatch || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
      qc.invalidateQueries({ queryKey: ["admin-payment-batches"] })
      setImportPreview(null)
      setImportFile(null)
      setImportBatch("")
    },
  })

  const [manageLetterId, setManageLetterId] = useState<string | null>(null)
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
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

  const allLetters = letters ?? []
  const letterTotal = (l: (typeof allLetters)[number]) =>
    l.sessions.reduce((s, x) => s + (x.compensation_aed || 0), 0) + l.addons.reduce((s, x) => s + (x.amount_aed || 0), 0)
  const shownLetters = batchFilter === "all"
    ? allLetters
    : batchFilter === "none"
      ? allLetters.filter((l) => !l.batch_id)
      : allLetters.filter((l) => l.batch_id === batchFilter)

  const summary = {
    paid: allLetters.filter((l) => l.status === "paid").reduce((s, l) => s + letterTotal(l), 0),
    pending: allLetters.filter((l) => l.status === "signed").reduce((s, l) => s + letterTotal(l), 0),
    awaitingSignature: allLetters.filter((l) => l.status === "published").length,
    sessions: allLetters.reduce((s, l) => s + l.sessions.length, 0),
    hours: allLetters.reduce((s, l) => s + l.sessions.reduce((h, x) => h + (x.duration_hours || 0), 0), 0),
  }
  const summaryTiles = [
    { label: "Total Spent (Paid)", value: `AED ${summary.paid.toLocaleString()}` },
    { label: "Pending Payment", value: `AED ${summary.pending.toLocaleString()}` },
    { label: "Awaiting Signature", value: summary.awaitingSignature },
    { label: "Total Sessions", value: summary.sessions },
    { label: "Total Hours", value: summary.hours },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Payments" subtitle="Payment letters, batches, and bulk import." />

      {/* Summary stat cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {summaryTiles.map((t) => (
          <div key={t.label} className="rounded-xl bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t.label}</p>
            <p className="mt-1 font-display text-xl font-bold text-foreground">{t.value}</p>
          </div>
        ))}
      </div>

      {/* Payment cohorts (batches) */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold">Payment batches <span className="text-muted-foreground font-normal">(cohorts)</span></h2>
        </div>
        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex-1"><input className="input" placeholder="New batch name (e.g. Nov 2026)" value={newBatchName} onChange={(e) => setNewBatchName(e.target.value)} /></div>
              <div className="flex-1"><input className="input" placeholder="Description (optional)" value={newBatchDesc} onChange={(e) => setNewBatchDesc(e.target.value)} /></div>
              <Button onClick={() => createBatch.mutate()} disabled={!newBatchName || createBatch.isPending}>
                <Plus size={14} className="mr-1" /> New batch
              </Button>
            </div>
            {(batches ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No batches yet. Create one to group payment letters into a cohort.</p>
            ) : (
              <div className="space-y-2">
                {batches!.map((b) => (
                  <div key={b.id} className="flex items-center justify-between gap-3 p-2.5 rounded-lg border border-border/60 bg-card/40">
                    <div>
                      <p className="text-sm font-medium">{b.name}</p>
                      <p className="text-xs text-muted-foreground">{b.letter_count} letter(s){b.description ? ` · ${b.description}` : ""}</p>
                    </div>
                    <button onClick={() => removeBatch.mutate(b.id)} className="p-2 text-muted-foreground hover:text-destructive" title="Delete batch">
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

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
              <div className="flex items-center gap-2 pt-1">
                <div className="flex-1">
                  <select className="input" value={importBatch} onChange={(e) => setImportBatch(e.target.value)}>
                    <option value="">No batch</option>
                    {(batches ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                  </select>
                </div>
                <Button size="sm" onClick={() => handleConfirm.mutate()} disabled={handleConfirm.isPending}>
                  {handleConfirm.isPending ? "Importing…" : "Confirm import"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <div>
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <h2 className="text-sm font-semibold">Payment letters</h2>
          <div className="flex items-center gap-2">
            <div className="w-44">
              <select className="input" value={batchFilter} onChange={(e) => setBatchFilter(e.target.value)}>
                <option value="all">All batches</option>
                <option value="none">No batch</option>
                {(batches ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
            <Button size="sm" onClick={() => setNewLetterOpen(true)}><Plus size={14} className="mr-1" /> New letter</Button>
          </div>
        </div>
        {shownLetters.length === 0 ? (
          <EmptyState title="No payment letters yet" />
        ) : (
          <div className="space-y-2">
            {shownLetters.map((l) => {
              const batchName = batches?.find((b) => b.id === l.batch_id)?.name
              return (
              <div key={l.id} className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-card">
                <div className="text-left">
                  <div className="flex items-center gap-2">
                    <button className="text-sm font-medium hover:underline" onClick={() => setManageLetterId(l.id)}>
                      {l.instructor_name}
                    </button>
                    {l.instructor_user_id && (
                      <button
                        onClick={() => setProfileUserId(l.instructor_user_id!)}
                        className="text-xs text-muted-foreground hover:text-primary transition-colors"
                      >
                        View profile →
                      </button>
                    )}
                    {batchName && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">{batchName}</span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{l.sessions.length} session(s) · AED {letterTotal(l).toLocaleString()} · {l.reference}</p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill status={l.status} />
                  {(l.pdf_url || l.signed_pdf_url) && (
                    <a href={l.signed_pdf_url ?? l.pdf_url ?? undefined} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="outline">
                        <Download size={14} className="mr-1.5" />
                        {l.status === "signed" || l.status === "paid" ? "View signed" : "View draft"}
                      </Button>
                    </a>
                  )}
                  {!l.pdf_url && <Button size="sm" variant="outline" onClick={() => generatePdf.mutate(l.id)}>Generate PDF</Button>}
                  {l.pdf_url && l.status === "draft" && <Button size="sm" onClick={() => publish.mutate(l.id)}>Publish</Button>}
                  {l.status === "signed" && <Button size="sm" onClick={() => markPaid.mutate(l.id)}>Mark paid</Button>}
                  {l.status === "draft" && (
                    <button onClick={() => removeLetter.mutate(l.id)} className="p-2 text-muted-foreground hover:text-destructive" title="Delete letter">
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              </div>
              )
            })}
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
          <select className="input mb-3" value={selectedBatch} onChange={(e) => setSelectedBatch(e.target.value)}>
            <option value="">No batch</option>
            {(batches ?? []).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <Button onClick={() => createLetter.mutate()} disabled={!selectedInstructor || createLetter.isPending}>
            {createLetter.isPending ? "Creating…" : "Create letter"}
          </Button>
        </DialogContent>
      </Dialog>

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}

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
