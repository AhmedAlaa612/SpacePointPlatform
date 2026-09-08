import { useState } from "react"
import { isAxiosError } from "axios"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Download, Pencil, Plus, Trash2, Upload } from "lucide-react"
import { PageHeader, EmptyState, Spinner, StatCard } from "@/components/ui/primitives"
import { ConfirmDialog, Modal, Field, ModalActions } from "@/pages/admin/components/common"
import {
  createAssessmentConfigApi,
  createAssessmentQuestionApi,
  deleteAssessmentQuestionApi,
  downloadAssessmentQuestionsTemplateApi,
  getAssessmentConfigApi,
  importAssessmentQuestionsApi,
  listAssessmentConfigsApi,
  updateAssessmentQuestionApi,
} from "@/api/instructor_assessment"
import type { AssessmentConfig, AssessmentQuestion } from "@/types/instructor_assessment"
import { cn, getErrorMessage } from "@/lib/utils"

const EMPTY_OPTIONS = [
  { text: "", is_correct: true },
  { text: "", is_correct: false },
  { text: "", is_correct: false },
  { text: "", is_correct: false },
]

/** Instructor Assessment question-bank authoring (2026-09) — same shape as
 *  LmsGames.tsx's list-plus-modals pattern, but folded into one page since
 *  a config's own question table is the point of opening it (no separate
 *  detail route needed for something this flat). */
export default function AssessmentQuestions() {
  const queryClient = useQueryClient()
  const [selectedConfigId, setSelectedConfigId] = useState<string | null>(null)
  const [createConfigOpen, setCreateConfigOpen] = useState(false)
  const [configName, setConfigName] = useState("")
  const [configDescription, setConfigDescription] = useState("")

  const { data: configs = [], isLoading: configsLoading } = useQuery<AssessmentConfig[]>({
    queryKey: ["assessment-configs"],
    queryFn: listAssessmentConfigsApi,
  })

  const createConfigMutation = useMutation({
    mutationFn: () => createAssessmentConfigApi({ name: configName, description: configDescription || null }),
    onSuccess: (config) => {
      setCreateConfigOpen(false); setConfigName(""); setConfigDescription("")
      queryClient.invalidateQueries({ queryKey: ["assessment-configs"] })
      setSelectedConfigId(config.id)
    },
  })

  const selected = configs.find((c) => c.id === selectedConfigId) ?? null

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Instructor Assessment — Question Bank"
        subtitle="Category-tagged, critical-flagged scenario questions. Each config is a reusable bank ops assigns to a cohort."
        action={
          <button
            onClick={() => setCreateConfigOpen(true)}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors shrink-0"
          >
            <Plus size={14} /> New assessment
          </button>
        }
      />

      {configsLoading ? (
        <Spinner />
      ) : configs.length === 0 ? (
        <EmptyState title="No assessment configs yet" hint="Create one to start writing questions." />
      ) : (
        <div className="flex gap-2 flex-wrap">
          {configs.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelectedConfigId(c.id)}
              className={`h-9 px-4 rounded-xl text-sm font-medium border transition-colors ${
                c.id === selectedConfigId
                  ? "bg-primary text-primary-foreground border-transparent"
                  : "bg-card border-border text-foreground hover:bg-muted"
              }`}
            >
              {c.name} · {c.question_count}
            </button>
          ))}
        </div>
      )}

      {selected && <AssessmentConfigDetail config={selected} />}

      {createConfigOpen && (
        <Modal title="New assessment" onClose={() => setCreateConfigOpen(false)}>
          <div className="flex flex-col gap-4">
            <Field label="Name">
              <input
                value={configName} onChange={(e) => setConfigName(e.target.value)} autoFocus
                placeholder="e.g. Shallow Flight Instructor Assessment"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
              />
            </Field>
            <Field label="Description (optional)">
              <textarea
                value={configDescription} onChange={(e) => setConfigDescription(e.target.value)} rows={2}
                className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
              />
            </Field>
            <ModalActions
              onCancel={() => setCreateConfigOpen(false)}
              onConfirm={() => configName.trim() && createConfigMutation.mutate()}
              loading={createConfigMutation.isPending}
              disabled={!configName.trim()}
              label="Create"
            />
          </div>
        </Modal>
      )}
    </div>
  )
}

