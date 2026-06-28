import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2, X, FileText } from "lucide-react"
import {
  listApplicationsApi, getApplicationApi, approveApplicationApi, rejectApplicationApi,
  listQuestionsAdminApi, createQuestionApi, deleteQuestionApi,
} from "@/api/apply"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

const ROLE_OPTIONS = [
  { value: "ambassador", label: "Ambassador" },
  { value: "intern",     label: "Intern" },
  { value: "teacher",    label: "Teacher" },
  { value: "facilitator", label: "Facilitator" },
]

const STATUS_COLOR: Record<string, string> = {
  pending:  "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300",
  approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-300",
}

const ROLE_COLOR: Record<string, string> = {
  ambassador: "bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-300",
  intern:     "bg-[#d6c7e1] text-[#643f83]",
  teacher:    "bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-300",
  facilitator:"bg-teal-100 text-teal-700 dark:bg-teal-500/20 dark:text-teal-300",
}

type Tab = "applications" | "questions"

export default function AdminApplications() {
  const [tab, setTab] = useState<Tab>("applications")

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-1 border-b border-border pb-1">
        {(["applications", "questions"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors capitalize ${
              tab === t ? "text-primary border-b-2 border-primary" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "applications" && <ApplicationsTab />}
      {tab === "questions" && <QuestionsTab />}
    </div>
  )
}

// ── Applications Tab ──────────────────────────────────────────────────────────

function ApplicationsTab() {
  const [roleFilter, setRoleFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("pending")
  const [selected, setSelected] = useState<string | null>(null)

  const { data: apps = [], isLoading } = useQuery({
    queryKey: ["admin-applications", roleFilter, statusFilter],
    queryFn: () => listApplicationsApi({
      role:   roleFilter !== "all" ? roleFilter : undefined,
      status: statusFilter !== "all" ? statusFilter : undefined,
    }),
  })

  return (
    <div className="flex flex-col gap-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="flex gap-1 bg-muted rounded-xl p-1">
          {["all", ...ROLE_OPTIONS.map((r) => r.value)].map((r) => (
            <button key={r} onClick={() => setRoleFilter(r)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors capitalize ${
                roleFilter === r ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}>
              {r === "all" ? "All roles" : r}
            </button>
          ))}
        </div>
        <div className="flex gap-1 bg-muted rounded-xl p-1">
          {["all", "pending", "approved", "rejected"].map((s) => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors capitalize ${
                statusFilter === s ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}>
              {s === "all" ? "All statuses" : s}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : apps.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground text-sm">No applications found</div>
      ) : (
        <div className="flex flex-col gap-2">
          {apps.map((app) => (
            <button
              key={app.id}
              onClick={() => setSelected(app.id)}
              className="w-full flex items-center justify-between p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors text-left gap-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-semibold text-foreground">{app.full_name}</p>
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${ROLE_COLOR[app.role] ?? "bg-muted text-foreground"}`}>
                    {app.role}
                  </span>
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${STATUS_COLOR[app.status]}`}>
                    {app.status}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">{app.email}{app.country ? ` · ${app.country}` : ""}</p>
              </div>
              <p className="text-xs text-muted-foreground shrink-0">
                {app.created_at ? new Date(app.created_at).toLocaleDateString() : "—"}
              </p>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <ApplicationDetailDialog id={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}

function ApplicationDetailDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [notes, setNotes] = useState("")

  const { data: app, isLoading } = useQuery({
    queryKey: ["admin-application", id],
    queryFn: () => getApplicationApi(id),
  })

  const { data: questions = [] } = useQuery({
    queryKey: ["admin-app-questions", app?.role],
    queryFn: () => listQuestionsAdminApi(app!.role),
    enabled: !!app?.role,
  })
  const qLabel = (qid: string) => questions.find((q) => q.id === qid)?.question_text ?? qid

  const approve = useMutation({
    mutationFn: () => approveApplicationApi(id, notes || undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-applications"] }); onClose() },
  })
  const reject = useMutation({
    mutationFn: () => rejectApplicationApi(id, notes || undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-applications"] }); onClose() },
  })

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-background w-full max-w-lg h-screen flex flex-col shadow-2xl border-l border-border">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <p className="text-sm font-semibold text-foreground">Application</p>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <div className="p-5 flex flex-col gap-4">
            {isLoading ? (
              <div className="flex justify-center py-12"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
            ) : !app ? null : (
              <>
                <Card>
                  <CardContent className="p-4 flex flex-col gap-3">
                    <div className="flex items-center gap-2">
                      <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center text-base font-bold text-foreground shrink-0">
                        {app.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <p className="font-semibold text-foreground">{app.full_name}</p>
                        <p className="text-sm text-muted-foreground">{app.email}</p>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <Info label="Role" value={app.role} />
                      <Info label="Status" value={app.status} />
                      {app.phone && <Info label="WhatsApp" value={app.phone} />}
                      {app.country && <Info label="Country" value={app.country} />}
                      {app.invite_code && <Info label="Invite code" value={app.invite_code} />}
                      {app.created_at && <Info label="Applied" value={new Date(app.created_at).toLocaleDateString()} />}
                    </div>
                  </CardContent>
                </Card>

                {app.has_cv && app.cv_signed_url && (
                  <a href={app.cv_signed_url} target="_blank" rel="noreferrer">
                    <Button variant="outline" className="w-full gap-2">
                      <FileText size={14} /> Download CV
                    </Button>
                  </a>
                )}

                {Object.keys(app.answers ?? {}).length > 0 && (
                  <Card>
                    <CardContent className="p-4 flex flex-col gap-3">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Answers</p>
                      {Object.entries(app.answers).map(([qId, ans]) => (
                        <div key={qId}>
                          <p className="text-xs text-muted-foreground mb-0.5">{qLabel(qId)}</p>
                          <p className="text-sm text-foreground">{String(ans)}</p>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {app.status === "pending" && (
                  <Card>
                    <CardContent className="p-4 flex flex-col gap-3">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Review</p>
                      <textarea
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="Admin notes (optional)"
                        rows={3}
                        className="w-full p-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none resize-none"
                      />
                      <div className="flex gap-2">
                        <Button variant="outline" className="flex-1 border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10"
                          onClick={() => reject.mutate()} disabled={reject.isPending || approve.isPending}>
                          {reject.isPending ? "Rejecting…" : "Reject"}
                        </Button>
                        <Button className="flex-1 bg-emerald-600 hover:bg-emerald-700"
                          onClick={() => approve.mutate()} disabled={approve.isPending || reject.isPending}>
                          {approve.isPending ? "Approving…" : "Approve"}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {app.status !== "pending" && app.admin_notes && (
                  <Card>
                    <CardContent className="p-4">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Admin notes</p>
                      <p className="text-sm text-foreground">{app.admin_notes}</p>
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm font-medium text-foreground capitalize">{value}</p>
    </div>
  )
}

// ── Questions Tab ─────────────────────────────────────────────────────────────

function QuestionsTab() {
  const qc = useQueryClient()
  const [audience, setAudience] = useState("ambassador")
  const [adding, setAdding] = useState(false)
  const [newQ, setNewQ] = useState({ question_text: "", question_type: "text", required: true, options: [""] })

  const { data: questions = [], isLoading } = useQuery({
    queryKey: ["admin-app-questions", audience],
    queryFn: () => listQuestionsAdminApi(audience),
  })

  const create = useMutation({
    mutationFn: () => createQuestionApi({ audience, ...newQ, options: newQ.options.filter(Boolean) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-app-questions", audience] })
      setAdding(false)
      setNewQ({ question_text: "", question_type: "text", required: true, options: [""] })
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteQuestionApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-app-questions", audience] }),
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <select value={audience} onChange={(e) => setAudience(e.target.value)}
          className="h-9 px-3 bg-background border border-border rounded-xl text-sm text-foreground focus:outline-none">
          {ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        <Button size="sm" onClick={() => setAdding(true)}><Plus size={14} className="mr-1" /> Add question</Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8"><div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
      ) : questions.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">No questions yet for {audience}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {questions.map((q, i) => (
            <div key={q.id} className="flex items-start gap-3 p-4 bg-card border border-border rounded-2xl">
              <span className="text-xs text-muted-foreground font-medium mt-0.5 w-5 shrink-0">{i + 1}.</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground">{q.question_text}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-muted-foreground capitalize">{q.question_type.replace("_", " ")}</span>
                  {q.required && <span className="text-xs text-destructive">Required</span>}
                  {q.options.length > 0 && (
                    <span className="text-xs text-muted-foreground">· {q.options.join(", ")}</span>
                  )}
                </div>
              </div>
              <button onClick={() => remove.mutate(q.id)}
                className="p-1.5 text-muted-foreground hover:text-destructive transition-colors shrink-0">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {adding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setAdding(false) }}>
          <Card className="w-full max-w-md">
            <CardContent className="p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <p className="font-semibold text-foreground text-sm">New question</p>
                <button onClick={() => setAdding(false)} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
              </div>
              <div className="flex flex-col gap-3">
                <textarea value={newQ.question_text} onChange={(e) => setNewQ({ ...newQ, question_text: e.target.value })}
                  placeholder="Question text" rows={2}
                  className="w-full p-3 bg-background border border-border rounded-xl text-sm focus:outline-none resize-none" />
                <select value={newQ.question_type} onChange={(e) => setNewQ({ ...newQ, question_type: e.target.value })}
                  className="h-9 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none">
                  <option value="text">Text</option>
                  <option value="number">Number</option>
                  <option value="radio">Radio (single choice)</option>
                  <option value="multiple_choice">Multiple choice</option>
                </select>
                {(newQ.question_type === "radio" || newQ.question_type === "multiple_choice") && (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs text-muted-foreground font-medium">Options</p>
                    {newQ.options.map((opt, i) => (
                      <div key={i} className="flex gap-2">
                        <div className="flex-1">
                          <input className="input" placeholder={`Option ${i + 1}`} value={opt}
                            onChange={(e) => {
                              const next = [...newQ.options]; next[i] = e.target.value
                              setNewQ({ ...newQ, options: next })
                            }} />
                        </div>
                        {newQ.options.length > 1 && (
                          <button onClick={() => setNewQ({ ...newQ, options: newQ.options.filter((_, j) => j !== i) })}
                            className="text-muted-foreground hover:text-destructive"><X size={14} /></button>
                        )}
                      </div>
                    ))}
                    <button onClick={() => setNewQ({ ...newQ, options: [...newQ.options, ""] })}
                      className="text-xs text-primary hover:underline text-left">+ Add option</button>
                  </div>
                )}
                <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                  <input type="checkbox" checked={newQ.required} onChange={(e) => setNewQ({ ...newQ, required: e.target.checked })} />
                  Required
                </label>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setAdding(false)}>Cancel</Button>
                <Button className="flex-1" disabled={!newQ.question_text.trim() || create.isPending} onClick={() => create.mutate()}>
                  {create.isPending ? "Saving…" : "Save question"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
