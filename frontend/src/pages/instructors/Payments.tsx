import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Banknote, Calendar, Download, MapPin } from "lucide-react"
import {
  getBankDetailsApi, updateBankDetailsApi,
} from "@/api/instructors/instructor"
import { getPaymentSummaryApi, listPaymentLettersApi, signPaymentLetterApi } from "@/api/instructors/payments"
import type { PaymentLetter } from "@/types/instructors"
import { BankSelect } from "@/components/ui/BankSelect"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner, StatCard, StatusPill } from "@/pages/instructors/components/common"
import { SignaturePad } from "@/pages/instructors/components/SignaturePad"

export default function Payments() {
  const qc = useQueryClient()
  const [signingLetter, setSigningLetter] = useState<PaymentLetter | null>(null)
  const [bank, setBank] = useState({ account_holder_name: "", bank_name: "", iban: "", swift_bic: "" })
  const [bankLoaded, setBankLoaded] = useState(false)

  const summary = useQuery({ queryKey: ["instructor-payment-summary"], queryFn: getPaymentSummaryApi })
  const letters = useQuery({ queryKey: ["instructor-payment-letters"], queryFn: listPaymentLettersApi })
  const bankDetails = useQuery({ queryKey: ["instructor-bank-details"], queryFn: getBankDetailsApi })

  if (bankDetails.data && !bankLoaded) {
    setBank({
      account_holder_name: bankDetails.data.account_holder_name ?? "",
      bank_name: bankDetails.data.bank_name ?? "",
      iban: bankDetails.data.iban ?? "",
      swift_bic: bankDetails.data.swift_bic ?? "",
    })
    setBankLoaded(true)
  }

  const saveBank = useMutation({
    mutationFn: () => updateBankDetailsApi(bank),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-bank-details"] }),
  })

  // Mirrors InstructorBankDetails.is_complete on the backend — SWIFT/BIC is
  // optional, so it is deliberately not checked here. Computed from local form
  // state rather than the query, so the gate lifts as the instructor types.
  const bankComplete = !!(
    bank.account_holder_name.trim() &&
    bank.bank_name.trim() &&
    bank.iban.trim()
  )

  const sign = useMutation({
    mutationFn: (signature: string) => signPaymentLetterApi(signingLetter!.id, signature),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-payment-letters"] })
      qc.invalidateQueries({ queryKey: ["instructor-payment-summary"] })
      setSigningLetter(null)
    },
  })

  // Waits on the bank query too: the form is hydrated by the `bankLoaded` latch
  // above, and BankSelect reads its dropdown-vs-free-text mode once at mount —
  // mounting before the data lands would strand a saved custom bank name.
  if (letters.isLoading || summary.isLoading || bankDetails.isLoading) return <Spinner />

  return (
    <div>
      <PageHeader title="Payments" subtitle="View and sign your facilitator payment letters." />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <StatCard icon={<Banknote size={20} />} label="Total Earned (AED)" value={summary.data?.total_earned_aed.toLocaleString() ?? 0} />
        <StatCard icon={<Banknote size={20} />} label="Hours Delivered" value={summary.data?.total_hours ?? 0} />
        <StatCard icon={<Calendar size={20} />} label="Sessions" value={summary.data?.total_sessions ?? 0} />
        <StatCard icon={<Banknote size={20} />} label="Pending Signature" value={summary.data?.pending_signature ?? 0} />
      </div>

      <Card className="mb-6">
        <CardHeader><CardTitle>Bank Details</CardTitle></CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-3">
          <input className="input" placeholder="Account holder name" value={bank.account_holder_name}
            onChange={(e) => setBank({ ...bank, account_holder_name: e.target.value })} />
          <BankSelect
            className="input"
            value={bank.bank_name}
            onChange={(next) => setBank({
              ...bank,
              bank_name: next.bank_name,
              // Only a listed bank carries a code; picking "Other" leaves
              // whatever the instructor typed alone.
              swift_bic: next.swift_bic ?? bank.swift_bic,
            })}
          />
          <input className="input" placeholder="IBAN" value={bank.iban}
            onChange={(e) => setBank({ ...bank, iban: e.target.value })} />
          <input className="input" placeholder="SWIFT/BIC (optional)" value={bank.swift_bic}
            onChange={(e) => setBank({ ...bank, swift_bic: e.target.value })} />
          <Button onClick={() => saveBank.mutate()} disabled={saveBank.isPending} className="sm:col-span-2 w-fit">
            {saveBank.isPending ? "Saving…" : "Save bank details"}
          </Button>
          {!bankComplete && (
            <p className="sm:col-span-2 flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
              <AlertTriangle size={14} className="shrink-0" />
              Add your account holder name, bank, and IBAN to unlock signing your payment
              letters. SWIFT/BIC is optional.
            </p>
          )}
        </CardContent>
      </Card>

      <h2 className="text-lg font-semibold mb-3">Payment Letters</h2>
      {(letters.data ?? []).length === 0 ? (
        <EmptyState title="No payment letters yet" hint="Letters appear here once an admin publishes one." />
      ) : (
        <div className="space-y-3">
          {letters.data!.map((l) => (
            <Card key={l.id}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div>
                    <p className="font-semibold">{l.reference}</p>
                    <p className="text-xs text-muted-foreground">{l.letter_date}</p>
                  </div>
                  <StatusPill status={l.status} />
                </div>
                <div className="space-y-1.5 mb-3">
                  {l.sessions.map((s) => (
                    <div key={s.id} className="text-sm flex items-center gap-2 text-muted-foreground">
                      <MapPin size={14} className="shrink-0" />
                      <span className="truncate">{s.workshop_description} — {s.role} — AED {s.compensation_aed.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  {l.status === "published" && (
                    bankComplete ? (
                      <Button size="sm" onClick={() => setSigningLetter(l)}>Sign letter</Button>
                    ) : (
                      <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                        <AlertTriangle size={14} className="shrink-0" />
                        Add your bank details above to sign this letter.
                      </div>
                    )
                  )}
                  {(l.pdf_url || l.signed_pdf_url) && (
                    <a href={l.signed_pdf_url ?? l.pdf_url ?? "#"} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="outline"><Download size={14} className="mr-1.5" /> Download</Button>
                    </a>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!signingLetter} onOpenChange={(open) => !open && setSigningLetter(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Sign Payment Letter</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground mb-3">
            By signing, you confirm agreement to the terms of this payment letter.
          </p>
          {sign.isError && (
            <p className="text-sm text-destructive mb-3">
              {sign.error instanceof Error ? sign.error.message : "Could not sign this letter. Please try again."}
            </p>
          )}
          <SignaturePad onSign={(sig) => sign.mutate(sig)} signing={sign.isPending} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
