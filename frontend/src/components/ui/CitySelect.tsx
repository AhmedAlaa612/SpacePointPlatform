import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchPublicCities } from "@/api/lms";
import { getCountries } from "@/lib/countries";

export const CITY_OTHER = "__other__";

/**
 * Countries for city gating (2026-08-08) — the country is stored as an
 * ISO-3166 code ("AE") on some forms and a display name ("United Arab
 * Emirates") on others; both resolve to the same code here.
 */
export function useCountryCode(country: string): string {
  return useMemo(() => {
    const match = getCountries().find((c) => c.code === country || c.name === country);
    return match ? match.code : country;
  }, [country]);
}

/** Cities of one country — the "does this country have cities at all"
 *  question pages ask before rendering the picker. */
export function useCitiesForCountry(country: string) {
  const { data: cities = [] } = useQuery({ queryKey: ["public-cities"], queryFn: fetchPublicCities });
  const countryCode = useCountryCode(country);
  return useMemo(
    () => cities.filter((c) => c.country === countryCode),
    [cities, countryCode],
  );
}

/**
 * Shared city `<select>` gated by country, with an "Other (type it)"
 * fallback (2026-08-08) — lists only the cities of the selected country,
 * plus an "Other" option that reveals a free-text input for countries with
 * no SpacePoint city. Selecting a real city clears `otherValue`; typing
 * Other clears the city id. The picker only renders once a country is
 * chosen; the text value lives on the parent (stored per surface).
 */
export function CitySelect({
  country,
  value,
  onChange,
  otherValue,
  onOtherChange,
  className,
  placeholder = "Select city...",
  required,
}: {
  country: string;
  value: string;
  onChange: (value: string) => void;
  otherValue?: string;
  onOtherChange?: (value: string) => void;
  className?: string;
  placeholder?: string;
  required?: boolean;
}) {
  const options = useCitiesForCountry(country);
  // Cities load from a query with default `data: cities = []` — without
  // `isPending`, the auto-clear effect below can't tell "still loading"
  // apart from "loaded, but this city isn't in this country," and wipes a
  // real saved value out from under the query on first mount.
  const { isPending } = useQuery({ queryKey: ["public-cities"], queryFn: fetchPublicCities });

  const otherField = !!onOtherChange;
  const showingOther = otherField && !value && otherValue !== undefined && otherValue !== "";

  useEffect(() => {
    if (isPending) return;
    if (value && !options.some((c) => c.id === value)) onChange("");
  }, [value, options, onChange, isPending]);

  if (!country) return null;

  if (showingOther) {
    return (
      <input
        type="text"
        value={otherValue ?? ""}
        onChange={(e) => onOtherChange!(e.target.value)}
        placeholder="Type your city..."
        required={required}
        className={className}
      />
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => {
        if (e.target.value === CITY_OTHER) {
          onChange("");
        } else {
          onChange(e.target.value);
          onOtherChange?.("");
        }
      }}
      required={required}
      className={className}
    >
      <option value="" disabled>{placeholder}</option>
      {options.map((c) => (
        <option key={c.id} value={c.id}>{c.name}</option>
      ))}
      {otherField && (
        <option value={CITY_OTHER}>Other (type it)</option>
      )}
    </select>
  );
}