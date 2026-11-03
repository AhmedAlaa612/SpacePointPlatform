import { useState, useMemo } from "react";
import { CheckCircle2, AlertCircle, Play, Unlock, HelpCircle, Code2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ContentPractice } from "@/api/lms";
import { MarkdownContent } from "@/components/lms/MarkdownContent";

interface CodePracticeBlockProps {
  content: ContentPractice;
  onComplete: () => void;
  isCompleted?: boolean;
}

export function CodePracticeBlock({ content, onComplete, isCompleted = false }: CodePracticeBlockProps) {
  const maxAttempts = content.max_attempts || 3;
  const [selectedAddress, setSelectedAddress] = useState<string>(
    content.hardware_selector?.default_address || content.hardware_selector?.addresses?.[0] || ""
  );

  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [attempts, setAttempts] = useState<number>(0);
  const [validation, setValidation] = useState<Record<string, boolean>>({});
  const [hasChecked, setHasChecked] = useState<boolean>(false);
  const [solved, setSolved] = useState<boolean>(isCompleted);

  const isUnlocked = attempts >= maxAttempts && !solved;

  const normalizeToken = (t: string) => t.replace(/[\s{}]/g, "").toUpperCase();

  // Split template by {{TOKEN}} placeholders (case-insensitive, allows whitespace, underscores, hyphens)
  const templateParts = useMemo(() => {
    const raw = content.template || "";
    const regex = /(\{\{\s*[\w-]+\s*\}\})/gi;
    return raw.split(regex);
  }, [content.template]);

  const blanksMap = useMemo(() => {
    const map = new Map<string, typeof content.blanks[0]>();
    (content.blanks || []).forEach((b) => {
      map.set(b.token, b);
      map.set(b.token.trim(), b);
      map.set(normalizeToken(b.token), b);
    });
    return map;
  }, [content.blanks]);

  const handleInputChange = (token: string, val: string) => {
    setInputs((prev) => ({ ...prev, [token]: val }));
    // reset single validation on change
    if (validation[token] !== undefined) {
      setValidation((prev) => ({ ...prev, [token]: true }));
    }
  };

  const verifyAnswers = () => {
    const newAttempts = attempts + 1;
    setAttempts(newAttempts);
    setHasChecked(true);

    let allValid = true;
    const newValidation: Record<string, boolean> = {};

    for (const blank of content.blanks || []) {
      const userVal = (inputs[blank.token] ?? inputs[blank.token.trim()] ?? inputs[normalizeToken(blank.token)] ?? "").trim();
      let pattern = blank.validator_pattern || "";

      // Allow placeholder replacement for dynamic addresses if needed
      if (pattern.includes("{{ADDRESS}}") && selectedAddress) {
        pattern = pattern.replaceAll("{{ADDRESS}}", selectedAddress);
      }

      let isValid = false;
      if (!pattern) {
        isValid = userVal.length > 0;
      } else {
        try {
          const rx = new RegExp(pattern, "i");
          isValid = rx.test(userVal);
        } catch {
          isValid = userVal.toLowerCase() === pattern.toLowerCase();
        }
      }

      newValidation[blank.token] = isValid;
      if (!isValid) allValid = false;
    }

    setValidation(newValidation);

    if (allValid) {
      setSolved(true);
    } else if (newAttempts >= maxAttempts) {
      // Auto-fill answers on max attempts
      const autoFilled: Record<string, string> = { ...inputs };
      for (const blank of content.blanks || []) {
        if (blank.correct_answer) {
          let ans = blank.correct_answer;
          if (ans.includes("{{ADDRESS}}") && selectedAddress) {
            ans = ans.replaceAll("{{ADDRESS}}", selectedAddress);
          }
          autoFilled[blank.token] = ans;
        }
      }
      setInputs(autoFilled);
    }
  };

  const handleReset = () => {
    setInputs({});
    setValidation({});
    setHasChecked(false);
    setAttempts(0);
    setSolved(false);
  };

  return (
    <Card className="p-6 flex flex-col gap-6 bg-card border border-border rounded-2xl shadow-sm">
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div className="flex items-center gap-2">
          <Code2 className="size-5 text-primary" />
          <h3 className="font-semibold text-lg">Interactive Code Practice</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs px-2.5 py-1 rounded-full bg-muted text-muted-foreground font-mono">
            Attempts: {attempts} / {maxAttempts}
          </span>
          {attempts > 0 && !solved && (
            <button
              onClick={handleReset}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              <RotateCcw className="size-3" /> Reset
            </button>
          )}
        </div>
      </div>

      {(content.markdown || content.instructions) && (
        <div className="p-4 sm:p-5 bg-muted/30 rounded-xl border border-border/60 overflow-hidden">
          <MarkdownContent content={content.markdown || content.instructions || ""} />
        </div>
      )}

      {/* Optional Hardware Address Selector */}
      {content.hardware_selector?.enabled && (content.hardware_selector.addresses || []).length > 0 && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 p-3.5 bg-primary/5 border border-primary/20 rounded-xl">
          <label className="text-xs font-semibold uppercase tracking-wider text-primary">
            Target I²C Address:
          </label>
          <select
            value={selectedAddress}
            onChange={(e) => setSelectedAddress(e.target.value)}
            disabled={solved}
            className="h-9 px-3 bg-card border border-border rounded-lg text-sm text-foreground font-mono focus:outline-none focus:border-primary"
          >
            {content.hardware_selector.addresses.map((addr) => (
              <option key={addr} value={addr}>
                {addr}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted-foreground">
            (Select sensor wiring address configuration)
          </span>
        </div>
      )}

      {/* Monospace Code Display with Embedded Blanks */}
      <div className="relative rounded-xl overflow-hidden border border-border bg-[#18181b] text-gray-100 p-4 font-mono text-sm leading-relaxed overflow-x-auto shadow-inner">
        <pre className="whitespace-pre font-mono leading-8">
          {templateParts.map((part, idx) => {
            const blank = blanksMap.get(part) || blanksMap.get(part.trim()) || blanksMap.get(normalizeToken(part));
            if (!blank) {
              return <span key={idx}>{part}</span>;
            }

            const tokenKey = blank.token;
            const isCorrect = validation[tokenKey] ?? validation[part];
            const hasError = hasChecked && isCorrect === false;
            const currentVal = inputs[tokenKey] ?? inputs[part] ?? "";
            const placeholderText = blank.label || "...";
            const displayText = currentVal || placeholderText;

            return (
              <span
                key={idx}
                className="inline-grid [grid-template-columns:1fr] items-center mx-1 my-0.5 align-middle"
              >
                {/* Sizer: invisible text that automatically sizes the grid column to fit without clipping */}
                <span
                  aria-hidden="true"
                  className="invisible whitespace-pre px-2.5 py-1 text-xs sm:text-sm font-mono col-start-1 row-start-1 pointer-events-none select-none min-w-[3.75rem]"
                >
                  {displayText}&nbsp;
                </span>
                <input
                  type="text"
                  value={currentVal}
                  onChange={(e) => handleInputChange(tokenKey, e.target.value)}
                  placeholder={placeholderText}
                  disabled={solved || isUnlocked}
                  className={`col-start-1 row-start-1 w-full px-2.5 py-1 text-xs sm:text-sm font-mono rounded-md border transition-all outline-none text-center ${
                    isCorrect
                      ? "bg-emerald-950/50 border-emerald-500 text-emerald-300 font-bold shadow-[0_0_8px_rgba(16,185,129,0.3)]"
                      : hasError
                      ? "bg-red-950/50 border-red-500 text-red-300 shadow-[0_0_8px_rgba(239,68,68,0.3)]"
                      : isUnlocked
                      ? "bg-amber-950/50 border-amber-500 text-amber-300 font-bold shadow-[0_0_8px_rgba(245,158,11,0.3)]"
                      : "bg-black/70 border-zinc-700 text-purple-300 placeholder:text-zinc-500 focus:border-purple-400 focus:ring-1 focus:ring-purple-400"
                  }`}
                />
              </span>
            );
          })}
        </pre>
      </div>

      {/* Hints & Feedback */}
      {hasChecked && !solved && !isUnlocked && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm">
          <AlertCircle className="size-5 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold">Some blanks are incorrect or incomplete.</p>
            <div className="mt-2 space-y-1 text-xs">
              {(content.blanks || []).map((blank) => {
                if (validation[blank.token] === false && blank.hint) {
                  return (
                    <p key={blank.token} className="flex items-center gap-1.5 opacity-90">
                      <HelpCircle className="size-3.5 shrink-0 text-amber-500" />
                      <span>
                        <strong>{blank.label || blank.token}:</strong> {blank.hint}
                      </span>
                    </p>
                  );
                }
                return null;
              })}
            </div>
          </div>
        </div>
      )}

      {isUnlocked && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-600 dark:text-amber-400 text-sm">
          <Unlock className="size-5 shrink-0 mt-0.5 text-amber-500" />
          <div>
            <p className="font-semibold">Maximum attempts reached — Solution Unlocked</p>
            <p className="text-xs opacity-90 mt-1">
              The correct code answers have been populated for your review. Read through the implementation to understand how the parameters align, then complete the step.
            </p>
          </div>
        </div>
      )}

      {solved && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 text-sm">
          <CheckCircle2 className="size-5 shrink-0 text-emerald-500" />
          <div>
            <p className="font-semibold">Verification Passed!</p>
            <p className="text-xs opacity-90">All code syntax and logic parameters match the mission requirements.</p>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between pt-2">
        {!solved && !isUnlocked ? (
          <Button onClick={verifyAnswers} className="flex items-center gap-2">
            <Play className="size-4" /> Run & Verify Code
          </Button>
        ) : (
          <Button
            onClick={onComplete}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold ml-auto"
          >
            <CheckCircle2 className="size-4" /> Complete & Continue
          </Button>
        )}
      </div>
    </Card>
  );
}
