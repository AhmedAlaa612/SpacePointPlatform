import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Download,
  FileText,
  FileSignature,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Send,
  Trash2,
  UploadCloud,
  Briefcase,
} from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import {
  listDocumentsApi,
  uploadDocumentApi,
  deleteDocumentApi,
  getMyDocumentsApi,
  getMyDocumentRequestsApi,
  createDocumentRequestApi,
  getAvailableTemplatesApi,
} from "@/api/documents"
import { getProfileApi, signContractApi } from "@/api/instructors/instructor"
import {
  createRoleRequestApi,
  getMyRoleRequestsApi,
  getMyInternshipLetterApi,
  signInternshipLetterApi,
} from "@/api/internship"
import { fetchPublicCities } from "@/api/lms"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { SignaturePad } from "@/pages/instructors/components/SignaturePad"

const DOC_TYPES = ["ID Card", "Passport", "Personal Picture", "Contract", "Visa", "CV", "Other"]

const CHECKLIST: { type: string; desc: string }[] = [
  { type: "ID Card", desc: "UAE Emirates ID (front & back copy) or National ID card." },
  { type: "Passport", desc: "High-quality copy of your passport information page." },
  { type: "Personal Picture", desc: "Professional high-resolution headshot for portal." },
  { type: "Contract", desc: "Signed copy of your SpacePoint Instructor contract." },
  { type: "Visa", desc: "UAE Residency Visa copy (if applicable)." },
  { type: "CV", desc: "Your latest professional CV or resume." },
]

// Mirrors backend/app/services/internship/allowed_role_requests.py — which
// current roles can request which additional role. The backend is the real
// gate; this only decides whether to show the "Apply" button at all.
const ALLOWED_ROLE_REQUESTS: Record<string, string[]> = {
  instructor: ["intern"],
}

