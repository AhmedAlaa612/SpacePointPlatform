import { useEffect, useRef, useState } from "react";
import { Link, useSearch } from "@tanstack/react-router";
import { isAxiosError } from "axios";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { fulfillCheckoutSession, type CheckoutFulfillResult } from "@/api/lms";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

const RETRY_DELAYS_MS = [2000, 3000, 5000]; // a delayed payment method settling — rare

/** `/learn/checkout/success` — the Stripe Checkout redirect target. Never
 * trusts the redirect alone as proof of payment (Stage S): it calls the
 * same server-side `fulfill()` the webhook uses, which is usually a fast,
 * idempotent no-op confirming what the webhook has already established. */
export default function LearnCheckoutSuccess() {
  const search = useSearch({ strict: false }) as { session_id?: string };
  const sessionId = search.session_id;
  const [result, setResult] = useState<CheckoutFulfillResult | null>(null);
  const [error, setError] = useState("");
  const attemptRef = useRef(0);

  useEffect(() => {
    if (!sessionId) {
      setError("Missing checkout session — if you just paid, check your email for a receipt and try My Courses.");
      return;
    }

    let cancelled = false;

    const attempt = async () => {
      try {
        const r = await fulfillCheckoutSession(sessionId);
        if (cancelled) return;
        setResult(r);
        if (r.status === "pending" && attemptRef.current < RETRY_DELAYS_MS.length) {
          const delay = RETRY_DELAYS_MS[attemptRef.current];
          attemptRef.current += 1;
          setTimeout(() => void attempt(), delay);
        }
      } catch (err) {
        if (!cancelled) setError(errorDetail(err, "Couldn't confirm your payment. Please try again."));
      }
    };

    void attempt();
    return () => { cancelled = true; };
  }, [sessionId]);

  return (
    <div className="mx-auto max-w-[560px] px-5 py-16">
      <Card className="p-8 flex flex-col items-center gap-4 text-center">
        {error ? (
          <>
            <XCircle className="size-10 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
            <Link to="/learn/my-courses"><Button variant="outline">Go to My Courses</Button></Link>
          </>
        ) : !result || result.status === "pending" ? (
          <>
            <Loader2 className="size-10 text-primary animate-spin" />
            <p className="text-sm text-muted-foreground">Confirming your payment...</p>
          </>
        ) : result.status === "paid" ? (
          <>
            <CheckCircle2 className="size-10 text-emerald-500" />
            <p className="text-sm font-medium">You're in! Your course is ready.</p>
            <Link to="/learn/courses/$courseId" params={{ courseId: result.course_id }}>
              <Button>Start learning</Button>
            </Link>
          </>
        ) : (
          <>
            <XCircle className="size-10 text-destructive" />
            <p className="text-sm text-destructive">
              {result.status === "failed"
                ? "This payment didn't go through — nothing was charged."
                : "This purchase isn't active right now."}
            </p>
            <Link to="/learn/courses/$courseId" params={{ courseId: result.course_id }}>
              <Button variant="outline">Back to the course</Button>
            </Link>
          </>
        )}
      </Card>
    </div>
  );
}
