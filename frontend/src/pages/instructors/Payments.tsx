import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Banknote, Calendar, Download, MapPin } from "lucide-react"
import {
  getBankDetailsApi, updateBankDetailsApi,
} from "@/api/instructors/instructor"
import { getPaymentSummaryApi, listPaymentLettersApi, signPaymentLetterApi } from "@/api/instructors/payments"
import type { PaymentLetter } from "@/types/instructors"
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

  const sign = useMutation({
    mutationFn: (signature: string) => signPaymentLetterApi(signingLetter!.id, signature),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-payment-letters"] })
      qc.invalidateQueries({ queryKey: ["instructor-payment-summary"] })
      setSigningLetter(null)
    },
  })

  if (letters.isLoading || summary.isLoading) return <Spinner />

  return (
    <div>
      <PageHeader title="Payments" subtitle="View and sign your facilitator payment letters." />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <StatCard icon={<Banknote size={20} />} label="Earned (AED)" value={summary.data?.total_earned_aed.toLocaleString() ?? 0} />
        <StatCard icon={<Calendar size={20} />} label="Sessions" value={summary.data?.total_sessions ?? 0} />
        <StatCard icon={<Banknote size={20} />} label="Hours" value={summary.data?.total_hours ?? 0} />
        <StatCard icon={<Banknote size={20} />} label="Pending signature" value={summary.data?.pending_signature ?? 0} />
      </div>

      <Card className="mb-6">
        <CardHeader><CardTitle>Bank Details</CardTitle></CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-3">
          <input className="input" placeholder="Account holder name" value={bank.account_holder_name}
            onChange={(e) => setBank({ ...bank, account_holder_name: e.target.value })} />
          <input className="input" placeholder="Bank name" value={bank.bank_name}
            onChange={(e) => setBank({ ...bank, bank_name: e.target.value })} />
          <input className="input" placeholder="IBAN" value={bank.iban}
            onChange={(e) => setBank({ ...bank, iban: e.target.value })} />
          <input className="input" placeholder="SWIFT/BIC" value={bank.swift_bic}
            onChange={(e) => setBank({ ...bank, swift_bic: e.target.value })} />
          <Button onClick={() => saveBank.mutate()} disabled={saveBank.isPending} className="sm:col-span-2 w-fit">
            {saveBank.isPending ? "Saving…" : "Save bank details"}
          </Button>
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
                <div className="flex gap-2">
                  {l.status === "published" && (
                    <Button size="sm" onClick={() => setSigningLetter(l)}>Sign letter</Button>
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
          <SignaturePad onSign={(sig) => sign.mutate(sig)} signing={sign.isPending} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
