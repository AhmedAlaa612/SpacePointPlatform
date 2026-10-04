import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Eye, Users, User, Plus, Loader2, AlertCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  getObserverTeamsApi,
  tryAsObserverApi,
  type TryAsObserverPayload,
} from "@/api/lms_admin";
import { cn } from "@/lib/utils";

interface ObserverTeamModalProps {
  cohortId: string;
  cohortName?: string;
  open: boolean;
  onClose: () => void;
  onSuccess?: (assignmentId: string) => void;
}

export function ObserverTeamModal({
  cohortId,
  cohortName,
  open,
  onClose,
  onSuccess,
}: ObserverTeamModalProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [teamAction, setTeamAction] = useState<"none" | "join" | "create">("none");
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");
  const [newTeamName, setNewTeamName] = useState<string>("");

  const { data: observerTeams = [], isLoading: loadingTeams } = useQuery({
    queryKey: ["cohort-observer-teams", cohortId],
    queryFn: () => getObserverTeamsApi(cohortId),
    enabled: open && !!cohortId,
  });

  useEffect(() => {
    if (open) {
      setTeamAction("none");
      setSelectedTeamId(observerTeams.length > 0 ? observerTeams[0].id : "");
      setNewTeamName("");
    }
  }, [open, observerTeams]);

  const tryMutation = useMutation({
    mutationFn: async (payload: TryAsObserverPayload) => {
      return await tryAsObserverApi(cohortId, payload);
    },
    onSuccess: async (data) => {
      toast.success("Entered Observer Mode");
      void queryClient.invalidateQueries({ queryKey: ["lms-checklist", data.assignment_id] });
      void queryClient.invalidateQueries({ queryKey: ["cohort-observer-teams", cohortId] });
      onClose();
      if (onSuccess) {
        onSuccess(data.assignment_id);
      } else {
        await navigate({ to: `/learn/checklists/${data.assignment_id}` });
      }
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to enter observer mode";
      toast.error(msg);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: TryAsObserverPayload = {
      team_action: teamAction,
    };
    if (teamAction === "join") {
      if (!selectedTeamId) {
        toast.error("Please select an observer team to join");
        return;
      }
      payload.team_id = selectedTeamId;
    } else if (teamAction === "create") {
      if (!newTeamName.trim()) {
        toast.error("Please enter a team name");
        return;
      }
      payload.team_name = newTeamName.trim();
    }
    tryMutation.mutate(payload);
  };

  return (
    <Dialog open={open} onOpenChange={(val) => !val && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-500 border border-indigo-500/20">
              <Eye className="w-4 h-4" />
            </div>
            <DialogTitle className="text-lg">Try as Observer</DialogTitle>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            {cohortName ? `Cohort: ${cohortName}. ` : ""}
            Test the full student experience — quizzes, missions, checklists, and scoring.
            Observer activity is safely labeled and isolated in a sandbox.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Choose Team Setup
          </div>

          <div className="flex flex-col gap-2.5">
            {/* Option 1: None / Unassigned (Normal Student Flow) */}
            <label
              className={cn(
                "flex items-start gap-3 p-3 rounded-xl border transition-all cursor-pointer text-left",
                teamAction === "none"
                  ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                  : "border-border bg-card hover:bg-muted/40",
              )}
            >
              <input
                type="radio"
                name="team_action"
                value="none"
                checked={teamAction === "none"}
                onChange={() => setTeamAction("none")}
                className="mt-1 accent-primary"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 font-medium text-sm text-foreground">
                  <User className="w-3.5 h-3.5 text-muted-foreground" />
                  Continue without a team
                  <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.2 rounded bg-muted text-muted-foreground ml-1">
                    Normal Flow
                  </span>
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Start unassigned just like a new student. You can join or create a team later from your roadmap board.
                </div>
              </div>
            </label>

            {/* Option 2: Join Existing Observer Team */}
            <label
              className={cn(
                "flex items-start gap-3 p-3 rounded-xl border transition-all cursor-pointer text-left",
                teamAction === "join"
                  ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                  : "border-border bg-card hover:bg-muted/40",
              )}
            >
              <input
                type="radio"
                name="team_action"
                value="join"
                checked={teamAction === "join"}
                onChange={() => setTeamAction("join")}
                className="mt-1 accent-primary"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 font-medium text-sm text-foreground">
                  <Users className="w-3.5 h-3.5 text-muted-foreground" />
                  Join existing observer team
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Collaborate in an existing sandbox team with other observers and test team submissions.
                </div>

                {teamAction === "join" && (
                  <div className="mt-2.5">
                    {loadingTeams ? (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground py-1">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading observer teams…
                      </div>
                    ) : observerTeams.length === 0 ? (
                      <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                        No observer teams exist yet in this cohort. Please create one below.
                      </div>
                    ) : (
                      <select
                        value={selectedTeamId}
                        onChange={(e) => setSelectedTeamId(e.target.value)}
                        className="w-full h-9 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs font-medium focus:outline-none focus:border-primary cursor-pointer"
                      >
                        <option value="">Select an observer team…</option>
                        {observerTeams.map((team) => (
                          <option key={team.id} value={team.id}>
                            {team.name} ({team.member_count} member{team.member_count === 1 ? "" : "s"})
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                )}
              </div>
            </label>

            {/* Option 3: Create New Observer Team */}
            <label
              className={cn(
                "flex items-start gap-3 p-3 rounded-xl border transition-all cursor-pointer text-left",
                teamAction === "create"
                  ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                  : "border-border bg-card hover:bg-muted/40",
              )}
            >
              <input
                type="radio"
                name="team_action"
                value="create"
                checked={teamAction === "create"}
                onChange={() => setTeamAction("create")}
                className="mt-1 accent-primary"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 font-medium text-sm text-foreground">
                  <Plus className="w-3.5 h-3.5 text-muted-foreground" />
                  Create a new observer team
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Form a fresh observer sandbox team for testing full team workflows and judging.
                </div>

                {teamAction === "create" && (
                  <div className="mt-2.5">
                    <input
                      type="text"
                      value={newTeamName}
                      onChange={(e) => setNewTeamName(e.target.value)}
                      placeholder="e.g. Observer Team Alpha"
                      className="w-full h-9 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs font-medium focus:outline-none focus:border-primary"
                      autoFocus
                    />
                  </div>
                )}
              </div>
            </label>
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onClose}
              disabled={tryMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={
                tryMutation.isPending ||
                (teamAction === "join" && !selectedTeamId) ||
                (teamAction === "create" && !newTeamName.trim())
              }
              className="gap-1.5"
            >
              {tryMutation.isPending ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Starting…
                </>
              ) : (
                <>
                  <Eye className="w-3.5 h-3.5" /> Start Observer Mode
                </>
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
