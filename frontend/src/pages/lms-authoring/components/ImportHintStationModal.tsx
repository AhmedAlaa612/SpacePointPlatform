import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  Loader2,
  Search,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { getProgramsApi } from "@/api/sessions/programs";
import { getCohortsApi } from "@/api/sessions/cohorts";
import {
  listProgramChallengesAdminApi,
  listCohortChallengesAdminApi,
  importCohortHintsAdminApi,
  importProgramHintsAdminApi,
  type CohortHintChallenge,
} from "@/api/hint_station";
import type { Cohort, Program } from "@/types/sessions";
import { cn } from "@/lib/utils";

interface SourceSelection {
  type: "program" | "cohort";
  id: string;
  label: string;
}

export function ImportHintStationModal({
  open,
  onClose,
  targetScope,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  targetScope: { type: "program"; programId: string } | { type: "cohort"; cohortId: string; cohortName?: string };
  onSuccess?: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [selectedProgramId, setSelectedProgramId] = useState<string>("");
  const [source, setSource] = useState<SourceSelection | null>(null);
  const [selectedChallengeIds, setSelectedChallengeIds] = useState<Set<string>>(new Set());
  const [replaceExisting, setReplaceExisting] = useState<boolean>(false);
  const [searchFilter, setSearchFilter] = useState<string>("");

  // ── Programs Query ────────────────────────────────────────────────────────
  const { data: programs = [] } = useQuery<Program[]>({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
    enabled: open,
  });

  useEffect(() => {
    if (open) {
      const defaultProgId =
        targetScope.type === "program" ? targetScope.programId : programs[0]?.id || "";
      setSelectedProgramId(defaultProgId);
      setSource(null);
      setSelectedChallengeIds(new Set());
      setReplaceExisting(false);
      setSearchFilter("");
    }
  }, [open, targetScope, programs]);

  // ── Cohorts Query for selected program ────────────────────────────────────
  const { data: cohorts = [] } = useQuery<Cohort[]>({
    queryKey: ["sessions-cohorts-for-prog", selectedProgramId],
    queryFn: () => getCohortsApi(selectedProgramId),
    enabled: open && !!selectedProgramId,
  });

  // ── Source Challenges Query ───────────────────────────────────────────────
  const isProgramSource = source?.type === "program";
  const isCohortSource = source?.type === "cohort";

  const { data: programChallenges = [], isLoading: loadingProgramChallenges } = useQuery<CohortHintChallenge[]>({
    queryKey: ["admin-hints-program", source?.id],
    queryFn: () => listProgramChallengesAdminApi(source!.id),
    enabled: open && isProgramSource && !!source?.id,
  });

  const { data: cohortChallenges = [], isLoading: loadingCohortChallenges } = useQuery<CohortHintChallenge[]>({
    queryKey: ["admin-hints-cohort", source?.id],
    queryFn: () => listCohortChallengesAdminApi(source!.id),
    enabled: open && isCohortSource && !!source?.id,
  });

  const sourceChallenges = isProgramSource ? programChallenges : isCohortSource ? cohortChallenges : [];
  const loadingChallenges = isProgramSource ? loadingProgramChallenges : isCohortSource ? loadingCohortChallenges : false;

  // Filter challenges by search query
  const filteredChallenges = sourceChallenges.filter((ch) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      ch.title.toLowerCase().includes(q) ||
      (ch.topic && ch.topic.toLowerCase().includes(q)) ||
      ch.description.toLowerCase().includes(q)
    );
  });

  // Toggle single challenge selection
  const toggleSelect = (id: string) => {
    setSelectedChallengeIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Toggle select all
  const toggleSelectAll = () => {
    if (selectedChallengeIds.size === filteredChallenges.length && filteredChallenges.length > 0) {
      setSelectedChallengeIds(new Set());
    } else {
      setSelectedChallengeIds(new Set(filteredChallenges.map((c) => c.id)));
    }
  };

  // ── Import Mutation ───────────────────────────────────────────────────────
  const importMutation = useMutation({
    mutationFn: async () => {
      if (!source) throw new Error("Please select a source");
      const ids = selectedChallengeIds.size > 0 ? Array.from(selectedChallengeIds) : undefined;

      if (targetScope.type === "cohort") {
        return await importCohortHintsAdminApi(targetScope.cohortId, {
          source_type: source.type,
          source_id: source.id,
          challenge_ids: ids,
          replace_existing: replaceExisting,
        });
      } else {
        return await importProgramHintsAdminApi(targetScope.programId, {
          source_type: source.type,
          source_id: source.id,
          challenge_ids: ids,
          replace_existing: replaceExisting,
        });
      }
    },
    onSuccess: (res) => {
      toast.success(`Successfully imported ${res.cloned_count} challenges!`);
      if (targetScope.type === "cohort") {
        void queryClient.invalidateQueries({ queryKey: ["admin-hints-cohort", targetScope.cohortId] });
      } else {
        void queryClient.invalidateQueries({ queryKey: ["admin-hints-program", targetScope.programId] });
      }
      onSuccess?.();
      onClose();
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Failed to import challenges");
    },
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col p-6 overflow-hidden">
        <DialogHeader className="gap-1 border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <div className="size-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <Copy size={16} />
            </div>
            <DialogTitle className="font-display text-lg font-bold">
              Import Hint Station Challenges
            </DialogTitle>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            Copy challenge cards and hints from another program template or cohort override.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4 flex flex-col gap-4">
          {/* Step 1: Pick Program and Source Type */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                1. Filter by Program
              </label>
              <select
                value={selectedProgramId}
                onChange={(e) => {
                  setSelectedProgramId(e.target.value);
                  setSource(null);
                  setSelectedChallengeIds(new Set());
                }}
                className="w-full h-9 px-3 border border-border bg-card text-foreground rounded-xl text-xs font-medium focus:outline-none focus:border-primary"
              >
                <option value="">Select a program…</option>
                {programs.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider block mb-1.5">
                2. Select Source Template or Cohort
              </label>
              <div className="flex flex-wrap gap-2">
                {selectedProgramId && (
                  <button
                    onClick={() => {
                      setSource({ type: "program", id: selectedProgramId, label: "Program Baseline" });
                      setSelectedChallengeIds(new Set());
                    }}
                    className={cn(
                      "px-3 py-1.5 rounded-lg border text-xs font-semibold cursor-pointer transition-all",
                      source?.type === "program" && source.id === selectedProgramId
                        ? "bg-primary text-primary-foreground border-primary shadow-sm"
                        : "bg-card border-border hover:bg-muted text-foreground",
                    )}
                  >
                    Program Baseline
                  </button>
                )}

                {cohorts.map((c) => {
                  const isCurrent = targetScope.type === "cohort" && targetScope.cohortId === c.id;
                  if (isCurrent) return null; // Can't import from self
                  const isSelected = source?.type === "cohort" && source.id === c.id;

                  return (
                    <button
                      key={c.id}
                      onClick={() => {
                        setSource({ type: "cohort", id: c.id, label: c.name });
                        setSelectedChallengeIds(new Set());
                      }}
                      className={cn(
                        "px-3 py-1.5 rounded-lg border text-xs font-semibold cursor-pointer transition-all",
                        isSelected
                          ? "bg-primary text-primary-foreground border-primary shadow-sm"
                          : "bg-card border-border hover:bg-muted text-foreground",
                      )}
                    >
                      {c.name}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Step 2: Challenges List from Selected Source */}
          {source && (
            <div className="flex flex-col gap-3 border-t border-border pt-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Available Challenges from:
                  </span>
                  <span className="text-xs font-bold text-primary bg-primary/10 border border-primary/20 px-2 py-0.5 rounded-md">
                    {source.label}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="Filter challenges…"
                      value={searchFilter}
                      onChange={(e) => setSearchFilter(e.target.value)}
                      className="h-8 pl-8 pr-3 text-xs border border-border bg-card rounded-lg focus:outline-none focus:border-primary w-40 sm:w-48"
                    />
                  </div>

                  <button
                    onClick={toggleSelectAll}
                    disabled={filteredChallenges.length === 0}
                    className="h-8 px-2.5 text-xs font-semibold border border-border rounded-lg bg-muted/60 hover:bg-muted transition-colors cursor-pointer shrink-0"
                  >
                    {selectedChallengeIds.size === filteredChallenges.length && filteredChallenges.length > 0
                      ? "Deselect All"
                      : "Select All"}
                  </button>
                </div>
              </div>

              {loadingChallenges ? (
                <div className="flex items-center justify-center p-8">
                  <Loader2 className="size-6 animate-spin text-primary" />
                </div>
              ) : filteredChallenges.length === 0 ? (
                <div className="p-6 text-center rounded-xl border border-dashed border-border bg-card/60">
                  <p className="text-xs text-muted-foreground">
                    No challenges found in this source.
                  </p>
                </div>
              ) : (
                <div className="max-h-60 overflow-y-auto divide-y divide-border border border-border rounded-xl bg-card">
                  {filteredChallenges.map((ch) => {
                    const isChecked = selectedChallengeIds.has(ch.id);

                    return (
                      <div
                        key={ch.id}
                        onClick={() => toggleSelect(ch.id)}
                        className={cn(
                          "flex items-start gap-3 p-3 text-xs cursor-pointer transition-colors select-none",
                          isChecked ? "bg-primary/5 hover:bg-primary/10" : "hover:bg-muted/30",
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => {}}
                          className="mt-0.5 rounded border-border text-primary cursor-pointer"
                        />
                        <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-foreground">{ch.title}</span>
                            {ch.topic && (
                              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                                {ch.topic}
                              </span>
                            )}
                          </div>
                          <p className="text-muted-foreground text-[11px] line-clamp-1">{ch.description}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px] text-muted-foreground font-mono">
                              {ch.cards.length} {ch.cards.length === 1 ? "hint card" : "hint cards"}
                            </span>
                            <span className="text-[10px] text-muted-foreground font-mono">
                              Max score: {ch.max_points} pts
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Step 3: Append vs Replace Mode */}
              <div className="p-3.5 rounded-xl border border-border bg-muted/20 flex items-center justify-between gap-4">
                <div className="flex flex-col gap-0.5">
                  <span className="text-xs font-bold text-foreground">Import Mode</span>
                  <span className="text-[11px] text-muted-foreground">
                    {replaceExisting
                      ? "Replace mode will remove existing challenges in this target before adding imported ones."
                      : "Append mode will keep current challenges and add imported ones at the end."}
                  </span>
                </div>

                <div className="flex items-center p-0.5 rounded-lg border border-border bg-card text-xs font-semibold shrink-0">
                  <button
                    onClick={() => setReplaceExisting(false)}
                    className={cn(
                      "px-2.5 py-1 rounded-md transition-colors cursor-pointer",
                      !replaceExisting ? "bg-primary text-primary-foreground font-bold" : "text-muted-foreground",
                    )}
                  >
                    Append
                  </button>
                  <button
                    onClick={() => setReplaceExisting(true)}
                    className={cn(
                      "px-2.5 py-1 rounded-md transition-colors cursor-pointer",
                      replaceExisting ? "bg-destructive text-destructive-foreground font-bold" : "text-muted-foreground",
                    )}
                  >
                    Replace
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Actions */}
        <div className="border-t border-border pt-4 flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">
            {selectedChallengeIds.size > 0
              ? `${selectedChallengeIds.size} challenges selected`
              : source
              ? "All source challenges will be imported"
              : "Select a source to begin"}
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl border border-border text-xs font-semibold hover:bg-muted transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={() => importMutation.mutate()}
              disabled={!source || importMutation.isPending}
              className="px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 disabled:opacity-40 transition-all cursor-pointer flex items-center gap-1.5"
            >
              {importMutation.isPending ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>Importing…</span>
                </>
              ) : (
                <>
                  <Check size={13} />
                  <span>Import Challenges</span>
                </>
              )}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
