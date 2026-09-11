import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ClipboardCheck, Eye, FlaskConical, RotateCcw, Trophy } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/context/AuthContext";
import { fetchMyChecklists, resetPreviewAssignment } from "@/api/lms";
import { createPreviewAssignmentApi, getMyReachableProgramsApi, listLmsProgramsApi } from "@/api/lms_admin";
import { cn } from "@/lib/utils";

/** /learn/checklists — the LMS Program redesign (2026-08-21): every
 * checklist a student has been assigned, auto-populated at registration
 * time. For staff, also renders a Staff Sandbox Directory to preview & test
 * any program checklist with full student permissions.
 */
export default function LearnChecklists() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { roles = [] } = useAuth();
  const isStaff = roles.some((r) => ["admin", "operations", "facilitator", "instructor"].includes(r));

  const [launchingProgramId, setLaunchingProgramId] = useState<string | null>(null);
  const [resettingId, setResettingId] = useState<string | null>(null);

  const { data: checklists, isLoading } = useQuery({ queryKey: ["lms-my-checklists"], queryFn: fetchMyChecklists });

  const { data: allPrograms, isLoading: programsLoading } = useQuery({
    queryKey: ["lms-all-programs-preview"],
    queryFn: () => (roles.includes("instructor") && !roles.some((r) => ["admin", "operations", "facilitator"].includes(r))
      ? getMyReachableProgramsApi()
      : listLmsProgramsApi()),
    enabled: isStaff,
  });

  const handleLaunchPreview = async (programId: string) => {
    setLaunchingProgramId(programId);
    try {
      const res = await createPreviewAssignmentApi(programId);
      await queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
      void navigate({ to: `/learn/checklists/${res.assignment_id}` });
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Failed to launch student preview sandbox");
    } finally {
      setLaunchingProgramId(null);
    }
  };

  const handleReset = async (e: React.MouseEvent, assignmentId: string) => {
    e.stopPropagation();
    setResettingId(assignmentId);
    try {
      await resetPreviewAssignment(assignmentId);
      await queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
      toast.success("Sandbox progress reset to step 1");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to reset sandbox");
    } finally {
      setResettingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Programs</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            Every checklist your instructors and ops have assigned you — courses, mission runs, submissions, and manual steps, all in one place.
          </p>
        </div>
        {isStaff && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => void navigate({ to: "/lms-authoring/curriculum" })}
            className="border-primary/30 text-primary hover:bg-primary/10 self-start sm:self-center cursor-pointer"
          >
            Authoring Workspace
          </Button>
        )}
      </div>

      {isStaff && (
        <Card className="border-purple-500/30 bg-purple-950/15 p-5 flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="flex items-center justify-center size-8 rounded-xl bg-purple-500/20 text-purple-300 border border-purple-500/30">
                <FlaskConical className="size-4" />
              </div>
              <div>
                <h2 className="font-display text-base font-bold text-foreground">Staff Sandbox Directory</h2>
                <p className="text-xs text-muted-foreground">
                  Launch an instant student preview for any program with real student capabilities (gated steps, quizzes, submissions).
                </p>
              </div>
            </div>
          </div>

          {programsLoading ? (
            <p className="text-xs text-muted-foreground py-2">Loading system programs…</p>
          ) : (allPrograms ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground italic py-2">No programs available to preview.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-1">
              {(allPrograms ?? []).map((prog) => (
                <div
                  key={prog.id}
                  className="flex items-center justify-between gap-2.5 p-3 rounded-xl border border-border bg-card/70 hover:border-purple-500/40 transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-bold text-foreground truncate">{prog.name}</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      {prog.items?.length ?? 0} checklist {prog.items?.length === 1 ? "step" : "steps"}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    disabled={launchingProgramId === prog.id}
                    onClick={() => void handleLaunchPreview(prog.id)}
                    className="h-7 text-xs bg-purple-600 hover:bg-purple-700 text-white shrink-0 gap-1.5 cursor-pointer"
                  >
                    <Eye size={12} />
                    {launchingProgramId === prog.id ? "Opening…" : "Preview"}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {checklists && checklists.length === 0 && !isStaff && (
        <EmptyState title="No programs assigned yet" hint="Once you're assigned a program checklist, it'll show up here." />
      )}

      {checklists && checklists.length > 0 && (
        <div className="flex flex-col gap-4 max-w-2xl">
          {checklists.map((c) => (
            <Card
              key={c.assignment_id}
              className="cursor-pointer hover:ring-primary/30 transition-shadow p-5 flex flex-col gap-4"
              onClick={() => void navigate({ to: `/learn/checklists/${c.assignment_id}` })}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    {c.cohort_name && (
                      <span className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">{c.cohort_name}</span>
                    )}
                    {c.is_test && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-purple-500/15 border border-purple-500/30 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-purple-400">
                        <FlaskConical size={10} /> Staff Sandbox
                      </span>
                    )}
                  </div>
                  <div className="font-display text-lg font-semibold leading-snug">{c.name}</div>
                </div>
                <span
                  className={cn(
                    "shrink-0 text-[10px] font-bold uppercase tracking-wide rounded-md px-2 py-1",
                    c.pct === 100 ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : c.items_done > 0 ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
                  )}
                >
                  {c.pct === 100 ? "Complete" : c.items_done > 0 ? "In progress" : "Not started"}
                </span>
              </div>

              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{c.items_done} of {c.items_total} steps</span>
                  <span>{c.pct}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-muted relative overflow-hidden">
                  <div
                    className={cn("absolute inset-y-0 left-0 rounded-full", c.pct === 100 ? "bg-emerald-500" : "bg-primary")}
                    style={{ width: `${c.pct}%` }}
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-border">
                {c.pct === 100 ? (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Trophy className="size-3.5" />
                    {c.certificate_earned ? "Certificate earned" : c.certificate_required ? "Awaiting certificate" : "All done"}
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground min-w-0">
                    <ClipboardCheck className="size-3.5 shrink-0" />
                    <span className="truncate">Next: <span className="text-foreground font-medium">{c.next_item_title}</span></span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  {c.is_test && (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={resettingId === c.assignment_id}
                      onClick={(e) => void handleReset(e, c.assignment_id)}
                      className="h-7 px-2 text-xs font-semibold text-purple-400 hover:text-purple-300 hover:bg-purple-500/10 gap-1 cursor-pointer"
                      title="Reset progress back to Step 1"
                    >
                      <RotateCcw className={cn("size-3", resettingId === c.assignment_id && "animate-spin")} />
                      Reset
                    </Button>
                  )}
                  <span className="shrink-0 text-sm font-semibold text-primary flex items-center gap-1">
                    {c.items_done > 0 ? "Continue" : "Start"}
                    <ChevronRight className="size-4" />
                  </span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
