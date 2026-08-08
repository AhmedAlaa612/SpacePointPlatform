"""ISO-3166-1 alpha-2 country codes + English display names — the backend
mirror of `frontend/src/lib/countries.ts`. Names are generated once from
Node's `Intl.DisplayNames(["en"], {type: "region"})` — the exact engine the
frontend's `CountrySelect` uses — so this list matches what a user actually
saw and picked in the dropdown, not a separately-sourced list (e.g.
`pycountry`) that could drift from it on contested/renamed names.

Codes are the stable identity (2026-08-08 country-code migration): a
display name is a computed, locale-dependent label — this file hardcodes
`en` today, but nothing prevents that from becoming locale-aware later, at
which point a *stored* name would silently stop matching a freshly
rendered one. A stored code has no such exposure. `Location.country`/
`City.country` were already built this way; `users.country`/
`applicant_profiles.country`/`applications.country` are migrated onto the
same convention by `alembic/versions/<see resolve_country_code callers>`.
"""

COUNTRY_NAMES: dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan", "AG": "Antigua & Barbuda",
    "AI": "Anguilla", "AL": "Albania", "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica",
    "AR": "Argentina", "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba",
    "AX": "Åland Islands", "AZ": "Azerbaijan", "BA": "Bosnia & Herzegovina", "BB": "Barbados",
    "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria", "BH": "Bahrain",
    "BI": "Burundi", "BJ": "Benin", "BL": "St. Barthélemy", "BM": "Bermuda", "BN": "Brunei",
    "BO": "Bolivia", "BQ": "Caribbean Netherlands", "BR": "Brazil", "BS": "Bahamas", "BT": "Bhutan",
    "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus", "BZ": "Belize", "CA": "Canada",
    "CC": "Cocos (Keeling) Islands", "CD": "Congo - Kinshasa", "CF": "Central African Republic",
    "CG": "Congo - Brazzaville", "CH": "Switzerland", "CI": "Côte d’Ivoire", "CK": "Cook Islands",
    "CL": "Chile", "CM": "Cameroon", "CN": "China", "CO": "Colombia", "CR": "Costa Rica",
    "CU": "Cuba", "CV": "Cape Verde", "CW": "Curaçao", "CX": "Christmas Island", "CY": "Cyprus",
    "CZ": "Czechia", "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica",
    "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt",
    "EH": "Western Sahara", "ER": "Eritrea", "ES": "Spain", "ET": "Ethiopia", "FI": "Finland",
    "FJ": "Fiji", "FK": "Falkland Islands", "FM": "Micronesia", "FO": "Faroe Islands", "FR": "France",
    "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada", "GE": "Georgia", "GF": "French Guiana",
    "GG": "Guernsey", "GH": "Ghana", "GI": "Gibraltar", "GL": "Greenland", "GM": "Gambia",
    "GN": "Guinea", "GP": "Guadeloupe", "GQ": "Equatorial Guinea", "GR": "Greece",
    "GS": "South Georgia & South Sandwich Islands", "GT": "Guatemala", "GU": "Guam",
    "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong SAR China",
    "HM": "Heard & McDonald Islands", "HN": "Honduras", "HR": "Croatia", "HT": "Haiti",
    "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IM": "Isle of Man",
    "IN": "India", "IO": "British Indian Ocean Territory", "IQ": "Iraq", "IR": "Iran",
    "IS": "Iceland", "IT": "Italy", "JE": "Jersey", "JM": "Jamaica", "JO": "Jordan", "JP": "Japan",
    "KE": "Kenya", "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati", "KM": "Comoros",
    "KN": "St. Kitts & Nevis", "KP": "North Korea", "KR": "South Korea", "KW": "Kuwait",
    "KY": "Cayman Islands", "KZ": "Kazakhstan", "LA": "Laos", "LB": "Lebanon", "LC": "St. Lucia",
    "LI": "Liechtenstein", "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco", "MC": "Monaco",
    "MD": "Moldova", "ME": "Montenegro", "MF": "St. Martin", "MG": "Madagascar",
    "MH": "Marshall Islands", "MK": "North Macedonia", "ML": "Mali", "MM": "Myanmar (Burma)",
    "MN": "Mongolia", "MO": "Macao SAR China", "MP": "Northern Mariana Islands", "MQ": "Martinique",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius", "MV": "Maldives",
    "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique", "NA": "Namibia",
    "NC": "New Caledonia", "NE": "Niger", "NF": "Norfolk Island", "NG": "Nigeria",
    "NI": "Nicaragua", "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NR": "Nauru",
    "NU": "Niue", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French Polynesia", "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan",
    "PL": "Poland", "PM": "St. Pierre & Miquelon", "PN": "Pitcairn Islands", "PR": "Puerto Rico",
    "PS": "Palestinian Territories", "PT": "Portugal", "PW": "Palau", "PY": "Paraguay",
    "QA": "Qatar", "RE": "Réunion", "RO": "Romania", "RS": "Serbia", "RU": "Russia", "RW": "Rwanda",
    "SA": "Saudi Arabia", "SB": "Solomon Islands", "SC": "Seychelles", "SD": "Sudan",
    "SE": "Sweden", "SG": "Singapore", "SH": "St. Helena", "SI": "Slovenia",
    "SJ": "Svalbard & Jan Mayen", "SK": "Slovakia", "SL": "Sierra Leone", "SM": "San Marino",
    "SN": "Senegal", "SO": "Somalia", "SR": "Suriname", "SS": "South Sudan",
    "ST": "São Tomé & Príncipe", "SV": "El Salvador", "SX": "Sint Maarten", "SY": "Syria",
    "SZ": "Eswatini", "TC": "Turks & Caicos Islands", "TD": "Chad",
    "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan",
    "TK": "Tokelau", "TL": "Timor-Leste", "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga",
    "TR": "Türkiye", "TT": "Trinidad & Tobago", "TV": "Tuvalu", "TW": "Taiwan", "TZ": "Tanzania",
    "UA": "Ukraine", "UG": "Uganda", "UM": "U.S. Outlying Islands", "US": "United States",
    "UY": "Uruguay", "UZ": "Uzbekistan", "VA": "Vatican City", "VC": "St. Vincent & Grenadines",
    "VE": "Venezuela", "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands", "VN": "Vietnam",
    "VU": "Vanuatu", "WF": "Wallis & Futuna", "WS": "Samoa", "YE": "Yemen", "YT": "Mayotte",
    "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}

# Real free-text variants seen in production data that don't match the
# canonical `Intl.DisplayNames` output exactly — extend as new ones turn up.
_ALIASES: dict[str, str] = {
    "uae": "AE",
}

_NAME_TO_CODE: dict[str, str] = {name.lower(): code for code, name in COUNTRY_NAMES.items()}


def resolve_country_code(value: str | None) -> str | None:
    """Case/whitespace-insensitive match of a free-text country name (or an
    already-valid code) to its ISO-3166-1 alpha-2 code. Returns `None` for
    blank input or anything unrecognized — callers leave an unresolved value
    as-is rather than guessing or destroying it (same discipline as the
    `locations` → `city_id` backfill: better to render unselected than to
    silently invent or delete real data)."""
    if not value:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if trimmed.upper() in COUNTRY_NAMES:
        return trimmed.upper()
    lowered = trimmed.lower()
    if lowered in _ALIASES:
        return _ALIASES[lowered]
    return _NAME_TO_CODE.get(lowered)
