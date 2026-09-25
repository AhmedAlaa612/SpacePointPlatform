import { useMemo, useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, Banknote, CheckCircle2, Download, FileText, LineChart, MapPin } from "lucide-react"
import {
  downloadBatchInstructorDocumentsZipApi,
  getAdminInstructorBankDetailsApi,
  getAdminInstructorDocumentsComplianceApi,
  listAdminInstructorsApi,
} from "@/api/instructors/admin"
import { downloadUserDocumentsZipApi } from "@/api/admin/users"
import { UserProfileModal } from "@/components/UserProfileModal"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

function InstructorDocumentsDialog({ userId, name, onClose }: { userId: string; name: string; onClose: () => void }) {
  const toast = useToast()
  const [downloading, setDownloading] = useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ["admin-instructor-documents-compliance", userId],
    queryFn: () => getAdminInstructorDocumentsComplianceApi(userId),
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader className="pb-3 border-b">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pr-6">
            <div>
              <DialogTitle className="text-base sm:text-lg">Instructor Documents — {name}</DialogTitle>
              {data && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {data.is_complete ? (
                    <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                      All mandatory documents on file ({data.uploaded_count}/{data.total_required})
                    </span>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-400 font-medium">
                      Missing {data.missing_docs.length} mandatory document{data.missing_docs.length === 1 ? "" : "s"} ({data.uploaded_count}/{data.total_required} uploaded)
                    </span>
                  )}
                  {data.is_uae_resident ? " · UAE Resident" : " · Non-UAE (Visa Exempt)"}
                </p>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={downloading}
              className="shrink-0 self-start sm:self-auto text-xs"
              onClick={async () => {
                try {
                  setDownloading(true)
                  await downloadUserDocumentsZipApi(userId, name)
                  toast.success(`Downloaded documents for ${name}`)
                } catch (err: any) {
                  toast.error(err?.message || "Failed to download documents")
                } finally {
                  setDownloading(false)
                }
              }}
            >
              {downloading ? (
                <span className="w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin mr-1.5" />
              ) : (
                <Download size={13} className="mr-1.5" />
              )}
              Download ZIP
            </Button>
          </div>
        </DialogHeader>

        {isLoading ? (
          <div className="py-8"><Spinner /></div>
        ) : (
          <div className="flex flex-col gap-5 pt-1">
            {/* Mandatory checklist */}
            <div className="flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Mandatory Checklist
                </p>
                <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                  data?.is_complete
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                    : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                }`}>
                  {data?.is_complete ? "All Complete" : `${data?.uploaded_count}/${data?.total_required} Complete`}
                </span>
              </div>

              <div className="space-y-2">
                {data?.checklist?.map((item) => (
                  <div
                    key={item.key}
                    className={`flex items-center justify-between gap-3 p-3 rounded-xl border transition-colors ${
                      item.uploaded
                        ? "bg-emerald-500/5 border-emerald-500/20"
                        : item.exempt
                        ? "bg-muted/30 border-border"
                        : "bg-amber-500/5 border-amber-500/20"
                    }`}
                  >
                    <div className="flex items-start gap-2.5 min-w-0">
                      {item.uploaded ? (
                        <CheckCircle2 size={16} className="text-emerald-500 mt-0.5 shrink-0" />
                      ) : item.exempt ? (
                        <span className="w-4 h-4 mt-0.5 rounded-full bg-muted flex items-center justify-center text-[10px] text-muted-foreground shrink-0">−</span>
                      ) : (
                        <AlertTriangle size={16} className="text-amber-500 mt-0.5 shrink-0" />
                      )}
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-xs font-semibold text-foreground">{item.label}</span>
                          {item.exempt ? (
                            <span className="text-[10px] uppercase font-bold text-muted-foreground px-1.5 py-0.5 rounded bg-muted/60">
                              Exempt (Non-UAE)
                            </span>
                          ) : item.mandatory ? (
                            <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                              item.uploaded ? "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10" : "text-amber-600 dark:text-amber-400 bg-amber-500/10"
                            }`}>
                              {item.uploaded ? "Uploaded" : "Missing"}
                            </span>
                          ) : null}
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-0.5">{item.desc}</p>
                        {item.uploaded_at && (
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            Uploaded {new Date(item.uploaded_at).toLocaleDateString()}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="shrink-0">
                      {item.uploaded && item.file_url ? (
                        <a href={item.file_url} target="_blank" rel="noreferrer">
                          <Button size="sm" variant="ghost" className="h-7 px-2.5 text-xs text-primary hover:text-primary">
                            <FileText size={13} className="mr-1" /> View
                          </Button>
                        </a>
                      ) : item.exempt ? (
                        <span className="text-[11px] text-muted-foreground italic px-2">Optional</span>
                      ) : item.key === "clearance" ? (
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] text-amber-600 dark:text-amber-400 font-medium px-1">Required</span>
                          <a href="/templates/clearance/Clearance_Forms_Templates.zip" download="Clearance_Forms_Templates.zip">
                            <Button size="sm" variant="outline" className="h-6 text-[11px] px-2">
                              <Download size={11} className="mr-1" /> Template
                            </Button>
                          </a>
                        </div>
                      ) : (
                        <span className="text-[11px] text-amber-600 dark:text-amber-400 font-medium px-2">Required</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Other uploaded documents */}
            {data?.other_documents && data.other_documents.length > 0 && (
              <div className="flex flex-col gap-2 pt-2 border-t">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Other Uploaded Documents ({data.other_documents.length})
                </p>
                <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
                  {data.other_documents.map((doc, idx) => {
                    const hasDistinctName = doc.file_name && doc.file_name.toLowerCase() !== doc.document_type.toLowerCase()
                    const displayTitle = hasDistinctName
                      ? doc.file_name
                      : data.other_documents.filter(d => d.document_type === doc.document_type).length > 1
                      ? `${doc.document_type} (${idx + 1})`
                      : doc.document_type

                    return (
                      <div key={doc.id} className="flex items-center justify-between gap-2 p-2.5 rounded-lg border bg-card/40 text-xs">
                        <div className="min-w-0">
                          <p className="font-medium text-foreground truncate">{displayTitle}</p>
                          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground mt-0.5">
                            {hasDistinctName && (
                              <span className="font-medium text-foreground/80">{doc.document_type} ·</span>
                            )}
                            {doc.uploaded_at && (
                              <span>Uploaded {new Date(doc.uploaded_at).toLocaleDateString()}</span>
                            )}
                          </div>
                        </div>
                        {doc.file_url && (
                          <a href={doc.file_url} target="_blank" rel="noreferrer">
                            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs">
                              <FileText size={12} className="mr-1" /> View
                            </Button>
                          </a>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function BankDetailsDialog({ userId, name, onClose }: { userId: string; name: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-instructor-bank-details", userId],
    queryFn: () => getAdminInstructorBankDetailsApi(userId),
  })
  const rows: [string, string | null][] = [
    ["Account holder name", data?.account_holder_name ?? null],
    ["Bank name", data?.bank_name ?? null],
    ["IBAN", data?.iban ?? null],
    ["SWIFT/BIC", data?.swift_bic ?? null],
    ["Bank location", data?.bank_location ?? null],
  ]
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Bank Details — {name}</DialogTitle></DialogHeader>
        {isLoading ? (
          <Spinner />
        ) : (
          <div className="flex flex-col gap-2.5">
            {rows.map(([label, value]) => (
              <div key={label}>
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-0.5">{label}</p>
                <p className="text-sm text-foreground break-all">{value?.trim() || <span className="text-muted-foreground italic">Not set</span>}</p>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

const DOCUMENT_TYPE_OPTIONS = [
  { id: "visa", label: "Residence Visa", desc: "UAE Residency Visa copies" },
  { id: "cv", label: "CV / Resume", desc: "Uploaded CV or Application Resume" },
  { id: "emirates_id", label: "Emirates ID / National ID", desc: "Emirates ID (front/back) or National ID" },
  { id: "passport", label: "Passport", desc: "Passport information page copy" },
  { id: "clearance", label: "Clearance Document", desc: "Police clearance / good conduct certificate" },
  { id: "photo", label: "Personal Picture", desc: "Official photo / headshot" },
  { id: "contract", label: "Contract", desc: "Signed instructor agreement" },
  { id: "payment_letters", label: "Payment Letters", desc: "Signed session payment letters" },
  { id: "other", label: "Other Uploaded Documents", desc: "Any additional uploaded files" },
]

function BatchDownloadModal({
  open,
  onClose,
  selectedCount,
  onDownload,
  downloading,
}: {
  open: boolean
  onClose: () => void
  selectedCount: number
  onDownload: (docTypes: string[], includeGen: boolean) => Promise<void>
  downloading: boolean
}) {
  const [selectedTypes, setSelectedTypes] = useState<string[]>(DOCUMENT_TYPE_OPTIONS.map((d) => d.id))
  const [includeGen, setIncludeGen] = useState(false)

  const toggleType = (id: string) => {
    setSelectedTypes((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const selectAll = () => setSelectedTypes(DOCUMENT_TYPE_OPTIONS.map((d) => d.id))
  const deselectAll = () => setSelectedTypes([])
  const selectVisaAndCv = () => setSelectedTypes(["visa", "cv"])

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !downloading && onClose()}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader className="pb-3 border-b">
          <DialogTitle className="text-base font-bold flex items-center gap-2">
            <Download size={18} className="text-primary" />
            Download Documents ({selectedCount} Instructor{selectedCount === 1 ? "" : "s"})
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            Select the document types to include in the ZIP. Each instructor will have a dedicated folder.
          </p>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Quick presets */}
          <div className="flex items-center justify-between gap-2 flex-wrap text-xs">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Selected ({selectedTypes.length}/{DOCUMENT_TYPE_OPTIONS.length}):
            </span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={selectAll}
                className="text-[11px] text-primary hover:underline font-medium"
              >
                All
              </button>
              <span className="text-muted-foreground">·</span>
              <button
                type="button"
                onClick={deselectAll}
                className="text-[11px] text-muted-foreground hover:text-foreground font-medium"
              >
                None
              </button>
              <span className="text-muted-foreground">·</span>
              <button
                type="button"
                onClick={selectVisaAndCv}
                className="text-[11px] text-primary font-medium hover:underline bg-primary/10 px-1.5 py-0.5 rounded"
              >
                Visa & CV only
              </button>
            </div>
          </div>

          {/* Checklist */}
          <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
            {DOCUMENT_TYPE_OPTIONS.map((opt) => {
              const checked = selectedTypes.includes(opt.id)
              return (
                <label
                  key={opt.id}
                  onClick={(e) => e.stopPropagation()}
                  className={`flex items-start gap-3 p-2.5 rounded-xl border text-xs cursor-pointer transition-colors ${
                    checked
                      ? "bg-primary/5 border-primary/30"
                      : "bg-card/40 border-border hover:bg-muted/40"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleType(opt.id)}
                    className="mt-0.5 rounded border-border text-primary focus:ring-primary h-4 w-4"
                  />
                  <div className="min-w-0 flex-1">
                    <p className={`font-semibold ${checked ? "text-foreground" : "text-muted-foreground"}`}>
                      {opt.label}
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">{opt.desc}</p>
                  </div>
                </label>
              )
            })}
          </div>

          {/* Additional toggles */}
          <div className="pt-2 border-t">
            <label
              onClick={(e) => e.stopPropagation()}
              className="flex items-center gap-2.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
            >
              <input
                type="checkbox"
                checked={includeGen}
                onChange={(e) => setIncludeGen(e.target.checked)}
                className="rounded border-border text-primary focus:ring-primary h-4 w-4"
              />
              <span>Include system-generated certificates & documents</span>
            </label>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t">
          <Button size="sm" variant="ghost" onClick={onClose} disabled={downloading}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={selectedTypes.length === 0 || downloading}
            onClick={() => onDownload(selectedTypes, includeGen)}
            className="gap-1.5"
          >
            {downloading ? (
              <span className="w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin mr-1" />
            ) : (
              <Download size={13} className="mr-1" />
            )}
            Download ZIP {selectedTypes.length > 0 ? `(${selectedTypes.length} types)` : ""}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default function InstructorsAdminInstructors() {
  const navigate = useNavigate()
  const toast = useToast()
  const { data: instructors, isLoading } = useQuery({ queryKey: ["admin-instructors"], queryFn: listAdminInstructorsApi })
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [bankDetailsFor, setBankDetailsFor] = useState<{ id: string; name: string } | null>(null)
  const [documentsFor, setDocumentsFor] = useState<{ id: string; name: string } | null>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [batchDownloading, setBatchDownloading] = useState(false)
  const [batchModalOpen, setBatchModalOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [cityId, setCityId] = useState("")
  const [deliverCityId, setDeliverCityId] = useState("")
  const [bankFilter, setBankFilter] = useState<"" | "missing" | "complete">("")
  const [docFilter, setDocFilter] = useState<"" | "missing" | "complete">("")

  // Options come from the loaded rows rather than /public/cities: the point of
  // these filters is to narrow THIS list, so offering cities no instructor is
  // in would only produce guaranteed-empty results.
  const { cityOptions, deliverOptions } = useMemo(() => {
    const cities = new Map<string, string>()
    const deliver = new Map<string, string>()
    for (const i of instructors ?? []) {
      if (i.city_id && i.city_name) cities.set(i.city_id, i.city_name)
      i.deliver_city_ids.forEach((id, idx) => deliver.set(id, i.deliver_city_names[idx]))
    }
    const byName = (a: [string, string], b: [string, string]) => a[1].localeCompare(b[1])
    return {
      cityOptions: [...cities.entries()].sort(byName),
      deliverOptions: [...deliver.entries()].sort(byName),
    }
  }, [instructors])

  const filteredInstructors = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (instructors ?? []).filter((i) => {
      if (q && !i.full_name.toLowerCase().includes(q)) return false
      if (cityId && i.city_id !== cityId) return false
      // Matched by id, never by name — same rule as staffing city-matching.
      if (deliverCityId && !i.deliver_city_ids.includes(deliverCityId)) return false
      if (bankFilter === "missing" && i.bank_details_complete) return false
      if (bankFilter === "complete" && !i.bank_details_complete) return false
      if (docFilter === "missing" && i.docs_compliance?.is_complete) return false
      if (docFilter === "complete" && !i.docs_compliance?.is_complete) return false
      return true
    })
  }, [instructors, search, cityId, deliverCityId, bankFilter, docFilter])

  const allFilteredIds = useMemo(() => filteredInstructors.map((i) => i.id), [filteredInstructors])
  const isAllSelected = allFilteredIds.length > 0 && allFilteredIds.every((id) => selectedIds.includes(id))

  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedIds([])
    } else {
      setSelectedIds(allFilteredIds)
    }
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const handleBatchDownload = async (docTypes: string[], includeGen: boolean) => {
    if (selectedIds.length === 0) return
    try {
      setBatchDownloading(true)
      await downloadBatchInstructorDocumentsZipApi(selectedIds, includeGen, docTypes)
      toast.success(`Downloaded documents archive for ${selectedIds.length} instructors`)
      setBatchModalOpen(false)
    } catch (err: any) {
      toast.error(err?.message || "Failed to download batch documents")
    } finally {
      setBatchDownloading(false)
    }
  }

  const filtersActive = !!(search.trim() || cityId || deliverCityId || bankFilter || docFilter)

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Instructors" subtitle="Directory of approved instructors." />

      <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name…"
          className="h-9 px-3 w-full sm:w-64 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
        <select
          value={cityId}
          onChange={(e) => setCityId(e.target.value)}
          className="h-9 px-3 w-full sm:w-52 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        >
          <option value="">All cities</option>
          {cityOptions.map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>
        <select
          value={deliverCityId}
          onChange={(e) => setDeliverCityId(e.target.value)}
          className="h-9 px-3 w-full sm:w-60 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        >
          <option value="">Open to work anywhere</option>
          {deliverOptions.map(([id, name]) => (
            <option key={id} value={id}>Open to work in {name}</option>
          ))}
        </select>
        <select
          value={bankFilter}
          onChange={(e) => setBankFilter(e.target.value as "" | "missing" | "complete")}
          className="h-9 px-3 w-full sm:w-52 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        >
          <option value="">Any bank details status</option>
          <option value="missing">Bank details missing</option>
          <option value="complete">Bank details on file</option>
        </select>
        <select
          value={docFilter}
          onChange={(e) => setDocFilter(e.target.value as "" | "missing" | "complete")}
          className="h-9 px-3 w-full sm:w-56 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        >
          <option value="">Any document status</option>
          <option value="complete">All documents complete</option>
          <option value="missing">Missing mandatory documents</option>
        </select>
        {filtersActive && (
          <button
            onClick={() => { setSearch(""); setCityId(""); setDeliverCityId(""); setBankFilter(""); setDocFilter("") }}
            className="h-9 px-3 text-sm text-muted-foreground hover:text-foreground transition-colors self-start sm:self-auto"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Batch selection toolbar */}
      {selectedIds.length > 0 && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 px-4 rounded-xl bg-primary/10 border border-primary/20 text-foreground animate-fade-in">
          <div className="flex items-center gap-2.5">
            <span className="text-sm font-semibold text-primary">
              {selectedIds.length} instructor{selectedIds.length === 1 ? "" : "s"} selected
            </span>
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <Button
              size="sm"
              disabled={batchDownloading}
              onClick={() => setBatchModalOpen(true)}
              className="gap-1.5 shadow-sm flex-1 sm:flex-initial text-xs h-8"
            >
              {batchDownloading ? (
                <span className="w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin mr-1" />
              ) : (
                <Download size={13} className="mr-1" />
              )}
              Download Documents (.zip)
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelectedIds([])}
              className="text-xs text-muted-foreground hover:text-foreground shrink-0 h-8"
            >
              Clear selection
            </Button>
          </div>
        </div>
      )}

      {filteredInstructors.length === 0 ? (
        <EmptyState title={(instructors ?? []).length === 0 ? "No approved instructors yet" : "No instructors match your filters"} />
      ) : (
        <div className="space-y-2.5">
          <div className="flex items-center justify-between px-1 py-1 text-xs text-muted-foreground">
            <label className="flex items-center gap-2 cursor-pointer hover:text-foreground transition-colors select-none">
              <input
                type="checkbox"
                checked={isAllSelected}
                onChange={toggleSelectAll}
                className="w-4 h-4 rounded border-border text-primary focus:ring-primary cursor-pointer accent-primary"
              />
              <span className="font-medium">Select all ({filteredInstructors.length})</span>
            </label>
            <span>Showing {filteredInstructors.length} instructors</span>
          </div>

          {filteredInstructors.map((i) => {
            const isSelected = selectedIds.includes(i.id)
            return (
              <div
                key={i.id}
                role="button"
                tabIndex={0}
                onClick={() => setProfileUserId(i.id)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setProfileUserId(i.id) } }}
                className={`w-full flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 p-3.5 sm:p-4 rounded-xl border text-left transition-colors cursor-pointer ${
                  isSelected
                    ? "bg-primary/5 border-primary/40 shadow-xs"
                    : "bg-card border-border hover:border-muted-foreground/30"
                }`}
              >
                {/* Main info section */}
                <div className="flex items-start gap-3 min-w-0 flex-1">
                  <label
                    className="flex items-center shrink-0 pt-0.5 cursor-pointer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(i.id)}
                      className="w-4 h-4 rounded border-border text-primary focus:ring-primary cursor-pointer accent-primary"
                    />
                  </label>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-foreground truncate">{i.full_name}</p>
                      <div className="lg:hidden shrink-0">
                        <StatusPill status={i.status} />
                      </div>
                    </div>
                    <p className="text-xs text-muted-foreground truncate">{i.email}</p>

                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 mt-2 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1 shrink-0 whitespace-nowrap">
                        <MapPin size={11} className="shrink-0" />
                        {i.city_name ?? <span className="italic">No city</span>}
                      </span>
                      {i.deliver_city_names.length > 0 && (
                        <span className="shrink-0 whitespace-nowrap">
                          · Works in {i.deliver_city_names.join(", ")}
                        </span>
                      )}
                      {i.bank_details_complete ? (
                        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 shrink-0 whitespace-nowrap">
                          <CheckCircle2 size={11} className="shrink-0" /> Bank details on file
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 shrink-0 whitespace-nowrap">
                          <AlertTriangle size={11} className="shrink-0" /> Bank details missing
                        </span>
                      )}
                      {i.docs_compliance ? (
                        i.docs_compliance.is_complete ? (
                          <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 shrink-0 whitespace-nowrap">
                            <CheckCircle2 size={11} className="shrink-0" /> Docs complete
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 shrink-0 whitespace-nowrap">
                            <AlertTriangle size={11} className="shrink-0" /> Missing {i.docs_compliance.missing_docs.length} docs
                          </span>
                        )
                      ) : null}
                    </div>
                  </div>
                </div>

                {/* Actions row */}
                <div className="flex flex-wrap lg:flex-nowrap items-center gap-2 pt-2.5 lg:pt-0 border-t border-border/40 lg:border-0 shrink-0">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs flex-1 sm:flex-initial justify-center"
                    onClick={(e) => { e.stopPropagation(); void navigate({ to: `/instructors/admin/instructors/${i.id}/performance` }) }}
                  >
                    <LineChart size={13} className="mr-1.5 shrink-0" />
                    <span>Performance</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs flex-1 sm:flex-initial justify-center"
                    onClick={(e) => { e.stopPropagation(); setBankDetailsFor({ id: i.id, name: i.full_name }) }}
                  >
                    <Banknote size={13} className="mr-1.5 shrink-0" />
                    <span className="hidden sm:inline">View bank details</span>
                    <span className="sm:hidden">Bank details</span>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className={`h-8 text-xs flex-1 sm:flex-initial justify-center ${
                      i.docs_compliance?.is_complete
                        ? "text-emerald-600 dark:text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
                        : "text-amber-600 dark:text-amber-400 border-amber-500/30 hover:bg-amber-500/10"
                    }`}
                    title="View documents & compliance checklist"
                    onClick={(e) => {
                      e.stopPropagation()
                      setDocumentsFor({ id: i.id, name: i.full_name })
                    }}
                  >
                    <FileText size={13} className="mr-1.5 shrink-0" />
                    <span className="hidden sm:inline">View documents</span>
                    <span className="sm:hidden">Documents</span>
                  </Button>
                  <div className="hidden lg:block shrink-0">
                    <StatusPill status={i.status} />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
      {bankDetailsFor && (
        <BankDetailsDialog
          userId={bankDetailsFor.id}
          name={bankDetailsFor.name}
          onClose={() => setBankDetailsFor(null)}
        />
      )}
      {documentsFor && (
        <InstructorDocumentsDialog
          userId={documentsFor.id}
          name={documentsFor.name}
          onClose={() => setDocumentsFor(null)}
        />
      )}
      {batchModalOpen && (
        <BatchDownloadModal
          open={batchModalOpen}
          onClose={() => setBatchModalOpen(false)}
          selectedCount={selectedIds.length}
          onDownload={handleBatchDownload}
          downloading={batchDownloading}
        />
      )}
    </div>
  )
}
