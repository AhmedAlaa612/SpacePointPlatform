import { api } from "@/api/client"
import type { PublicTicket } from "@/types/sessions"

/** No auth — the token in the path is the credential (same as the QR at the door). */
export const getPublicTicketApi = (ticketToken: string) =>
  api.get<PublicTicket>(`/public/ticket/${ticketToken}`).then((r) => r.data)
