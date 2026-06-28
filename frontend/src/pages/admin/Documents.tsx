import { useState, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { FileText, CheckCircle2, XCircle, AlertCircle, Eye, HardDrive, Edit3, Trash2, Download, Upload, RefreshCw } from "lucide-react"
import {
  listDocumentRequestsApi,
  generateDocumentRequestApi,
  approveDocumentRequestApi,
  regenerateDocumentRequestApi,
  rejectDocumentRequestApi,
  listBucketsApi,
  listBucketFilesApi,
  deleteBucketFileApi,
  listAdminTemplatesApi,
  updateDocumentTemplateApi,
  createDocumentTemplateApi,
  deleteDocumentTemplateApi,
} from "@/api/documents"
import { getSettingsApi } from "@/api/admin/settings"
import type { DocumentRequest } from "@/types/documents"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"
import { UserProfileModal } from "@/components/UserProfileModal"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  recommendation_letter: "Recommendation Letter",
  confirmation_letter: "Confirmation Letter",
  completion_letter: "Completion Letter",
  certificate: "Completion Certificate",
}

const statusBadgeColor: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  rejected: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
}

export default function AdminDocuments() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<"requests" | "storage" | "templates">("requests")
  const [filter, setFilter] = useState<string>("all")
  
  // State for request modals
  const [approveRequest, setApproveRequest] = useState<DocumentRequest | null>(null)
  const [rejectRequest, setRejectRequest] = useState<DocumentRequest | null>(null)
  const [viewRequest, setViewRequest] = useState<DocumentRequest | null>(null)
  const [profileUserId, setProfileUserId] = useState<string | null>(null)

  // Fields for approval modal
  const [signatoryName, setSignatoryName] = useState("")
  const [signatoryTitle, setSignatoryTitle] = useState("")
  const [documentDate, setDocumentDate] = useState("")
  const [documentTitle, setDocumentTitle] = useState("")
  const [recommendationText, setRecommendationText] = useState("")

  // Fields for rejection modal
  const [adminNotes, setAdminNotes] = useState("")

  // 1. Fetch document requests
  const { data: requests = [], isLoading: loadingRequests } = useQuery<DocumentRequest[]>({
    queryKey: ["admin-document-requests", filter],
    queryFn: () => listDocumentRequestsApi(filter === "all" ? undefined : filter),
    enabled: activeTab === "requests",
  })

  // 2. Fetch system settings
  const { data: systemSettings } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: getSettingsApi,
    enabled: activeTab === "requests",
  })

  // 3. Fetch templates
  const { data: templates = [], isLoading: loadingTemplates, refetch: refetchTemplates } = useQuery({
    queryKey: ["admin-templates"],
    queryFn: listAdminTemplatesApi,
    enabled: activeTab === "requests" || activeTab === "templates",
  })

  // Mutations for requests
  const generateMutation = useMutation({
    mutationFn: ({ id, signatory_name, signatory_title, recommendation_text, date, title }: {
      id: string
      signatory_name?: string
      signatory_title?: string
      recommendation_text?: string
      date?: string
      title?: string
    }) => generateDocumentRequestApi(id, { signatory_name, signatory_title, recommendation_text, date, title }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-document-requests"] })
      setApproveRequest(null)
      setSignatoryName("")
      setSignatoryTitle("")
      setRecommendationText("")
      setDocumentDate("")
      setDocumentTitle("")
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to generate document")
    }
  })

  const approveMutation = useMutation({
    mutationFn: (id: string) => approveDocumentRequestApi(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-document-requests"] })
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to approve request")
    }
  })

  const regenerateMutation = useMutation({
    mutationFn: (id: string) => regenerateDocumentRequestApi(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["admin-document-requests"] })
      handleOpenApprove(data)
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to reset request")
    }
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, admin_notes }: { id: string; admin_notes: string }) =>
      rejectDocumentRequestApi(id, { admin_notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-document-requests"] })
      setRejectRequest(null)
      setAdminNotes("")
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to reject request")
    }
  })

  const handleOpenApprove = (req: DocumentRequest) => {
    setApproveRequest(req)
    const sigName = systemSettings?.admin_signatory_name || "ABDULLAH ALSALMANI"
    const sigTitle = systemSettings?.admin_signatory_title || "Co-Founder & CEO of SpacePoint"
    setSignatoryName(sigName)
    setSignatoryTitle(sigTitle)
    
    // Helper to format dates
    const formatDate = (dateStr?: string) => {
      const d = dateStr ? new Date(dateStr) : new Date()
      if (isNaN(d.getTime())) return ""
      const day = d.getDate()
      const month = d.toLocaleString("en-US", { month: "long" })
      const year = d.getFullYear()
      return `${day} ${month} ${year}`
    }
    
    setDocumentDate(formatDate())
    
    // Find matching template
    const matchingTemplate = templates.find(t => t.key === req.type || t.key.includes(req.type))
    setDocumentTitle(matchingTemplate?.name || DOCUMENT_TYPE_LABELS[req.type] || "Document")
    
    // Keep template text completely raw with placeholders
    setRecommendationText(matchingTemplate?.body_text || "")
  }

  const handleConfirmApprove = () => {
    if (!approveRequest) return
    generateMutation.mutate({
      id: approveRequest.id,
      signatory_name: signatoryName || undefined,
      signatory_title: signatoryTitle || undefined,
      recommendation_text: recommendationText || undefined,
      date: documentDate || undefined,
      title: documentTitle || undefined,
    })
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground tracking-tight">Documents Hub</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Admin interface for document requests, storage browsing, and customizable templates.
          </p>
        </div>

        {/* Tab switcher */}
        <div className="flex bg-muted p-1 rounded-xl">
          <button
            onClick={() => setActiveTab("requests")}
            className={cn("px-4 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all", activeTab === "requests" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
          >
            <FileText size={13} /> Requests
          </button>
          <button
            onClick={() => setActiveTab("storage")}
            className={cn("px-4 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all", activeTab === "storage" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
          >
            <HardDrive size={13} /> Storage Browser
          </button>
          <button
            onClick={() => setActiveTab("templates")}
            className={cn("px-4 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all", activeTab === "templates" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
          >
            <Edit3 size={13} /> Templates
          </button>
        </div>
      </div>

      {/* 1. REQUESTS TAB */}
      {activeTab === "requests" && (
        <div className="flex flex-col gap-4">
          <div className="flex gap-2 border-b border-border pb-1">
            {["all", "pending", "approved", "rejected"].map((tab) => (
              <button
                key={tab}
                onClick={() => setFilter(tab)}
                className={cn(
                  "px-3 py-2 text-sm font-semibold capitalize border-b-2 -mb-[5px] transition-colors",
                  filter === tab ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                {tab}
              </button>
            ))}
          </div>

          {loadingRequests ? (
            <Spinner />
          ) : requests.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 bg-card border border-border rounded-2xl text-center">
              <AlertCircle className="h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-sm font-medium text-foreground">No requests found</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {requests.map((req) => (
                <div
                  key={req.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between p-5 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors gap-4"
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <button
                      onClick={() => setProfileUserId(req.user_id)}
                      className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 mt-0.5 hover:opacity-80 transition-opacity shrink-0"
                      title="View profile"
                    >
                      <FileText size={20} />
                    </button>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <button
                          onClick={() => setProfileUserId(req.user_id)}
                          className="text-sm font-semibold text-foreground truncate hover:text-primary transition-colors"
                        >
                          {req.user_name || "Unknown User"}
                        </button>
                        <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full", statusBadgeColor[req.status])}>
                          {req.status}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground truncate">{req.user_email}</p>
                      <div className="mt-2 flex flex-col gap-1">
                        <p className="text-sm font-medium text-foreground">
                          Requested: <span className="font-semibold text-primary">{templates.find(t => t.key === req.type)?.name || DOCUMENT_TYPE_LABELS[req.type] || req.type.replace(/_/g, " ")}</span>
                          {req.requested_role && (
                            <span className="ml-2 px-2 py-0.5 bg-violet-500/10 text-violet-600 dark:text-violet-400 text-[10px] uppercase font-bold rounded-md tracking-wider">
                              as {req.requested_role}
                            </span>
                          )}
                        </p>
                        {req.notes && (
                          <p className="text-xs text-muted-foreground bg-muted p-2 rounded-lg italic border border-border mt-1 max-w-xl">
                            "{req.notes}"
                          </p>
                        )}
                        {req.admin_notes && (
                          <p className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/20 p-2 rounded-lg border border-red-200 dark:border-red-900/30 mt-1 max-w-xl">
                            <strong>Admin Feedback:</strong> {req.admin_notes}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0 self-end sm:self-center">
                    <button
                      onClick={() => setViewRequest(req)}
                      className="p-2 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-all"
                      title="View Details"
                    >
                      <Eye size={16} />
                    </button>
                    {req.status === "pending" && (
                      <>
                        <button
                          onClick={() => { setRejectRequest(req); setAdminNotes("") }}
                          className="flex items-center gap-1 h-9 px-3 border border-red-200 text-red-600 hover:bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/20 text-xs font-semibold rounded-xl transition-colors"
                        >
                          <XCircle size={14} /> Reject
                        </button>
                        
                        {!req.file_url ? (
                          <button
                            onClick={() => handleOpenApprove(req)}
                            className="flex items-center gap-1 h-9 px-4 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 transition-colors"
                          >
                            <CheckCircle2 size={14} /> Generate
                          </button>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <a
                              href={req.file_url}
                              target="_blank"
                              rel="noreferrer"
                              className="flex items-center gap-1 h-9 px-3 border border-border text-foreground hover:bg-muted text-xs font-semibold rounded-xl transition-colors"
                            >
                              <Eye size={14} /> Preview
                            </a>
                            <button
                              onClick={() => regenerateMutation.mutate(req.id)}
                              disabled={regenerateMutation.isPending}
                              className="flex items-center gap-1 h-9 px-3 border border-border text-muted-foreground hover:text-foreground hover:bg-muted text-xs font-semibold rounded-xl transition-colors disabled:opacity-50"
                              title="Regenerate Document"
                            >
                              <RefreshCw size={14} className={regenerateMutation.isPending ? "animate-spin" : ""} /> Regenerate
                            </button>
                            <button
                              onClick={() => approveMutation.mutate(req.id)}
                              disabled={approveMutation.isPending}
                              className="flex items-center gap-1 h-9 px-4 bg-emerald-600 text-white text-xs font-semibold rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
                            >
                              <CheckCircle2 size={14} /> Send
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Request Detail Modal */}
          {viewRequest && (
            <Modal title="Document Request Details" onClose={() => setViewRequest(null)}>
              <div className="flex flex-col gap-3 text-sm">
                <div>
                  <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider block">User</span>
                  <span className="text-foreground font-medium">{viewRequest.user_name} ({viewRequest.user_email})</span>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider block">Request Type</span>
                  <span className="text-foreground font-semibold text-primary">
                    {templates.find(t => t.key === viewRequest.type)?.name || DOCUMENT_TYPE_LABELS[viewRequest.type] || viewRequest.type}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider block">Status</span>
                  <span className="text-foreground capitalize font-semibold">{viewRequest.status}</span>
                </div>
                {viewRequest.notes && (
                  <div>
                    <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider block">User Notes</span>
                    <p className="text-foreground italic bg-muted p-3 rounded-xl border border-border mt-1 font-mono">"{viewRequest.notes}"</p>
                  </div>
                )}
                {viewRequest.admin_notes && (
                  <div>
                    <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider block">Admin Reason / Notes</span>
                    <p className="text-red-500 bg-red-500/5 border border-red-500/10 p-3 rounded-xl mt-1">"{viewRequest.admin_notes}"</p>
                  </div>
                )}
                <div className="flex justify-end mt-2">
                  <Button variant="outline" onClick={() => setViewRequest(null)}>Close</Button>
                </div>
              </div>
            </Modal>
          )}

          {/* Rejection Modal */}
          {rejectRequest && (
            <Modal title={`Reject ${templates.find(t => t.key === rejectRequest.type)?.name || rejectRequest.type}`} onClose={() => setRejectRequest(null)}>
              <div className="flex flex-col gap-4">
                <p className="text-xs text-muted-foreground">Specify the reason for rejecting this document request.</p>
                <Field label="Reason / Notes">
                  <textarea
                    value={adminNotes}
                    onChange={(e) => setAdminNotes(e.target.value)}
                    placeholder="e.g. Missing required program modules or milestone tasks."
                    rows={4}
                    className="w-full p-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary resize-none"
                    required
                  />
                </Field>
                <ModalActions
                  onCancel={() => setRejectRequest(null)}
                  onConfirm={() => rejectMutation.mutate({ id: rejectRequest.id, admin_notes: adminNotes })}
                  loading={rejectMutation.isPending}
                  disabled={!adminNotes.trim()}
                  label="Reject Request"
                />
              </div>
            </Modal>
          )}

          {/* Approval Modal */}
          {approveRequest && (
            <Modal title={`Approve ${templates.find(t => t.key === approveRequest.type)?.name || approveRequest.type}`} onClose={() => setApproveRequest(null)}>
              <div className="flex flex-col gap-4">
                <p className="text-xs text-muted-foreground">Approve this request and generate the PDF. Customize signatory information below.</p>
                <div className="flex flex-col gap-4">
                  <Field label="Document Title">
                    <input
                      type="text"
                      value={documentTitle}
                      onChange={(e) => setDocumentTitle(e.target.value)}
                      placeholder="e.g. Recommendation Letter"
                      className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none"
                    />
                  </Field>
                  <Field label="Date">
                    <input
                      type="text"
                      value={documentDate}
                      onChange={(e) => setDocumentDate(e.target.value)}
                      placeholder="e.g. 27 June 2026"
                      className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none"
                    />
                  </Field>
                  <Field label="Signatory Name">
                    <input
                      type="text"
                      value={signatoryName}
                      onChange={(e) => setSignatoryName(e.target.value)}
                      placeholder="e.g. Abdullah Alsalmani"
                      className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none"
                    />
                  </Field>
                  <Field label="Signatory Title">
                    <input
                      type="text"
                      value={signatoryTitle}
                      onChange={(e) => setSignatoryTitle(e.target.value)}
                      placeholder="e.g. Co-Founder & CEO"
                      className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none"
                    />
                  </Field>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Signatory Signature
                  </label>
                  <div className="relative overflow-hidden rounded-xl border border-border bg-muted/20 p-2 flex items-center justify-center min-h-[50px] max-w-[200px]">
                    {systemSettings?.admin_signature_url ? (
                      <img
                        src={systemSettings.admin_signature_url}
                        alt="Admin signature"
                        className="max-h-10 object-contain dark:invert"
                      />
                    ) : (
                      <span className="text-[11px] text-amber-500 italic">No admin signature uploaded in settings</span>
                    )}
                  </div>
                </div>

                <Field label="Document text template (supports HTML & placeholders like {name}, {start_date}, {end_date}, {signature}, {signatory_name}, {signatory_title})">
                  <textarea
                    value={recommendationText}
                    onChange={(e) => setRecommendationText(e.target.value)}
                    rows={8}
                    className="w-full p-3 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-none resize-none font-mono font-medium leading-relaxed"
                  />
                </Field>
                <ModalActions
                  onCancel={() => setApproveRequest(null)}
                  onConfirm={handleConfirmApprove}
                  loading={generateMutation.isPending}
                  disabled={!recommendationText.trim()}
                  label="Generate"
                />
              </div>
            </Modal>
          )}
        </div>
      )}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}

      {/* 2. STORAGE TAB */}
      {activeTab === "storage" && <StorageManager />}

      {/* 3. TEMPLATES TAB */}
      {activeTab === "templates" && (
        <TemplateManager templates={templates} isLoading={loadingTemplates} onRefresh={refetchTemplates} />
      )}
    </div>
  )
}

function StorageManager() {
  const [selectedBucket, setSelectedBucket] = useState("certificates")
  const [filesPath, setFilesPath] = useState("")

  const { data: buckets = [] } = useQuery({
    queryKey: ["storage-buckets"],
    queryFn: listBucketsApi,
  })

  const { data: files = [], isLoading: loadingFiles, refetch: refetchFiles } = useQuery({
    queryKey: ["storage-files", selectedBucket, filesPath],
    queryFn: () => listBucketFilesApi(selectedBucket, filesPath),
    enabled: !!selectedBucket,
  })

  const deleteFile = useMutation({
    mutationFn: (filePath: string) => deleteBucketFileApi(selectedBucket, filePath),
    onSuccess: () => {
      refetchFiles()
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to delete file")
    }
  })

  const handleDelete = (fileName: string) => {
    const fullPath = filesPath ? `${filesPath}/${fileName}` : fileName
    if (confirm(`Are you sure you want to delete ${fileName} from ${selectedBucket}?`)) {
      deleteFile.mutate(fullPath)
    }
  }



  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-6 bg-card border border-border p-5 rounded-2xl shadow-sm">
      {/* Bucket selection Sidebar */}
      <div className="md:col-span-1 border-r border-border/80 pr-4 flex flex-col gap-2">
        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Storage Buckets</span>
        {buckets.map((b) => (
          <button
            key={b}
            onClick={() => { setSelectedBucket(b); setFilesPath("") }}
            className={cn(
              "w-full text-left px-3 py-2 rounded-xl text-xs font-semibold transition-colors flex items-center gap-2",
              selectedBucket === b ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <HardDrive size={13} /> {b}
          </button>
        ))}
      </div>

      {/* Files list */}
      <div className="md:col-span-3 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
            Files in <span className="font-mono text-primary font-bold">{selectedBucket}</span>
          </h2>
          <Button size="sm" variant="outline" onClick={() => refetchFiles()} disabled={loadingFiles}>
            <RefreshCw size={12} className={loadingFiles ? "animate-spin" : ""} /> Refresh
          </Button>
        </div>

        {loadingFiles ? (
          <div className="flex items-center justify-center p-12"><Spinner /></div>
        ) : files.length === 0 ? (
          <div className="text-center p-12 border border-dashed border-border rounded-xl">
            <p className="text-sm text-muted-foreground italic">No files found in this bucket.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/80 text-muted-foreground uppercase tracking-wider font-semibold text-[10px]">
                  <th className="pb-2">User</th>
                  <th className="pb-2">Document</th>
                  <th className="pb-2">Type</th>
                  <th className="pb-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {files.map((file) => (
                  <tr key={file.name} className="border-b border-border/30 hover:bg-muted/10 transition-colors">
                    <td className="py-2.5 font-medium text-foreground truncate max-w-[150px]" title={file.owner_name || "System / General"}>
                      <span className={cn(
                        file.owner_name ? "text-foreground font-semibold" : "text-muted-foreground/70 italic"
                      )}>
                        {file.owner_name || "System / General"}
                      </span>
                    </td>
                    <td className="py-2.5 font-medium text-foreground truncate max-w-xs" title={file.name}>
                      {file.signed_url ? (
                        <a href={file.signed_url} target="_blank" rel="noreferrer" className="hover:text-primary transition-colors flex items-center gap-1.5">
                          <FileText size={12} className="text-primary/70 shrink-0" />
                          <span className="truncate">{file.document_type_label || file.name}</span>
                        </a>
                      ) : (
                        <span className="flex items-center gap-1.5">
                          <FileText size={12} className="text-muted-foreground/40 shrink-0" />
                          <span className="truncate">{file.document_type_label || file.name}</span>
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 text-muted-foreground truncate max-w-[120px]">{file.mimetype || "—"}</td>
                    <td className="py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {file.signed_url && (
                          <>
                            <a
                              href={file.signed_url} target="_blank" rel="noreferrer"
                              className="p-1.5 border border-border rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-all shrink-0"
                              title="View File"
                            >
                              <Eye size={12} />
                            </a>
                            <a
                              href={file.signed_url} download={file.name} target="_blank" rel="noreferrer"
                              className="p-1.5 border border-border rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-all shrink-0"
                              title="Download File"
                            >
                              <Download size={12} />
                            </a>
                          </>
                        )}
                        <button
                          onClick={() => handleDelete(file.name)}
                          disabled={deleteFile.isPending}
                          className="p-1.5 border border-border rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/5 transition-all shrink-0"
                          title="Delete File"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

interface TemplateManagerProps {
  templates: any[]
  isLoading: boolean
  onRefresh: () => void
}

function TemplateManager({ templates, isLoading, onRefresh }: TemplateManagerProps) {
  const [editingTemplate, setEditingTemplate] = useState<any | null>(null)
  const [editName, setEditName] = useState("")
  const [editType, setEditType] = useState<"letter" | "certificate">("letter")
  const [editRoles, setEditRoles] = useState<string[]>([])
  const [bodyText, setBodyText] = useState("")
  const [fileToUpload, setFileToUpload] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Creation State
  const [createOpen, setCreateOpen] = useState(false)
  const [newKey, setNewKey] = useState("")
  const [newName, setNewName] = useState("")
  const [newRoles, setNewRoles] = useState<string[]>(["intern"])
  const [newBodyText, setNewBodyText] = useState("")
  const [newType, setNewType] = useState<"letter" | "certificate">("letter")

  const ROLE_OPTIONS = [
    { value: "intern", label: "Intern" },
    { value: "instructor", label: "Instructor" },
    { value: "facilitator", label: "Facilitator" },
    { value: "teacher", label: "Teacher" },
    { value: "ambassador", label: "Ambassador" },
    { value: "team_leader", label: "Team Leader" },
    { value: "admin", label: "Admin" },
  ]

  const toggleRole = (roles: string[], role: string): string[] =>
    roles.includes(role) ? roles.filter(r => r !== role) : [...roles, role]

  const createTemplate = useMutation({
    mutationFn: () => createDocumentTemplateApi({ key: newKey, name: newName, roles: newRoles, body_text: newBodyText || undefined, type: newType }),
    onSuccess: () => {
      onRefresh()
      setCreateOpen(false)
      setNewKey("")
      setNewName("")
      setNewRoles(["intern"])
      setNewBodyText("")
      setNewType("letter")
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to create template")
    }
  })

  const updateTemplate = useMutation({
    mutationFn: (data: { id: string; name?: string; roles?: string[]; bodyText?: string; file?: File; type?: string }) =>
      updateDocumentTemplateApi(data.id, data.name, data.roles, data.bodyText, data.file, data.type),
    onSuccess: () => {
      onRefresh()
      setEditingTemplate(null)
      setFileToUpload(null)
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to update template")
    }
  })

  const deleteTemplate = useMutation({
    mutationFn: (id: string) => deleteDocumentTemplateApi(id),
    onSuccess: () => {
      onRefresh()
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to delete template")
    }
  })

  const handleEditClick = (temp: any) => {
    setEditingTemplate(temp)
    setEditName(temp.name)
    setEditType(temp.type === "certificate" ? "certificate" : "letter")
    setEditRoles(temp.roles || [])
    setBodyText(temp.body_text || "")
    setFileToUpload(null)
  }

  const handleSave = () => {
    if (!editingTemplate) return
    updateTemplate.mutate({
      id: editingTemplate.id,
      name: editName,
      roles: editRoles,
      bodyText,
      type: editType,
      file: fileToUpload || undefined
    })
  }

  const handleDeleteClick = (id: string, name: string) => {
    if (confirm(`Are you sure you want to delete the document template "${name}"?`)) {
      deleteTemplate.mutate(id)
    }
  }

  if (isLoading) return <div className="flex items-center justify-center p-12"><Spinner /></div>

  return (
    <div className="flex flex-col gap-6">
      <div className="flex justify-end">
        <Button onClick={() => setCreateOpen(true)} className="gap-1.5">
          Create Template
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {templates.map((temp) => (
          <Card key={temp.id} className="border border-border bg-card rounded-2xl hover:border-muted-foreground/20 transition-all flex flex-col">
            <CardHeader className="pb-2 border-b border-border/40">
              <CardTitle className="text-sm font-semibold flex items-center justify-between gap-2">
                <span className="truncate">{temp.name}</span>
                <span className="flex items-center gap-1 shrink-0">
                  <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${temp.type === "certificate" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400" : "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400"}`}>
                    {temp.type === "certificate" ? "Certificate" : "Letter"}
                  </span>
                  {temp.is_system && (
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted text-muted-foreground">System</span>
                  )}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 flex-1 flex flex-col justify-between gap-4">
              <div className="flex flex-col gap-2">
                {/* Available To */}
                <div>
                  <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1">Available To</span>
                  {(temp.roles || []).length >= 5 ? (
                    <span className="inline-flex items-center px-2.5 py-1 bg-primary/10 text-primary text-[11px] font-bold rounded-lg tracking-wide">
                      All Roles
                    </span>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {(temp.roles || []).map((r: string) => (
                        <span key={r} className="px-2 py-0.5 bg-primary/10 text-primary text-[10px] uppercase font-bold rounded-md tracking-wider">
                          {r}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block">Key Identifier</span>
                  <span className="text-xs font-mono font-medium block mt-0.5">{temp.key}</span>
                </div>
                {temp.body_text && (

                  <div>
                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block">Template Text</span>
                    <p className="text-xs text-foreground bg-muted p-2 rounded-xl mt-1 border border-border/50 max-h-24 overflow-y-auto italic font-mono whitespace-pre-wrap">
                      "{temp.body_text}"
                    </p>
                  </div>
                )}
                {temp.template_file_url && (
                  <div>
                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block">Custom File Template</span>
                    <a
                      href={temp.template_file_url} target="_blank" rel="noreferrer"
                      className="text-xs text-primary hover:underline font-semibold flex items-center gap-1.5 mt-1"
                    >
                      <Download size={11} /> Download Custom Frame/Asset
                    </a>
                  </div>
                )}
              </div>

              <div className="flex gap-2 mt-2">
                <Button size="sm" variant="outline" className="flex-1 gap-1.5" onClick={() => handleEditClick(temp)}>
                  <Edit3 size={12} /> Edit
                </Button>
                {!temp.is_system && (
                  <button
                    onClick={() => handleDeleteClick(temp.id, temp.name)}
                    disabled={deleteTemplate.isPending}
                    className="p-2 border border-border rounded-xl text-muted-foreground hover:text-red-600 hover:bg-red-500/5 transition-all shrink-0 flex items-center justify-center"
                    title="Delete Template"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Create Template Modal */}
      {createOpen && (
        <Modal title="Create New Document Template" onClose={() => setCreateOpen(false)}>
          <div className="flex flex-col gap-4">
            <Field label="Template Key (Unique ID, e.g. intern_certificate)">
              <input
                type="text"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="e.g. intern_custom_letter"
                className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
                required
              />
            </Field>

            <Field label="Template Name">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Custom Recommendation Letter"
                className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
                required
              />
            </Field>

            <Field label="Type">
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value as "letter" | "certificate")}
                className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
              >
                <option value="letter">Letter — text on a blank page</option>
                <option value="certificate">Certificate — text over a base image</option>
              </select>
            </Field>

            <Field label="Available To (Roles that can request this document)">
              <div className="flex flex-wrap gap-3 pt-1">
                {ROLE_OPTIONS.map(opt => (
                  <label key={opt.value} className="flex items-center gap-2 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={newRoles.includes(opt.value)}
                      onChange={() => setNewRoles(toggleRole(newRoles, opt.value))}
                      className="w-4 h-4 rounded accent-primary"
                    />
                    <span className="text-sm text-foreground">{opt.label}</span>
                  </label>
                ))}
              </div>
            </Field>

            <Field label="Template Body Text (Supports HTML and placeholders like {name})">
              <textarea
                value={newBodyText}
                onChange={(e) => setNewBodyText(e.target.value)}
                placeholder="e.g. This is to confirm that {name} has completed the program..."
                rows={4}
                className="w-full p-3 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-none resize-none font-mono"
              />
            </Field>

            <ModalActions
              onCancel={() => setCreateOpen(false)}
              onConfirm={() => createTemplate.mutate()}
              loading={createTemplate.isPending}
              disabled={!newKey.trim() || !newName.trim() || newRoles.length === 0}
              label="Create Template"
            />
          </div>
        </Modal>
      )}

      {/* Edit Template Modal */}
      {editingTemplate && (
        <Modal title={`Edit Template: ${editingTemplate.name}`} onClose={() => setEditingTemplate(null)}>
          <div className="flex flex-col gap-4">
            <Field label="Template Name">
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="e.g. Custom Recommendation Letter"
                className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
                required
              />
            </Field>

            <Field label="Type">
              <select
                value={editType}
                onChange={(e) => setEditType(e.target.value as "letter" | "certificate")}
                className="w-full h-10 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none focus:border-primary"
              >
                <option value="letter">Letter — text on a blank page</option>
                <option value="certificate">Certificate — text over a base image</option>
              </select>
            </Field>

            <Field label="Available To (Roles that can request this document)">
              <div className="flex flex-wrap gap-3 pt-1">
                {ROLE_OPTIONS.map(opt => (
                  <label key={opt.value} className="flex items-center gap-2 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={editRoles.includes(opt.value)}
                      onChange={() => setEditRoles(toggleRole(editRoles, opt.value))}
                      className="w-4 h-4 rounded accent-primary"
                    />
                    <span className="text-sm text-foreground">{opt.label}</span>
                  </label>
                ))}
              </div>
            </Field>

            <Field label="Template Body Text (Supports HTML and placeholders like {name}, {start_date}, {end_date})">
              <textarea
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                rows={5}
                className="w-full p-3 bg-background border border-border rounded-xl text-xs text-foreground focus:outline-none resize-none font-mono"
              />
            </Field>

            <Field label="Replace Template Frame/Background File (Optional)">
              <div className="flex items-center gap-3">
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) setFileToUpload(f)
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload size={12} /> Upload File
                </Button>
                {fileToUpload ? (
                  <span className="text-xs text-foreground font-semibold truncate max-w-[180px]">
                    {fileToUpload.name}
                  </span>
                ) : editingTemplate.template_file_url ? (
                  <span className="text-xs text-muted-foreground italic">Has custom file uploaded</span>
                ) : (
                  <span className="text-xs text-muted-foreground italic">Using system default frame</span>
                )}
              </div>
            </Field>

            <ModalActions
              onCancel={() => setEditingTemplate(null)}
              onConfirm={handleSave}
              loading={updateTemplate.isPending}
              disabled={!editName.trim()}
              label="Save Changes"
            />
          </div>
        </Modal>
      )}
    </div>
  )
}
