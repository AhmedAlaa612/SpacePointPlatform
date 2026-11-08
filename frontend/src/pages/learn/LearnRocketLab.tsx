import { useMemo } from "react";
import { Link, useSearch } from "@tanstack/react-router";
import { ArrowLeft, Rocket, Sparkles, CheckCircle2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { completeChecklistItem } from "@/api/lms";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export default function LearnRocketLab() {
  const search = useSearch({ strict: false }) as {
    program?: string;
    itemId?: string;
    mod?: string;
    pathway?: string;
  };
  const assignmentId = search.program;
  const itemId = search.itemId;
  const moduleParam = search.mod;
  const pathwayParam = search.pathway;

  const queryClient = useQueryClient();
  const toast = useToast();

  const completeMutation = useMutation({
    mutationFn: () => {
      if (!assignmentId || !itemId) throw new Error("Missing assignment or item ID");
      return completeChecklistItem(assignmentId, itemId);
    },
    onSuccess: () => {
      toast.success("Simulation step completed!");
      if (assignmentId) {
        void queryClient.invalidateQueries({ queryKey: ["lms-checklist", assignmentId] });
      }
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to mark item complete";
      toast.error(msg);
    },
  });

  const iframeSrc = useMemo(() => {
    const params = new URLSearchParams();
    if (moduleParam) params.set("mod", moduleParam);
    if (pathwayParam) params.set("pathway", pathwayParam);
    const qs = params.toString();
    return `/rocketlab/index.html${qs ? `?${qs}` : ""}`;
  }, [moduleParam, pathwayParam]);

  return (
    <div className="w-full h-[calc(100vh-4rem)] md:h-screen flex flex-col bg-background">
      {/* ── SpacePoint LMS Header Bar ── */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-2.5 bg-card/90 border-b border-border text-sm shrink-0 backdrop-blur-sm z-10">
        <div className="flex items-center gap-3 min-w-0">
          {assignmentId ? (
            <Link
              to="/learn/checklists/$assignmentId"
              params={{ assignmentId }}
              className="inline-flex items-center gap-1.5 font-semibold text-primary hover:underline shrink-0"
            >
              <ArrowLeft className="size-4" /> Back to Program
            </Link>
          ) : (
            <Link
              to="/learn/home"
              className="inline-flex items-center gap-1.5 font-semibold text-primary hover:underline shrink-0"
            >
              <ArrowLeft className="size-4" /> Back to Home
            </Link>
          )}

          <div className="hidden sm:flex items-center gap-2 text-muted-foreground min-w-0">
            <span>/</span>
            <div className="flex items-center gap-2 font-medium text-foreground truncate">
              <span className="p-1 rounded-md bg-primary/10 text-primary">
                <Rocket className="size-4" />
              </span>
              <span className="font-semibold">RocketLab 3D</span>
            </div>
            <span className="text-xs text-muted-foreground hidden lg:inline">
              · Interactive Rocket Design &amp; 3D Flight Simulator
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-medium text-primary">
            <Sparkles className="size-3.5" />
            <span>Interactive Simulator</span>
          </div>

          {assignmentId && itemId && (
            <Button
              size="sm"
              variant="outline"
              disabled={completeMutation.isPending}
              onClick={() => completeMutation.mutate()}
              className="gap-1.5 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 hover:text-emerald-300"
            >
              <CheckCircle2 className="size-4 text-emerald-400" />
              <span>Mark Step Complete</span>
            </Button>
          )}
        </div>
      </div>

      {/* ── RocketLab Workspace ── */}
      <div className="flex-1 w-full min-h-0 bg-[#05030A] relative overflow-hidden">
        <iframe
          src={iframeSrc}
          title="SpacePoint RocketLab 3D"
          className="w-full h-full border-0 block"
          allow="fullscreen"
        />
      </div>
    </div>
  );
}
