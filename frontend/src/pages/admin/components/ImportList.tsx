import { useRef, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { X, Download, Upload, CheckCircle2 } from "lucide-react"
import type { Cohort, ImportBatch, ImportBatchListItem, ImportRowDisposition } from "@/types/sessions"
import {
  downloadImportTemplateApi, listImportBatchesApi, dryRunImportApi, commitImportBatchApi,
} from "@/api/sessions/imports"
import { Field } from "@/pages/admin/components/common"

const DISPOSITION_LABEL: Record<ImportRowDisposition, string> = {
  create: "New contact",
  link: "Linked to existing contact",
  already_registered: "Already registered",
  review: "Needs review",
  error: "Error",
}

const DISPOSITION_COLOR: Record<ImportRowDisposition, string> = {
  create: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  link: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  already_registered: "bg-muted text-muted-foreground",
  review: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  error: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
}

/* ================================================================== */
/* Import list modal — upload a sheet for THIS cohort (no separate     */
/* cohort-picker page; the cohort is already known from context).      */
/* Wider than the shared Modal, same reasoning as CohortDetailDrawer.   */
/* ================================================================== */
export function ImportListModal({ cohort, onClose, onImported }: {
  cohort: Cohort; onClose: () => void; onImported: () => void
}) {
  const [batch, setBatch] = useState<ImportBatch | null>(null)
  const [committed, setCommitted] = useState(false)
  const [source, setSource] = useState<"b2b_sheet" | "backfill">("b2b_sheet")
  const [sendEmails, setSendEmails] = useState(true)
  const [error, setError] = useState("")
  const fileRef = useRef<HTMLInputElement>(null)

  const { data: history = [] } = useQuery<ImportBatchListItem[]>({
    queryKey: ["sessions-import-batches", cohort.id],
    queryFn: () => listImportBatchesApi(cohort.id),
  })

  const dryRunMutation = useMutation({
    mutationFn: () => {
      const file = fileRef.current?.files?.[0]
      if (!file) throw new Error("Choose a file first")
      return dryRunImportApi({ cohortId: cohort.id, file, source, sendEmails })
    },
    onSuccess: (b) => { setBatch(b); setError("") },
    onError: (e: any) => setError(e?.response?.data?.detail ?? e?.message ?? "Failed to preview the file"),
  })

  const commitMutation = useMutation({
    mutationFn: () => commitImportBatchApi(batch!.id),
    onSuccess: () => { setCommitted(true); onImported() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to commit the import"),
  })

  const handleDownloadTemplate = async () => {
    const blob = await downloadImportTemplateApi()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "spacepoint_import_template.xlsx"
    a.click()
    URL.revokeObjectURL(url)
  }

  const startOver = () => {
    setBatch(null)
    setCommitted(false)
    setError("")
    if (fileRef.current) fileRef.current.value = ""
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4">
      <div className="w-full max-w-3xl bg-card border border-border rounded-2xl p-6 flex flex-col gap-4 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-base font-semibold text-foreground">Import list — {cohort.name}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Upload a spreadsheet of students to register into this cohort.</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
            <X size={16} />
          </button>
        </div>

        {!batch && (
          <div className="flex flex-col gap-3">
            <button
              onClick={handleDownloadTemplate}
              className="flex items-center gap-1.5 self-start h-9 px-3 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              <Download size={14} /> Download template
            </button>
            <Field label="File">
              <input
                ref={fileRef} type="file" accept=".xlsx"
                className="w-full text-sm text-foreground file:mr-3 file:h-9 file:px-3 file:rounded-xl file:border-0 file:bg-muted file:text-foreground file:text-sm file:font-medium file:cursor-pointer cursor-pointer"
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Source">
                <select
                  value={source} onChange={(e) => setSource(e.target.value as "b2b_sheet" | "backfill")}
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
                >
                  <option value="b2b_sheet">B2B / partner sheet</option>
                  <option value="backfill">Historical backfill</option>
                </select>
              </Field>
              <Field label="Ticket emails">
                <label className="flex items-center gap-2 h-10 text-sm text-foreground cursor-pointer select-none">
                  <input type="checkbox" checked={sendEmails} onChange={(e) => setSendEmails(e.target.checked)} />
                  Send ticket emails once imported
                </label>
              </Field>
            </div>
            {error && <p className="text-xs text-red-500">{error}</p>}
            <button
              onClick={() => dryRunMutation.mutate()}
              disabled={dryRunMutation.isPending}
              className="flex items-center justify-center gap-1.5 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
            >
              <Upload size={14} /> {dryRunMutation.isPending ? "Previewing…" : "Preview"}
            </button>
          </div>
        )}

        {batch && !committed && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              {(["total", "create", "link", "already_registered", "review", "error"] as const).map((k) => (
                <span key={k} className="text-xs font-medium px-2.5 py-1 rounded-full bg-background border border-border text-foreground">
                  {k === "total" ? "Total" : DISPOSITION_LABEL[k as ImportRowDisposition]}: {batch.summary[k] ?? 0}
                </span>
              ))}
            </div>
            <div className="border border-border rounded-xl overflow-hidden">
              <div className="max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="bg-muted sticky top-0">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">#</th>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Student</th>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Result</th>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batch.rows.map((r) => (
                      <tr key={r.row_number} className="border-t border-border">
                        <td className="px-3 py-1.5 text-muted-foreground">{r.row_number}</td>
                        <td className="px-3 py-1.5 text-foreground">{String(r.data?.student_name ?? "—")}</td>
                        <td className="px-3 py-1.5">
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${DISPOSITION_COLOR[r.disposition]}`}>
                            {DISPOSITION_LABEL[r.disposition]}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-muted-foreground">{r.reason ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {error && <p className="text-xs text-red-500">{error}</p>}
            <div className="flex gap-2">
              <button
                onClick={startOver}
                className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
              >
                Start over
              </button>
              <button
                onClick={() => commitMutation.mutate()}
                disabled={commitMutation.isPending || batch.summary.total === batch.summary.error}
                className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50"
              >
                {commitMutation.isPending ? "Committing…" : `Commit ${batch.summary.total - batch.summary.error} row${batch.summary.total - batch.summary.error !== 1 ? "s" : ""}`}
              </button>
            </div>
          </div>
        )}

        {committed && (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <CheckCircle2 size={28} className="text-emerald-500" />
            <p className="text-sm font-medium text-foreground">Import committed</p>
            <p className="text-xs text-muted-foreground">The roster has been updated.</p>
            <div className="flex gap-2 mt-2">
              <button onClick={startOver} className="h-9 px-4 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors">
                Import another file
              </button>
              <button onClick={onClose} className="h-9 px-4 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors">
                Done
              </button>
            </div>
          </div>
        )}

        {history.length > 0 && (
          <div className="border-t border-border pt-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Past imports for this cohort</p>
            <div className="flex flex-col gap-1.5">
              {history.map((b) => (
                <div key={b.id} className="flex items-center justify-between text-xs px-3 py-2 bg-background border border-border rounded-xl">
                  <span className="text-foreground truncate">{b.filename}</span>
                  <span className="text-muted-foreground flex-shrink-0 ml-2">
                    {b.status} · {b.summary.total ?? 0} rows · {new Date(b.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
