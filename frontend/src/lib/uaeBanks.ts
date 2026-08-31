/**
 * Common UAE banks, for the instructor bank-details picker.
 *
 * Every SWIFT code here was verified against the bank's own site or a BIC
 * registry rather than retyped from a spreadsheet — a wrong code misroutes a
 * payout, and two codes in the shortlist this list came from were wrong
 * (NBQ read UHMQAEAD, and Mbank's needs the digit zero).
 *
 * Codes are the 8-character head-office BIC, which is what a payment letter
 * should print; a sending bank that demands 11 characters appends "XXX".
 *
 * This is a convenience list, not a closed set — `bank_name` stays a free-text
 * column, and BankSelect's "Other" option covers anyone banking elsewhere. So
 * adding a bank here is a one-line edit with nothing else to migrate.
 */
export interface UaeBank {
  /** Legal name — what gets stored in bank_name and printed on the letter. */
  name: string
  /** What people actually call it, and what they'll scan the dropdown for. */
  commonName: string
  /** 8-character head-office BIC. */
  swift: string
  emirate: string
  /** Shown under the picker when this bank is chosen. */
  note?: string
}

/** Sorted by commonName — people look for their bank by the name they use. */
export const UAE_BANKS: UaeBank[] = [
  { commonName: "ADCB", name: "Abu Dhabi Commercial Bank PJSC", swift: "ADCBAEAA", emirate: "Abu Dhabi" },
  { commonName: "ADIB", name: "Abu Dhabi Islamic Bank PJSC", swift: "ABDIAEAD", emirate: "Abu Dhabi" },
  { commonName: "Ajman Bank", name: "Ajman Bank PJSC", swift: "AJMNAEAJ", emirate: "Ajman" },
  { commonName: "Al Hilal Bank", name: "Al Hilal Bank PJSC", swift: "HLALAEAA", emirate: "Abu Dhabi" },
  { commonName: "Bank of Sharjah", name: "Bank of Sharjah PJSC", swift: "SHARAEAS", emirate: "Sharjah" },
  { commonName: "CBD", name: "Commercial Bank of Dubai PSC", swift: "CBDUAEAD", emirate: "Dubai" },
  { commonName: "CBI", name: "Commercial Bank International PJSC", swift: "CLBIAEAD", emirate: "Dubai" },
  { commonName: "DIB", name: "Dubai Islamic Bank PJSC", swift: "DUIBAEAD", emirate: "Dubai" },
  { commonName: "Emirates Islamic", name: "Emirates Islamic Bank PJSC", swift: "MEBLAEAD", emirate: "Dubai" },
  { commonName: "Emirates NBD", name: "Emirates NBD Bank PJSC", swift: "EBILAEAD", emirate: "Dubai" },
  { commonName: "FAB", name: "First Abu Dhabi Bank PJSC", swift: "NBADAEAA", emirate: "Abu Dhabi" },
  { commonName: "Mashreq", name: "Mashreqbank PSC", swift: "BOMLAEAD", emirate: "Dubai" },
  {
    commonName: "Mbank",
    name: "Al Maryah Community Bank LLC",
    swift: "E097AEXX",
    emirate: "Abu Dhabi",
    // Not a real ISO 9362 BIC — Al Maryah issues this for local AED transfers
    // and does not accept inbound international SWIFT.
    note: "Local AED transfers only — Mbank does not accept international SWIFT transfers.",
  },
  { commonName: "NBF", name: "National Bank of Fujairah PJSC", swift: "NBFUAEAF", emirate: "Fujairah" },
  { commonName: "NBQ", name: "National Bank of Umm Al Qaiwain PSC", swift: "UMMQAEAD", emirate: "Umm Al Quwain" },
  { commonName: "RAKBANK", name: "National Bank of Ras Al Khaimah PJSC", swift: "NRAKAEAK", emirate: "Ras Al Khaimah" },
  { commonName: "SIB", name: "Sharjah Islamic Bank PJSC", swift: "NBSHAEAS", emirate: "Sharjah" },
  { commonName: "Standard Chartered", name: "Standard Chartered Bank UAE", swift: "SCBLAEAD", emirate: "Dubai" },
  { commonName: "UAB", name: "United Arab Bank PJSC", swift: "UARBAEAA", emirate: "Sharjah" },
  { commonName: "Wio", name: "Wio Bank PJSC", swift: "WIOBAEAD", emirate: "Abu Dhabi" },
]

/** Matched on the stored legal name — that's what the select's value is. */
export function findUaeBank(name: string): UaeBank | undefined {
  const q = name.trim().toLowerCase()
  return q ? UAE_BANKS.find((b) => b.name.toLowerCase() === q) : undefined
}

/** "ADCB — Abu Dhabi Commercial Bank PJSC", collapsed where that would stutter. */
export function bankLabel(bank: UaeBank): string {
  return bank.name.toLowerCase().startsWith(bank.commonName.toLowerCase())
    ? bank.name
    : `${bank.commonName} — ${bank.name}`
}
