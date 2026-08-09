import { useEffect, useMemo, useRef, useState } from "react";
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
  // Explicit mode flag — can't infer "should show the text field" purely
  // from `otherValue !== ""`, since picking "Other" starts with nothing
  // typed yet either; that made the dropdown just re-render itself instead
  // of switching to the text input. Starts true when editing a profile that
  // already has a saved custom city.
  const [otherMode, setOtherMode] = useState(!!otherValue);

  useEffect(() => {
    if (isPending) return;
    if (value && !options.some((c) => c.id === value)) onChange("");
  }, [value, options, onChange, isPending]);

  // A different country invalidates whatever custom city was typed for the
  // old one — back to the dropdown, not a stale free-text value. Skips the
  // first run: on mount this would otherwise immediately wipe a saved
  // custom city before the user ever touched the country field.
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return; }
    setOtherMode(false);
    onOtherChange?.("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [country]);

  if (!country) return null;

  if (otherField && otherMode) {
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
          setOtherMode(true);
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