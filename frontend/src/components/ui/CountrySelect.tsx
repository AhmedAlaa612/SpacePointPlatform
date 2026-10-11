import { getCountries } from "@/lib/countries";

const LEGACY_CODE_MAP: Record<string, string> = {
  uae: "AE",
  ae: "AE",
  ksa: "SA",
  sa: "SA",
  egypt: "EG",
  eg: "EG",
  oman: "OM",
  om: "OM",
  bahrain: "BH",
  bh: "BH",
  kuwait: "KW",
  kw: "KW",
  qatar: "QA",
  qa: "QA",
  jordan: "JO",
  jo: "JO",
};

export function resolveCountryCode(raw: string | null | undefined): string {
  if (!raw) return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const lower = trimmed.toLowerCase();
  if (LEGACY_CODE_MAP[lower]) return LEGACY_CODE_MAP[lower];
  const countries = getCountries();
  const match = countries.find(
    (c) => c.code.toLowerCase() === lower || c.name.toLowerCase() === lower,
  );
  return match ? match.code : trimmed.toUpperCase();
}

/** Shared country `<select>` (2026-08-08) — same options everywhere a
 * country is picked, sourced from `lib/countries.ts` instead of each place
 * hand-typing its own list. This codebase has two pre-existing storage
 * conventions for "country" and this component serves both without
 * changing either: `valueType="name"` (default) returns the display name —
 * matches `User.country`/`ApplicantProfile.country`'s existing free-text
 * storage. `valueType="code"` returns the ISO-3166 alpha-2 code — matches
 * `Location.country`/`City.country`.
 */
export function CountrySelect({
  value,
  onChange,
  className,
  placeholder = "Select country...",
  required,
  disabled,
  valueType = "name",
}: {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  valueType?: "name" | "code";
}) {
  const countries = getCountries();
  const code = resolveCountryCode(value);
  const resolvedValue =
    valueType === "code"
      ? code
      : countries.find((c) => c.code === code)?.name ?? value;

  return (
    <select
      value={resolvedValue}
      onChange={(e) => onChange(e.target.value)}
      required={required}
      disabled={disabled}
      className={className}
    >
      <option value="" disabled>{placeholder}</option>
      {countries.map((c) => (
        <option key={c.code} value={valueType === "code" ? c.code : c.name}>{c.name}</option>
      ))}
    </select>
  );
}

