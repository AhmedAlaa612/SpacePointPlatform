import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class names, resolving conflicts. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** A pasted-back link ("test.com", "www.test.com") has no scheme, so a
 * plain `href` treats it as a path relative to the current page instead
 * of an external site (e.g. `/judge/teams/test.com`). Submission/external
 * links are free text typed by students and judges, never validated as
 * full URLs — this is the one place that decides what "open it" means,
 * rather than every `<a href>` site guessing differently. */
export function ensureAbsoluteUrl(url: string): string {
  return /^[a-z][a-z0-9+.-]*:/i.test(url) ? url : `https://${url}`;
}

/** Locale-friendly date formatting. */
export function formatDate(value: string | Date, opts?: Intl.DateTimeFormatOptions) {
  const d = typeof value === "string" ? new Date(value) : value;
  return d.toLocaleDateString(undefined, opts ?? { year: "numeric", month: "short", day: "numeric" });
}

/**
 * Safely extracts a human-readable error message string from any API error response or Exception.
 * Guarantees a string return value so React never crashes with "Objects are not valid as a React child".
 */
export function getErrorMessage(err: any, fallbackMessage: string = "An error occurred"): string {
  if (!err) return fallbackMessage;

  const detail = err?.response?.data?.detail ?? err?.data?.detail ?? err?.detail ?? err?.message;

  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  const formatSingleDetail = (d: any): string => {
    if (!d) return "";
    if (typeof d === "string") return d;
    if (typeof d === "object") {
      const field = Array.isArray(d.loc)
        ? d.loc.filter((item: any) => item !== "body" && item !== "query" && item !== "path").join(".")
        : "";
      const msg = d.msg || d.detail || d.message;
      if (msg && typeof msg === "string") {
        return field ? `${field}: ${msg}` : msg;
      }
      try {
        return JSON.stringify(d);
      } catch {
        return String(d);
      }
    }
    return String(d);
  };

  if (Array.isArray(detail)) {
    const formatted = detail.map(formatSingleDetail).filter(Boolean);
    if (formatted.length > 0) {
      return formatted.join("; ");
    }
  }

  if (typeof detail === "object") {
    const formatted = formatSingleDetail(detail);
    if (formatted) return formatted;
  }

  if (typeof err === "string" && err.trim()) {
    return err.trim();
  }

  return fallbackMessage;
}