function AssessmentConfigDetail({ config }: { config: AssessmentConfig }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<AssessmentQuestion | null>(null)
  const [adding, setAdding] = useState(false)
  const [deleting, setDeleting] = useState<AssessmentQuestion | null>(null)
  const [importErrors, setImportErrors] = useState<string[]>([])

  const { data: detail, isLoading } = useQuery({
    queryKey: ["assessment-config", config.id],
    queryFn: () => getAssessmentConfigApi(config.id),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["assessment-config", config.id] })
    queryClient.invalidateQueries({ queryKey: ["assessment-configs"] })
  }

  const deleteMutation = useMutation({
    mutationFn: () => deleteAssessmentQuestionApi(deleting!.id),
    onSuccess: () => { setDeleting(null); invalidate() },
  })

  const importMutation = useMutation({
    mutationFn: (file: File) => importAssessmentQuestionsApi(config.id, file),
    onSuccess: (result) => { setImportErrors(result.errors); invalidate() },
  })

  if (isLoading || !detail) return <Spinner />

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard icon={<Plus size={18} />} label="Total questions" value={detail.question_count} />
        <StatCard icon={<Plus size={18} />} label="Categories" value={Object.keys(detail.category_counts).length} />
        <StatCard icon={<AlertTriangle size={18} />} label="Critical" value={detail.critical_count}
          sub={detail.question_count ? `${Math.round((detail.critical_count / detail.question_count) * 100)}%` : undefined} />
      </div>

      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => void downloadAssessmentQuestionsTemplateApi()}
            className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs sm:text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            <Download size={14} /> Download template
          </button>
          <label className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 h-9 px-3 border border-border rounded-xl text-xs sm:text-sm font-medium text-foreground hover:bg-muted transition-colors cursor-pointer">
            <Upload size={14} /> Import from Excel
            <input
              type="file" accept=".xlsx" className="hidden"
              onChange={(e) => { const file = e.target.files?.[0]; if (file) importMutation.mutate(file); e.target.value = "" }}
            />
          </label>
        </div>
        <button
          onClick={() => setAdding(true)}
          className="flex items-center justify-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-xs sm:text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
        >
          <Plus size={14} /> Add question
        </button>
      </div>

      {importErrors.length > 0 && (
        <div className="text-xs text-amber-700 dark:text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2 flex flex-col gap-1">
          <span className="font-semibold">{importErrors.length} row{importErrors.length === 1 ? "" : "s"} skipped:</span>
          {importErrors.map((e, i) => <span key={i}>{e}</span>)}
        </div>
      )}

      {detail.questions.length === 0 ? (
        <EmptyState title="No questions yet" hint="Add one, or import from Excel." />
      ) : (
        <>
          {/* Mobile View: Stacked Cards */}
          <div className="flex flex-col gap-3 sm:hidden">
            {detail.questions.map((q) => (
              <div
                key={q.id}
                className={cn(
                  "flex flex-col gap-2.5 p-4 rounded-xl border border-border bg-card shadow-sm",
                  q.critical && "border-red-500/40 bg-red-500/5",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold px-2 py-0.5 rounded bg-muted text-muted-foreground truncate">
                    {q.category}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {q.critical && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-500 text-white">
                        CRITICAL
                      </span>
                    )}
                    <span className={cn(
                      "text-[10px] font-medium px-1.5 py-0.5 rounded",
                      q.is_active ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20" : "bg-muted text-muted-foreground"
                    )}>
                      {q.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                </div>
                <p className="text-sm font-medium text-foreground leading-snug">{q.prompt}</p>
                <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/50">
                  <button
                    onClick={() => setEditing(q)}
                    className="flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted border border-border transition-colors"
                  >
                    <Pencil size={12} /> Edit
                  </button>
                  <button
                    onClick={() => setDeleting(q)}
                    className="flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium text-destructive hover:bg-destructive/10 border border-destructive/20 transition-colors"
                  >
                    <Trash2 size={12} /> Delete
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Desktop View: Table with horizontal scroll */}
          <div className="hidden sm:block rounded-2xl border border-border overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="text-left font-medium px-4 py-2.5">Category</th>
                  <th className="text-left font-medium px-4 py-2.5">Question</th>
                  <th className="text-left font-medium px-4 py-2.5">Critical</th>
                  <th className="text-left font-medium px-4 py-2.5">Status</th>
                  <th className="text-left font-medium px-4 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {detail.questions.map((q) => (
                  <tr key={q.id} className={cn("border-t border-border transition-colors hover:bg-muted/20", q.critical && "bg-red-500/5")}>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs font-medium text-muted-foreground">{q.category}</td>
                    <td className="px-4 py-2.5 max-w-md truncate font-medium text-foreground">{q.prompt}</td>
                    <td className="px-4 py-2.5">
                      {q.critical ? (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-500 text-white">CRITICAL</span>
                      ) : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-2.5 text-xs">{q.is_active ? "Active" : "Inactive"}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1">
                        <button onClick={() => setEditing(q)} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                          <Pencil size={13} />
                        </button>
                        <button onClick={() => setDeleting(q)} className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-muted transition-colors">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {(adding || editing) && (
        <QuestionForm
          configId={config.id}
          question={editing}
          onClose={() => { setAdding(false); setEditing(null) }}
          onSaved={() => { setAdding(false); setEditing(null); invalidate() }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete question"
          description="This removes the question permanently. Past attempts that already used it keep their recorded answer."
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleting(null)}
          onConfirm={() => deleteMutation.mutate()}
        />
      )}
    </div>
  )
}

function QuestionForm({ configId, question, onClose, onSaved }: {
  configId: string; question: AssessmentQuestion | null; onClose: () => void; onSaved: () => void
}) {
  const [category, setCategory] = useState(question?.category ?? "")
  const [prompt, setPrompt] = useState(question?.prompt ?? "")
  const [options, setOptions] = useState(question?.options ?? EMPTY_OPTIONS)
  const [critical, setCritical] = useState(question?.critical ?? false)
  const [rationale, setRationale] = useState(question?.rationale ?? "")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () => {
      const payload = { category, prompt, options, critical, rationale: rationale || null }
      return question ? updateAssessmentQuestionApi(question.id, payload) : createAssessmentQuestionApi(configId, payload)
    },
    onSuccess: onSaved,
    onError: (err) => setError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string") ? err.response.data.detail : "Couldn't save this question.",
    ),
  })

  const setOptionText = (i: number, text: string) => setOptions((prev) => prev.map((o, idx) => (idx === i ? { ...o, text } : o)))
  const setCorrect = (i: number) => setOptions((prev) => prev.map((o, idx) => ({ ...o, is_correct: idx === i })))

  const canSave = category.trim() && prompt.trim() && options.every((o) => o.text.trim())

  return (
    <Modal title={question ? "Edit question" : "Add question"} onClose={onClose} maxWidth="max-w-xl">
      <div className="flex flex-col gap-4">
        <Field label="Category">
          <input
            value={category} onChange={(e) => setCategory(e.target.value)} autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
          />
        </Field>
        <Field label="Scenario / question">
          <textarea
            value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
          />
        </Field>
        <Field label="Answer options — select the correct one">
          <div className="flex flex-col gap-2">
            {options.map((o, i) => (
              <div key={i} className="flex items-center gap-2">
                <input type="radio" checked={o.is_correct} onChange={() => setCorrect(i)} className="shrink-0" />
                <input
                  value={o.text} onChange={(e) => setOptionText(i, e.target.value)}
                  placeholder={`Option ${String.fromCharCode(65 + i)}`}
                  className="flex-1 h-9 px-3 border border-border bg-card text-foreground rounded-lg text-sm focus:outline-none focus:border-primary"
                />
              </div>
            ))}
          </div>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={critical} onChange={(e) => setCritical(e.target.checked)} />
          Critical scenario (safety, safeguarding, or student-movement judgment call)
        </label>
        <Field label="Rationale — shown to the instructor after answering">
          <textarea
            value={rationale} onChange={(e) => setRationale(e.target.value)} rows={2}
            className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
          />
        </Field>
        {error && (
          <div className="text-xs text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl px-3 py-2">{error}</div>
        )}
        <ModalActions onCancel={onClose} onConfirm={() => mutation.mutate()} loading={mutation.isPending} disabled={!canSave} label="Save" />
      </div>
    </Modal>
  )
}