export default function PersonalDocuments() {
  const { activeRole, roles } = useAuth()
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)

  // Only instructors get the personal-document vault — everyone else just requests documents.
  const canUseVault = activeRole === "instructor"
  const requestableRoles = ALLOWED_ROLE_REQUESTS[activeRole ?? ""] ?? []

  // ── Vault state ──────────────────────────────────────────────
  const [docType, setDocType] = useState(DOC_TYPES[0])
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [dragActive, setDragActive] = useState(false)

  // ── Request state ────────────────────────────────────────────
  const [selectedTemplate, setSelectedTemplate] = useState("")
  const [requestNotes, setRequestNotes] = useState("")
  const [requestForRole, setRequestForRole] = useState(activeRole ?? "")
  const [requestSuccess, setRequestSuccess] = useState(false)

  // ── Contract signing state (instructors) ────────────────────
  const [signingContract, setSigningContract] = useState(false)

  // ── Internship letter signing state (interns) ────────────────
  const [signingInternshipLetter, setSigningInternshipLetter] = useState(false)

  // ── Apply-for-internship state (instructors) ─────────────────
  const [applying, setApplying] = useState(false)
  const [universityId, setUniversityId] = useState("")
  const [preferredCityId, setPreferredCityId] = useState("")
  const [requestedStartDate, setRequestedStartDate] = useState("")
  const [requestedDurationWeeks, setRequestedDurationWeeks] = useState("")

  // ── Queries ──────────────────────────────────────────────────
  const { data: vaultDocs = [], isLoading: loadingVault } = useQuery({
    queryKey: ["personal-documents"],
    queryFn: listDocumentsApi,
    enabled: canUseVault,
  })

  const { data: instructorProfile } = useQuery({
    queryKey: ["instructor-profile"],
    queryFn: getProfileApi,
    enabled: canUseVault,
  })

  const { data: internLetter } = useQuery({
    queryKey: ["my-internship-letter"],
    queryFn: getMyInternshipLetterApi,
    enabled: activeRole === "intern",
  })

  const { data: myRoleRequests = [] } = useQuery({
    queryKey: ["my-role-requests"],
    queryFn: getMyRoleRequestsApi,
    enabled: requestableRoles.length > 0,
  })

  const { data: cities = [] } = useQuery({
    queryKey: ["public-cities"],
    queryFn: fetchPublicCities,
    enabled: applying,
  })

  const { data: myDocs, isLoading: loadingDocs } = useQuery({
    queryKey: ["my-documents"],
    queryFn: getMyDocumentsApi,
  })

  const { data: myRequests = [], isLoading: loadingRequests } = useQuery({
    queryKey: ["my-document-requests"],
    queryFn: getMyDocumentRequestsApi,
  })

  const { data: templates = [], isLoading: loadingTemplates } = useQuery({
    queryKey: ["available-templates", requestForRole],
    queryFn: () => getAvailableTemplatesApi(requestForRole || ""),
    enabled: !!requestForRole,
  })

  // ── Mutations ────────────────────────────────────────────────
  const upload = useMutation({
    mutationFn: () => uploadDocumentApi(docType, selectedFile!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["personal-documents"] })
      setSelectedFile(null)
      if (fileRef.current) fileRef.current.value = ""
    },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to upload document."),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteDocumentApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["personal-documents"] }),
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to delete document."),
  })

  const signContract = useMutation({
    mutationFn: (signature: string) => signContractApi(signature),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-profile"] })
      setSigningContract(false)
    },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to sign contract."),
  })

  const signInternshipLetter = useMutation({
    mutationFn: (signature: string) => signInternshipLetterApi(signature),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-internship-letter"] })
      setSigningInternshipLetter(false)
    },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to sign internship letter."),
  })

  const applyForInternship = useMutation({
    mutationFn: () =>
      createRoleRequestApi({
        target_role: "intern",
        details: {
          university_id_number: universityId.trim() || undefined,
          preferred_city_id: preferredCityId || undefined,
          requested_start_date: requestedStartDate || undefined,
          requested_duration_weeks: requestedDurationWeeks ? Number(requestedDurationWeeks) : undefined,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-role-requests"] })
      setApplying(false)
      setUniversityId("")
      setPreferredCityId("")
      setRequestedStartDate("")
      setRequestedDurationWeeks("")
    },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to submit internship request."),
  })

  const submitRequest = useMutation({
    mutationFn: () =>
      createDocumentRequestApi({
        type: selectedTemplate,
        requested_role: requestForRole || undefined,
        notes: requestNotes.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-document-requests"] })
      setRequestNotes("")
      setSelectedTemplate("")
      setRequestSuccess(true)
      setTimeout(() => setRequestSuccess(false), 3000)
    },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to submit request"),
  })

  // ── Received documents list ──────────────────────────────────
  const receivedItems = [
    ...(myDocs?.certificates ?? []).map((c) => ({
      id: c.id,
      label:
        c.type === "instructor_completion"
          ? "Instructor Program Completion Certificate"
          : c.type === "internship_completion"
          ? "Internship Completion Certificate"
          : "Workshop Facilitator Certificate",
      url: c.file_url,
      date: c.generated_at || new Date().toISOString(),
    })),
    ...(myDocs?.documents ?? []).map((d) => ({
      id: d.id,
      label: d.label,
      url: d.file_url,
      date: d.generated_at,
    })),
  ].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())

  const statusColor: Record<string, string> = {
    pending:
      "text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-950/20 border-amber-200/50 dark:border-amber-900/30",
    approved:
      "text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-950/20 border-emerald-200/50 dark:border-emerald-900/30",
    rejected:
      "text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-950/20 border-red-200/50 dark:border-red-900/30",
  }

  const handleFile = (f: File | undefined) => {
    if (f) setSelectedFile(f)
  }

  const handleRequestSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTemplate) return
    submitRequest.mutate()
  }

  const pendingInternshipRequest = myRoleRequests.find((r) => r.target_role === "intern" && r.status === "pending")
  const lastRejectedInternshipRequest = myRoleRequests
    .filter((r) => r.target_role === "intern" && r.status === "rejected")
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0]

  return (
    <div className="flex flex-col gap-8 max-w-6xl mx-auto">
      <div className="hidden md:block border-b border-border pb-6">
        <h1 className="font-display text-3xl font-bold text-foreground mb-2">Personal Documents</h1>
        <p className="text-muted-foreground text-sm">
          Upload and manage your personal documents, request certificates or confirmation letters,
          and download documents issued to you.
        </p>
      </div>

      {/* ── Apply for an additional role (e.g. instructor -> intern) ─── */}
      {requestableRoles.length > 0 && (
        <Card className="rounded-2xl">
          <CardHeader className="pb-3 border-b border-border/50">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <Briefcase size={16} className="text-primary" />
              Apply for an Internship
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {pendingInternshipRequest ? (
              <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400 bg-amber-500/5 border border-amber-500/10 p-3 rounded-xl">
                <AlertCircle size={14} className="shrink-0" />
                <span>Your internship request is pending admin review.</span>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {lastRejectedInternshipRequest && (
                  <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/5 border border-red-500/10 p-3 rounded-xl">
                    <strong>Your last request was not approved.</strong>
                    {lastRejectedInternshipRequest.admin_notes && (
                      <p className="mt-1">{lastRejectedInternshipRequest.admin_notes}</p>
                    )}
                  </div>
                )}
                <p className="text-sm text-muted-foreground">
                  Request the intern role in addition to your current one — an admin will review it and
                  generate your internship letter for signature.
                </p>
                <Button size="sm" className="self-start" onClick={() => setApplying(true)}>
                  Apply for Internship
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Facilitator Agreement Contract (instructors only) ────────── */}
      {canUseVault && instructorProfile?.contract_url && (
        <Card className="rounded-2xl">
          <CardHeader className="pb-3 border-b border-border/50">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <FileSignature size={16} className="text-primary" />
              Facilitator Agreement Contract
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                {instructorProfile.contract_signed_at ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 size={13} /> Signed
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-600 dark:text-amber-400">
                    <AlertCircle size={13} /> Awaiting your signature
                  </span>
                )}
                {instructorProfile.contract_signed_at && (
                  <span className="text-xs text-muted-foreground">
                    Signed {new Date(instructorProfile.contract_signed_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <a href={instructorProfile.signed_contract_url ?? instructorProfile.contract_url ?? "#"} target="_blank" rel="noreferrer">
                  <Button size="sm" variant="outline"><Download size={14} className="mr-1.5" /> View Contract</Button>
                </a>
                {!instructorProfile.contract_signed_at && (
                  <Button size="sm" onClick={() => setSigningContract(true)}>Sign Contract</Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Internship Letter (interns only) ─────────────────────────── */}
      {activeRole === "intern" && internLetter?.letter_url && (
        <Card className="rounded-2xl">
          <CardHeader className="pb-3 border-b border-border/50">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <FileSignature size={16} className="text-primary" />
              Internship Letter
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                {internLetter.letter_signed_at ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 size={13} /> Signed
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-600 dark:text-amber-400">
                    <AlertCircle size={13} /> Awaiting your signature
                  </span>
                )}
                {internLetter.letter_signed_at && (
                  <span className="text-xs text-muted-foreground">
                    Signed {new Date(internLetter.letter_signed_at).toLocaleDateString()}
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                <a href={internLetter.signed_letter_url ?? internLetter.letter_url ?? "#"} target="_blank" rel="noreferrer">
                  <Button size="sm" variant="outline"><Download size={14} className="mr-1.5" /> View Letter</Button>
                </a>
                {!internLetter.letter_signed_at && (
                  <Button size="sm" onClick={() => setSigningInternshipLetter(true)}>Sign Letter</Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Upload Personal Document (vault — instructors only) ──────── */}
      {canUseVault && (
        <Card className="rounded-2xl">
          <CardContent className="p-6 sm:p-8 flex flex-col gap-8">
            <div>
              <h3 className="font-display font-bold text-xl text-foreground mb-1.5">
                Upload Personal Document
              </h3>
              <p className="text-sm text-muted-foreground">
                Select a document type, choose or drop your file, and upload it to your library.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
              {/* Left: type + checklist */}
              <div className="lg:col-span-2 flex flex-col gap-4">
                <div>
                  <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-2 font-semibold">
                    Document Type
                  </label>
                  <select
                    value={docType}
                    onChange={(e) => setDocType(e.target.value)}
                    className="w-full bg-background border border-border rounded-xl px-4 py-3 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
                  >
                    {DOC_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="bg-primary/5 border border-primary/15 rounded-2xl p-5 flex flex-col gap-3">
                  <h4 className="text-[11px] uppercase tracking-wider text-primary font-bold">
                    Required Documents Checklist
                  </h4>
                  <ul className="flex flex-col gap-3 text-xs text-muted-foreground">
                    {CHECKLIST.map((c) => (
                      <li key={c.type} className="flex items-start gap-2">
                        <span className="text-primary mt-0.5">•</span>
                        <div>
                          <strong className="text-foreground">{c.type}:</strong> {c.desc}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Right: drop zone */}
              <div className="lg:col-span-3">
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    if (selectedFile) upload.mutate()
                  }}
                  className="flex flex-col gap-4"
                >
                  <div>
                    <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-2 font-semibold">
                      File Upload
                    </label>
                    <div
                      onClick={() => fileRef.current?.click()}
                      onDragOver={(e) => {
                        e.preventDefault()
                        setDragActive(true)
                      }}
                      onDragLeave={(e) => {
                        e.preventDefault()
                        setDragActive(false)
                      }}
                      onDrop={(e) => {
                        e.preventDefault()
                        setDragActive(false)
                        handleFile(e.dataTransfer.files?.[0])
                      }}
                      className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all flex flex-col justify-center items-center h-48 bg-background/40 ${
                        dragActive ? "border-primary/60 bg-primary/5" : "border-border hover:border-primary/40"
                      }`}
                    >
                      <UploadCloud className="w-11 h-11 text-muted-foreground/50 mb-3" />
                      {selectedFile ? (
                        <p className="text-sm font-semibold text-primary">
                          {selectedFile.name}{" "}
                          <span className="text-muted-foreground font-normal">
                            ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
                          </span>
                        </p>
                      ) : (
                        <>
                          <p className="text-foreground/80 font-medium text-sm">
                            Drag and drop file here, or click to browse
                          </p>
                          <p className="text-muted-foreground/70 text-xs mt-1">
                            Supports PDF, JPG, JPEG, PNG, DOC, DOCX (max 10MB)
                          </p>
                        </>
                      )}
                      <input
                        ref={fileRef}
                        type="file"
                        className="hidden"
                        onChange={(e) => handleFile(e.target.files?.[0])}
                      />
                    </div>
                  </div>

                  <Button
                    type="submit"
                    disabled={!selectedFile || upload.isPending}
                    className="w-full h-11 gap-2"
                  >
                    {upload.isPending ? (
                      <>
                        <RefreshCw size={16} className="animate-spin" /> Uploading…
                      </>
                    ) : (
                      <>
                        <UploadCloud size={16} /> Upload Document
                      </>
                    )}
                  </Button>
                </form>
              </div>
            </div>

            {/* Vault table */}
            <div className="border-t border-border pt-6">
              <h3 className="font-display font-bold text-foreground mb-4">Your Documents</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-3 px-4 font-medium">Document Type</th>
                      <th className="py-3 px-4 font-medium">Filename</th>
                      <th className="py-3 px-4 font-medium">Uploaded At</th>
                      <th className="py-3 px-4 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {loadingVault ? (
                      <tr>
                        <td colSpan={4} className="py-8 text-center text-muted-foreground">
                          Loading documents…
                        </td>
                      </tr>
                    ) : vaultDocs.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="py-8 text-center text-muted-foreground">
                          No personal documents uploaded yet.
                        </td>
                      </tr>
                    ) : (
                      vaultDocs.map((doc) => {
                        const filename = doc.file_url.split("/").pop()?.split("?")[0] ?? "document"
                        return (
                          <tr key={doc.id} className="hover:bg-foreground/5 transition-colors">
                            <td className="py-4 px-4 font-medium text-foreground">
                              {doc.document_type}
                            </td>
                            <td
                              className="py-4 px-4 text-muted-foreground truncate max-w-[200px]"
                              title={decodeURIComponent(filename)}
                            >
                              {decodeURIComponent(filename)}
                            </td>
                            <td className="py-4 px-4 text-muted-foreground">
                              {new Date(doc.uploaded_at).toLocaleString()}
                            </td>
                            <td className="py-4 px-4 text-right whitespace-nowrap">
                              <a
                                href={doc.file_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline mr-3"
                              >
                                <Download size={13} /> Download
                              </a>
                              <button
                                onClick={() => {
                                  if (confirm("Delete this document?")) remove.mutate(doc.id)
                                }}
                                disabled={remove.isPending}
                                className="inline-flex items-center gap-1 text-xs font-semibold text-red-500 hover:underline"
                              >
                                <Trash2 size={13} /> Delete
                              </button>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Dialog open={signingContract} onOpenChange={(open) => !open && setSigningContract(false)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Sign Facilitator Agreement Contract</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground mb-3">
            By signing, you confirm agreement to the terms of your SpacePoint Instructor Agreement.
          </p>
          <SignaturePad onSign={(sig) => signContract.mutate(sig)} signing={signContract.isPending} />
        </DialogContent>
      </Dialog>

      <Dialog open={signingInternshipLetter} onOpenChange={(open) => !open && setSigningInternshipLetter(false)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Sign Internship Letter</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground mb-3">
            By signing, you confirm acceptance of your SpacePoint internship offer.
          </p>
          <SignaturePad onSign={(sig) => signInternshipLetter.mutate(sig)} signing={signInternshipLetter.isPending} />
        </DialogContent>
      </Dialog>

      <Dialog open={applying} onOpenChange={(open) => !open && setApplying(false)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Apply for Internship</DialogTitle></DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              applyForInternship.mutate()
            }}
            className="flex flex-col gap-4"
          >
            <div>
              <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                University ID Number
              </label>
              <input
                type="text"
                value={universityId}
                onChange={(e) => setUniversityId(e.target.value)}
                className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                Which city do you want to work at?
              </label>
              <select
                value={preferredCityId}
                onChange={(e) => setPreferredCityId(e.target.value)}
                className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
              >
                <option value="">Select a city...</option>
                {cities.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                  Preferred Start Date
                </label>
                <input
                  type="date"
                  value={requestedStartDate}
                  onChange={(e) => setRequestedStartDate(e.target.value)}
                  className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                  Duration (weeks)
                </label>
                <input
                  type="number"
                  min={1}
                  value={requestedDurationWeeks}
                  onChange={(e) => setRequestedDurationWeeks(e.target.value)}
                  className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              An admin reviews every field above and can adjust them before approving — this is a
              request, not a final assignment.
            </p>
            <Button type="submit" disabled={applyForInternship.isPending} className="w-full h-10 gap-1.5">
              {applyForInternship.isPending ? (
                <>
                  <RefreshCw size={14} className="animate-spin" /> Submitting…
                </>
              ) : (
                "Submit Request"
              )}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* ── Received Documents + Requests ───────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Received Documents */}
          <Card className="rounded-2xl">
            <CardHeader className="pb-3 border-b border-border/50">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                <FileText size={16} className="text-primary" />
                Received Documents
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {loadingDocs ? (
                <div className="flex items-center justify-center p-8">
                  <RefreshCw className="w-5 h-5 animate-spin text-primary" />
                </div>
              ) : receivedItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-8 text-center bg-muted/10 rounded-2xl border border-dashed border-border">
                  <AlertCircle className="w-8 h-8 text-muted-foreground/40 mb-2" />
                  <p className="text-sm font-medium text-foreground">No generated documents yet</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Documents will appear here once approved by admins.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {receivedItems.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-center justify-between p-4 rounded-xl border border-border bg-muted/10 hover:border-muted-foreground/30 transition-colors"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                          <FileText size={18} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-foreground truncate">{item.label}</p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            Issued on {new Date(item.date).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        className="p-2 border border-border hover:bg-muted text-muted-foreground hover:text-foreground rounded-xl transition-all flex items-center justify-center shrink-0"
                        title="Download Document"
                      >
                        <Download size={14} />
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Request History */}
          <Card className="rounded-2xl">
            <CardHeader className="pb-3 border-b border-border/50">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                <FileText size={16} className="text-primary" />
                Request History
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {loadingRequests ? (
                <div className="flex items-center justify-center p-8">
                  <RefreshCw className="w-5 h-5 animate-spin text-primary" />
                </div>
              ) : myRequests.length === 0 ? (
                <div className="text-center p-8 bg-muted/10 rounded-2xl border border-dashed border-border">
                  <p className="text-sm text-muted-foreground/75 italic">No requests submitted yet</p>
                </div>
              ) : (
                <div className="flex flex-col gap-3 max-h-[360px] overflow-y-auto pr-1">
                  {myRequests.map((req) => (
                    <div
                      key={req.id}
                      className="p-3.5 bg-muted/20 border border-border/80 rounded-xl flex flex-col gap-1.5 text-xs transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-foreground text-sm">
                          {templates.find((t) => t.key === req.type)?.name ||
                            req.type.replace(/_/g, " ").toUpperCase()}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded-full border text-[10px] capitalize font-semibold tracking-wider ${statusColor[req.status]}`}
                        >
                          {req.status}
                        </span>
                      </div>
                      {req.notes && (
                        <p className="text-muted-foreground bg-muted/30 p-2 rounded-lg italic border border-border/40 mt-0.5">
                          "{req.notes}"
                        </p>
                      )}
                      {req.admin_notes && (
                        <div className="text-red-600 dark:text-red-400 bg-red-500/5 border border-red-500/10 p-2 rounded-lg mt-0.5">
                          <strong>Admin Feedback:</strong> {req.admin_notes}
                        </div>
                      )}
                      <span className="text-[10px] text-muted-foreground/60 mt-1 self-start">
                        Requested on {new Date(req.created_at).toLocaleDateString()} at{" "}
                        {new Date(req.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Request New Document */}
        <div className="flex flex-col gap-6">
          <Card className="rounded-2xl">
            <CardHeader className="pb-3 border-b border-border/50">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                <Send size={15} className="text-primary" />
                Request New Document
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              <form onSubmit={handleRequestSubmit} className="flex flex-col gap-4">
                {roles.length > 1 && (
                  <div>
                    <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                      Requesting As
                    </label>
                    <select
                      value={requestForRole}
                      onChange={(e) => {
                        setRequestForRole(e.target.value)
                        setSelectedTemplate("")
                      }}
                      className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
                    >
                      {roles.map((r) => (
                        <option key={r} value={r}>
                          {r.charAt(0).toUpperCase() + r.slice(1)}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div>
                  <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    Available Documents
                  </label>
                  {loadingTemplates ? (
                    <div className="w-full h-10 bg-muted/20 border border-border rounded-xl animate-pulse" />
                  ) : templates.length === 0 ? (
                    <p className="text-xs text-muted-foreground/80 italic">
                      No requestable documents for this role.
                    </p>
                  ) : (
                    <select
                      value={selectedTemplate}
                      onChange={(e) => setSelectedTemplate(e.target.value)}
                      required
                      className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
                    >
                      <option value="">Select a document...</option>
                      {templates.map((t) => (
                        <option key={t.id} value={t.key}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                <div>
                  <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    Optional Notes / Details
                  </label>
                  <textarea
                    value={requestNotes}
                    onChange={(e) => setRequestNotes(e.target.value)}
                    placeholder="e.g. specific purpose, required format details, or custom notes..."
                    rows={4}
                    className="w-full p-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary resize-none placeholder:text-muted-foreground/50"
                  />
                </div>

                {requestSuccess && (
                  <div className="flex items-center gap-2 text-xs text-emerald-600 dark:text-emerald-400 bg-emerald-500/5 border border-emerald-500/10 p-2.5 rounded-xl">
                    <CheckCircle2 size={14} className="shrink-0" />
                    <span>Request submitted successfully!</span>
                  </div>
                )}

                <Button
                  type="submit"
                  disabled={!selectedTemplate || submitRequest.isPending}
                  className="w-full h-10 gap-1.5"
                >
                  {submitRequest.isPending ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" /> Submitting…
                    </>
                  ) : (
                    "Submit Request"
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
