import { api } from "@/api/client"
import type { PaymentLetter, PaymentSummary } from "@/types/instructors"

export const listPaymentLettersApi = () =>
  api.get<PaymentLetter[]>("/instructors/payments/letters").then((r) => r.data)

export const getPaymentLetterApi = (letterId: string) =>
  api.get<PaymentLetter>(`/instructors/payments/letters/${letterId}`).then((r) => r.data)

export const signPaymentLetterApi = (letterId: string, signature: string) =>
  api.post<PaymentLetter>(`/instructors/payments/letters/${letterId}/sign`, { signature }).then((r) => r.data)

export const downloadPaymentLetterApi = (letterId: string) =>
  api.get<{ url: string }>(`/instructors/payments/letters/${letterId}/download`).then((r) => r.data.url)

export const getPaymentSummaryApi = () =>
  api.get<PaymentSummary>("/instructors/payments/summary").then((r) => r.data)
