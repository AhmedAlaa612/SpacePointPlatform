import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { Ticket } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { fetchMe } from "@/api/auth";
import { redeemInviteCodeApi, type RedeemInviteResult } from "@/api/lms";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface RedeemInviteModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (result: RedeemInviteResult) => void;
  navigateOnSuccess?: boolean;
}

export function RedeemInviteModal({
  open,
  onOpenChange,
  onSuccess,
  navigateOnSuccess = true,
}: RedeemInviteModalProps) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setCurrentUser } = useAuth();

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      setCode("");
      setError(null);
    }
    onOpenChange(newOpen);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim().toUpperCase();
    if (!trimmed) {
      setError("Please enter an invite code.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await redeemInviteCodeApi(trimmed);

      // Invalidate relevant queries
      await queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
      await queryClient.invalidateQueries({ queryKey: ["lms-my-courses"] });
      await queryClient.invalidateQueries({ queryKey: ["me"] });

      // Refresh current user in auth context for observer role conversion
      const updatedUser = await fetchMe();
      setCurrentUser(updatedUser);

      handleOpenChange(false);
      onSuccess?.(res);

      if (navigateOnSuccess && res.redirect_to) {
        void navigate({ to: res.redirect_to as never });
      }
    } catch (err) {
      if (isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Invalid or expired invite code.");
      } else {
        setError("Something went wrong. Please check the code and try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={(e) => void handleSubmit(e)}>
          <DialogHeader>
            <div className="flex items-center gap-2 mb-1">
              <div className="p-2 rounded-xl bg-primary/10 text-primary">
                <Ticket className="size-4" />
              </div>
              <DialogTitle className="text-base font-bold">Redeem invite code</DialogTitle>
            </div>
            <DialogDescription className="text-xs text-muted-foreground">
              Enter an invite code provided by your school, instructor, or administrator to unlock programs and courses.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3 py-4">
            {error && (
              <div className="p-3 rounded-xl bg-destructive/10 text-destructive text-xs font-medium">
                {error}
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                Invite Code
              </label>
              <input
                type="text"
                autoFocus
                placeholder="e.g. FALL26"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow font-mono tracking-wider font-semibold uppercase"
              />
            </div>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="ghost"
              onClick={() => handleOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading || !code.trim()}>
              {loading ? "Redeeming..." : "Redeem code"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
