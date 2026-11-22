import { FileText } from "lucide-react"
import type { ProgramCertificateTemplate } from "@/types/sessions"
import { CompetitionCertificatesModal } from "@/pages/admin/components/CompetitionCertificatesModal"

export function CohortCertificatesPanel({
  cohortId,
  cohortName,
  programName,
  onOpenExcuseLetter,
  readOnly = false,
}: {
  cohortId: string
  cohortName: string
  programName?: string
  programTemplates?: ProgramCertificateTemplate[]
  onOpenExcuseLetter?: () => void
  readOnly?: boolean
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-base font-semibold text-foreground">Certificates & Excuse Letters</h2>
        {!readOnly && onOpenExcuseLetter && (
          <button
            type="button"
            onClick={onOpenExcuseLetter}
            className="flex items-center gap-1.5 h-9 px-3.5 border border-border rounded-[10px] text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            <FileText size={14} className="text-primary" /> Excuse Letter
          </button>
        )}
      </div>

      <CompetitionCertificatesModal
        cohortId={cohortId}
        cohortName={cohortName}
        programName={programName}
        embedded
        readOnly={readOnly}
      />
    </div>
  )
}
