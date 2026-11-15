import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { Program } from "@/types/sessions"
import {
  createLmsProgramApi,
  getLmsProgramApi,
  listLmsProgramsApi,
} from "@/api/lms_admin"
import { Spinner } from "@/pages/admin/components/common"
import {
  CreateChecklistPrompt,
  ProgramTemplateEditor,
} from "@/pages/lms-authoring/components/LmsChecklistAuthoring"
import { ProgramMissionsPanel } from "@/pages/lms-authoring/components/LmsProgressAndMissions"
import { LmsComponentConfigPanel } from "@/pages/lms-authoring/components/LmsComponentConfigPanel"
import { LmsHintStationAuthoring } from "@/pages/lms-authoring/components/LmsHintStationAuthoring"

type SubTab = "checklist" | "missions" | "components" | "hints"

const SUBTAB_LABEL: Record<SubTab, string> = {
  checklist: "Checklist",
  missions: "Missions",
  components: "Components",
  hints: "Hints",
}

export function ProgramLmsSection({ program }: { program: Program }) {
  const queryClient = useQueryClient()
  const [subtab, setSubtab] = useState<SubTab>("checklist")

  const { data: lmsPrograms = [], isLoading } = useQuery({
    queryKey: ["lms-programs", program.id],
    queryFn: () => listLmsProgramsApi(program.id),
  })
  const lmsProgramId = lmsPrograms[0]?.id ?? ""

  const { data: lmsProgramDetail } = useQuery({
    queryKey: ["lms-program", lmsProgramId],
    queryFn: () => getLmsProgramApi(lmsProgramId),
    enabled: !!lmsProgramId,
  })

  const effective = lmsProgramDetail ?? lmsPrograms[0] ?? null

  const createMutation = useMutation({
    mutationFn: (name: string) =>
      createLmsProgramApi({ program_id: program.id, name }),
    onSuccess: (created) => {
      queryClient.setQueryData(["lms-programs", program.id], [created])
      queryClient.setQueryData(["lms-program", created.id], created)
    },
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["lms-programs", program.id] })
    if (effective?.id) {
      queryClient.invalidateQueries({ queryKey: ["lms-program", effective.id] })
    }
  }

  if (isLoading) return <Spinner />

  if (!effective) {
    return (
      <CreateChecklistPrompt
        onCreate={(name) => createMutation.mutate(name)}
        pending={createMutation.isPending}
      />
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar">
        {(["checklist", "missions", "components", "hints"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setSubtab(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer shrink-0 whitespace-nowrap ${
              subtab === t
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {SUBTAB_LABEL[t]}
          </button>
        ))}
      </div>

      {subtab === "checklist" && (
        <ProgramTemplateEditor
          program={effective}
          onChanged={refresh}
          readOnly={false}
        />
      )}
      {subtab === "missions" && (
        <ProgramMissionsPanel
          program={effective}
          onChanged={refresh}
          readOnly={false}
        />
      )}
      {subtab === "components" && (
        <LmsComponentConfigPanel
          ownerType="program"
          ownerId={effective.id}
          isStaff
        />
      )}
      {subtab === "hints" && (
        <LmsHintStationAuthoring programId={program.id} scope="program" />
      )}
    </div>
  )
}
