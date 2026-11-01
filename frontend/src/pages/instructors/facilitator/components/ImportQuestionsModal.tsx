import { useState } from "react"
import { CheckCircle, Download, FileSpreadsheet, Upload } from "lucide-react"
import {
  downloadPreQuizTemplateApi,
  importPreQuizQuestionsApi,
  type PreSessionQuizImportResult,
  type PreSessionQuizPreset,
} from "@/api/sessions/pre_session_quiz"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { Field, Modal, ModalActions } from "@/pages/admin/components/common"

interface ImportQuestionsModalProps {
  existingPresets: PreSessionQuizPreset[]
  onClose: () => void
  onImportSuccess: () => void
}

export function ImportQuestionsModal({
  existingPresets,
  onClose,
  onImportSuccess,
}: ImportQuestionsModalProps) {
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [topicOverride, setTopicOverride] = useState("")
  const [presetTargetId, setPresetTargetId] = useState("")
  const [loading, setLoading] = useState(false)
  const [downloadingTemplate, setDownloadingTemplate] = useState(false)
  const [result, setResult] = useState<PreSessionQuizImportResult | null>(null)
  const [error, setError] = useState("")

  const handleDownload = async () => {
    try {
      setDownloadingTemplate(true)
      await downloadPreQuizTemplateApi()
      toast.success("Excel template downloaded")
    } catch (e) {
      toast.error(getErrorMessage(e, "Could not download template"))
    } finally {
      setDownloadingTemplate(false)
    }
  }

  const handleImport = async () => {
    if (!file) return
    try {
      setLoading(true)
      setError("")
      setResult(null)
      const res = await importPreQuizQuestionsApi(
        file,
        topicOverride.trim() || undefined,
        presetTargetId.trim() || undefined
      )
      setResult(res)
      if (res.created > 0) {
        toast.success(`Successfully imported ${res.created} questions!`)
        onImportSuccess()
      }
    } catch (e) {
      setError(getErrorMessage(e, "Bulk import failed"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title="Bulk Import Questions (Excel / CSV)" onClose={onClose} maxWidth="sm:max-w-xl max-w-xl">
      <div className="flex flex-col gap-4">
        {/* Template info card */}
        <div className="p-3 rounded-xl border border-primary/25 bg-primary/5 flex items-center justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
              <FileSpreadsheet size={14} className="text-primary" />
              Standard SpacePoint Template
            </span>
            <p className="text-[11px] text-muted-foreground">
              Supports .xlsx and .csv workbooks. Auto-detects headers: ID, Topic/Section, Question, Options A-D, Answer Key, Rationale, Critical?, Points, and Photo.
            </p>
          </div>
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloadingTemplate}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-primary/40 bg-primary/10 hover:bg-primary/20 text-xs font-semibold text-primary transition-colors cursor-pointer shrink-0"
          >
            <Download size={13} />
            {downloadingTemplate ? "Downloading..." : "Template"}
          </button>
        </div>

        {/* File Dropzone */}
        <Field label="Upload Spreadsheet (.xlsx, .csv)">
          <div className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-border hover:border-primary/50 rounded-2xl bg-card transition-colors">
            <input
              type="file"
              accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
              onChange={(e) => {
                if (e.target.files?.[0]) setFile(e.target.files[0])
              }}
              className="hidden"
              id="bulk-import-file-input"
            />
            <label
              htmlFor="bulk-import-file-input"
              className="flex flex-col items-center gap-2 cursor-pointer text-center"
            >
              <Upload size={24} className="text-muted-foreground" />
              <span className="text-xs font-semibold text-foreground">
                {file ? file.name : "Click or drag spreadsheet here"}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {file ? `${(file.size / 1024).toFixed(1)} KB` : "Supports Excel (.xlsx) or CSV (.csv)"}
              </span>
            </label>
          </div>
        </Field>

        {/* Options */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Assign to Preset (Optional)">
            <select
              value={presetTargetId}
              onChange={(e) => setPresetTargetId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-xs focus:outline-none focus:border-primary"
            >
              <option value="">Don't assign — Bank only</option>
              {existingPresets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.preset_type || "readiness"})
                </option>
              ))}
            </select>
          </Field>

          <Field label="Override Topic (Optional)">
            <input
              value={topicOverride}
              onChange={(e) => setTopicOverride(e.target.value)}
              placeholder="Leave blank to use sheet's Category"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-xs focus:outline-none focus:border-primary"
            />
          </Field>
        </div>

        {/* Results / Feedback */}
        {result && (
          <div className="flex flex-col gap-2 p-3.5 rounded-xl border border-border bg-card">
            <div className="flex items-center gap-2 text-xs font-bold text-emerald-600 dark:text-emerald-400">
              <CheckCircle size={15} />
              <span>Created {result.created} new question{result.created === 1 ? "" : "s"} in bank!</span>
            </div>
            {result.errors.length > 0 && (
              <div className="flex flex-col gap-1 mt-1">
                <span className="text-[11px] font-bold text-amber-600 dark:text-amber-400">
                  {result.errors.length} row warning{result.errors.length === 1 ? "" : "s"}:
                </span>
                <div className="max-h-28 overflow-y-auto text-[11px] text-muted-foreground space-y-1 bg-muted/40 p-2 rounded-lg">
                  {result.errors.map((err, idx) => (
                    <div key={idx} className="font-mono">{err}</div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {error && <p className="text-xs text-red-500 bg-red-500/10 p-2.5 rounded-xl">{error}</p>}

        <ModalActions
          onCancel={onClose}
          onConfirm={handleImport}
          loading={loading}
          disabled={!file}
          label="Start Import"
        />
      </div>
    </Modal>
  )
}
