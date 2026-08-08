/** Country list (2026-08-08, fixed 2026-08-08) — display *names* are never
 * hand-typed: they come live from `Intl.DisplayNames`, which is why this
 * codebase used to have per-page ~200-line hardcoded name arrays that drift
 * out of sync with each other. The *codes* below are the ISO-3166-1 alpha-2
 * standard itself — a fixed reference table (a code is retired/added on the
 * order of once every few years, as a real geopolitical event, not routine
 * maintenance), not a list anyone types display names into.
 *
 * `Intl.supportedValuesOf("region")` looks like it should replace even this
 * static list, but it doesn't exist — "region" isn't a valid key per
 * ECMA-402 (valid keys: calendar, collation, currency, numberingSystem,
 * timeZone, unit); every engine throws `RangeError: Invalid key` on it, not
 * just older ones. Found live via the apply-instructor page 2026-08-08.
 */

const ISO_3166_1_ALPHA2 = [
  "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT", "AU", "AW", "AX", "AZ",
  "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY", "BZ",
  "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN", "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ",
  "DE", "DJ", "DK", "DM", "DO", "DZ",
  "EC", "EE", "EG", "EH", "ER", "ES", "ET",
  "FI", "FJ", "FK", "FM", "FO", "FR",
  "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY",
  "HK", "HM", "HN", "HR", "HT", "HU",
  "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR", "IS", "IT",
  "JE", "JM", "JO", "JP",
  "KE", "KG", "KH", "KI", "KM", "KN", "KP", "KR", "KW", "KY", "KZ",
  "LA", "LB", "LC", "LI", "LK", "LR", "LS", "LT", "LU", "LV", "LY",
  "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK", "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ",
  "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP", "NR", "NU", "NZ",
  "OM",
  "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM", "PN", "PR", "PS", "PT", "PW", "PY",
  "QA",
  "RE", "RO", "RS", "RU", "RW",
  "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ",
  "TC", "TD", "TF", "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW", "TZ",
  "UA", "UG", "UM", "US", "UY", "UZ",
  "VA", "VC", "VE", "VG", "VI", "VN", "VU",
  "WF", "WS",
  "YE", "YT",
  "ZA", "ZM", "ZW",
];

export interface CountryOption {
  code: string; // ISO-3166 alpha-2, e.g. "AE"
  name: string; // display name, e.g. "United Arab Emirates"
}

let cached: CountryOption[] | null = null;

export function getCountries(): CountryOption[] {
  if (cached) return cached;

  const displayNames = new Intl.DisplayNames(["en"], { type: "region" });

  const options = ISO_3166_1_ALPHA2
    .map((code) => ({ code, name: displayNames.of(code) ?? code }))
    .sort((a, b) => (
      // Home markets pinned first (AE, EG), everything else alphabetical.
      (a.code === "AE" ? 0 : a.code === "EG" ? 1 : 2)
      - (b.code === "AE" ? 0 : b.code === "EG" ? 1 : 2)
    ) || a.name.localeCompare(b.name));

  cached = options;
  return options;
}
