import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, FileText, CheckCircle2, AlertCircle, RefreshCw, Send } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import {
  getMyDocumentsApi,
  getMyDocumentRequestsApi,
  createDocumentRequestApi,
  getAvailableTemplatesApi,
} from "@/api/documents"
import { ProfileIdCard } from "@/components/documents/ProfileIdCard"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export default function UserDocuments() {
  const { activeRole } = useAuth()
  const qc = useQueryClient()
  
  const [selectedTemplate, setSelectedTemplate] = useState("")
  const [requestNotes, setRequestNotes] = useState("")
  const [requestSuccess, setRequestSuccess] = useState(false)

  // 1. Fetch received documents
  const { data: myDocs, isLoading: loadingDocs } = useQuery({
    queryKey: ["my-documents"],
    queryFn: getMyDocumentsApi,
  })

  // 2. Fetch my document requests
  const { data: myRequests = [], isLoading: loadingRequests } = useQuery({
    queryKey: ["my-document-requests"],
    queryFn: getMyDocumentRequestsApi,
  })

  // 3. Fetch available templates for my active role
  const { data: templates = [], isLoading: loadingTemplates } = useQuery({
    queryKey: ["available-templates", activeRole],
    queryFn: () => getAvailableTemplatesApi(activeRole ?? ""),
    enabled: !!activeRole,
  })

  // 4. Submit document request
  const submitRequest = useMutation({
    mutationFn: () =>
      createDocumentRequestApi({
        type: selectedTemplate,
        requested_role: activeRole || undefined,
        notes: requestNotes.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-document-requests"] })
      setRequestNotes("")
      setSelectedTemplate("")
      setRequestSuccess(true)
      setTimeout(() => setRequestSuccess(false), 3000)
    },
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to submit request")
    },
  })

  // Compile received documents list
  const receivedItems = [
    ...(myDocs?.certificates ?? []).map((c) => ({
      id: c.id,
      label: c.type === "instructor_completion" ? "Instructor Program Completion Certificate" : c.type === "internship_completion" ? "Internship Completion Certificate" : "Workshop Facilitator Certificate",
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
    pending: "text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-950/20 border-amber-200/50 dark:border-amber-900/30",
    approved: "text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-950/20 border-emerald-200/50 dark:border-emerald-900/30",
    rejected: "text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-950/20 border-red-200/50 dark:border-red-900/30",
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedTemplate) return
    submitRequest.mutate()
  }

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">My Documents</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage your personal profile assets, request certificates or confirmation letters, and download generated documents.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Received docs and request logs */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Received Documents */}
          <Card className="border border-border bg-card rounded-2xl shadow-sm">
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
                  <p className="text-xs text-muted-foreground mt-0.5">Documents will appear here once approved by admins.</p>
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

          {/* Request Log */}
          <Card className="border border-border bg-card rounded-2xl shadow-sm">
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
                          {templates.find((t) => t.key === req.type)?.name || req.type.replace(/_/g, " ").toUpperCase()}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded-full border text-[10px] capitalize font-semibold tracking-wider ${
                            statusColor[req.status]
                          }`}
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
                        {new Date(req.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Submission Form & Profile ID Card */}
        <div className="flex flex-col gap-6">
          {/* Submit Request Form */}
          <Card className="border border-border bg-card rounded-2xl shadow-sm">
            <CardHeader className="pb-3 border-b border-border/50">
              <CardTitle className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                <Send size={15} className="text-primary" />
                Request New Document
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div>
                  <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
                    Available Documents
                  </label>
                  {loadingTemplates ? (
                    <div className="w-full h-10 bg-muted/20 border border-border rounded-xl animate-pulse" />
                  ) : templates.length === 0 ? (
                    <p className="text-xs text-muted-foreground/80 italic">No requestable documents for your active role.</p>
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
                    <><RefreshCw size={14} className="animate-spin" /> Submitting…</>
                  ) : (
                    "Submit Request"
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Profile ID Cardpreview */}
          {activeRole && activeRole !== "admin" && (
            <ProfileIdCard role={activeRole} />
          )}
        </div>
      </div>
    </div>
  )
}
