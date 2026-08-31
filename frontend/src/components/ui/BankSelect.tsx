import { useState } from "react";

import { UAE_BANKS, bankLabel, findUaeBank } from "@/lib/uaeBanks";

export const BANK_OTHER = "__other__";

/**
 * Bank picker with an "Other (type it)" fallback, modelled on `CitySelect`.
 *
 * Picking a listed bank hands the parent the bank's SWIFT code too, so the
 * instructor doesn't retype a BIC (and can't typo one). `bank_name` is stored
 * as free text, so anything already saved that isn't on the list simply opens
 * in Other mode — no migration, no closed set.
 *
 * `otherMode` is an explicit flag rather than something inferred from `value`:
 * choosing Other starts with nothing typed, so `value === ""` can't tell
 * "typing a custom bank" apart from "nothing chosen yet" — the same trap
 * documented in CitySelect. Its initial value is read once at mount, which is
 * only correct because Payments.tsx waits for the bank query before rendering
 * the form; mounting against an unhydrated empty value would strand a saved
 * custom bank behind the dropdown.
 */
export function BankSelect({
  value,
  onChange,
  className,
  placeholder = "Select your bank...",
  required,
  disabled,
}: {
  value: string;
  /** Fires with the bank name, plus the SWIFT code when one is known. */
  onChange: (next: { bank_name: string; swift_bic?: string }) => void;
  className?: string;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
}) {
  const [otherMode, setOtherMode] = useState(() => !!value.trim() && !findUaeBank(value));

  if (otherMode) {
    return (
      <div className="flex flex-col gap-1.5">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange({ bank_name: e.target.value })}
          placeholder="Type your bank name..."
          required={required}
          disabled={disabled}
          className={className}
        />
        <button
          type="button"
          onClick={() => { setOtherMode(false); onChange({ bank_name: "" }); }}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors w-fit"
        >
          Pick from the list instead
        </button>
      </div>
    );
  }

  const selected = findUaeBank(value);

  return (
    <div className="flex flex-col gap-1.5">
      <select
        value={selected?.name ?? ""}
        onChange={(e) => {
          if (e.target.value === BANK_OTHER) {
            setOtherMode(true);
            onChange({ bank_name: "" });
            return;
          }
          const bank = findUaeBank(e.target.value);
          // Overwrite any SWIFT already typed — the bank's own code beats a
          // hand-entered one, and leaving a stale code next to a new bank is
          // worse than asking for it again.
          onChange({ bank_name: e.target.value, swift_bic: bank?.swift ?? "" });
        }}
        required={required}
        disabled={disabled}
        className={className}
      >
        <option value="" disabled>{placeholder}</option>
        {UAE_BANKS.map((b) => (
          <option key={b.swift} value={b.name}>{bankLabel(b)}</option>
        ))}
        <option value={BANK_OTHER}>Other (my bank isn&apos;t listed)</option>
      </select>
      {selected?.note && (
        <p className="text-xs text-amber-600 dark:text-amber-400">{selected.note}</p>
      )}
    </div>
  );
}
