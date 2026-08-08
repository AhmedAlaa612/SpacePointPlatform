import { getCountries } from "@/lib/countries";

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
  return (
    <select
      value={value}
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
