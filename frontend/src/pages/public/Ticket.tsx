/** Public ticket page — /t/:ticketToken
 *
 * Both the QR code and the "view your ticket" link in the confirmation email
 * point here. It has no auth: the token in the URL is the credential, the
 * same way it is when a staff member scans the QR at the door. Anyone holding
 * the link is, by construction, holding the ticket.
 */
import { useQuery } from "@tanstack/react-query"
import { useParams } from "@tanstack/react-router"
import { CalendarDays, MapPin, ExternalLink, CheckCircle2, Ticket as TicketIcon } from "lucide-react"

import { apiBaseUrl } from "@/api/client"
import { getPublicTicketApi } from "@/api/sessions/public"

export default function Ticket() {
  const { ticketToken } = useParams({ from: "/t/$ticketToken" })

  const { data: ticket, isLoading, isError } = useQuery({
    queryKey: ["public-ticket", ticketToken],
    queryFn: () => getPublicTicketApi(ticketToken),
    retry: false,
  })

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background">
      <div className="w-full max-w-sm">
        {isLoading ? (
          <div className="h-64 rounded-3xl border border-border bg-card animate-pulse" />
        ) : isError || !ticket ? (
          <div className="rounded-3xl border border-border bg-card p-8 text-center">
            <p className="text-base font-semibold text-foreground">Ticket not found</p>
            <p className="text-sm text-muted-foreground mt-2">
              This link doesn't match any ticket. Check you copied it in full, or use the
              link in your confirmation email.
            </p>
          </div>
        ) : (
          <div className="rounded-3xl border border-border bg-card overflow-hidden shadow-sm">
            <div className="px-6 py-5 border-b border-border flex items-center gap-2">
              <TicketIcon size={18} className="text-primary" />
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                SpacePoint ticket
              </p>
            </div>

            <div className="px-6 py-6 flex flex-col gap-5">
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground font-medium">Attendee</p>
                <p className="text-xl font-bold text-foreground mt-0.5">{ticket.student_name}</p>
              </div>

              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground font-medium">Workshop</p>
                <p className="text-base font-semibold text-foreground mt-0.5">{ticket.program_name}</p>
                <p className="text-sm text-muted-foreground">{ticket.cohort_name}</p>
              </div>

              <div className="flex flex-col gap-2 text-sm text-foreground">
                <p className="flex items-center gap-2">
                  <CalendarDays size={15} className="text-muted-foreground shrink-0" />
                  {ticket.dates}
                </p>
                {ticket.location && (
                  <p className="flex items-center gap-2">
                    <MapPin size={15} className="text-muted-foreground shrink-0" />
                    {ticket.location}
                  </p>
                )}
                {ticket.location_address && (
                  <p className="flex items-center gap-2 text-muted-foreground">
                    <span className="w-[15px] shrink-0" />
                    {ticket.location_address}
                  </p>
                )}
                {ticket.location_maps_url && (
                  <a
                    href={ticket.location_maps_url} target="_blank" rel="noreferrer"
                    className="flex items-center gap-2 text-sm font-medium text-primary hover:underline w-fit"
                  >
                    <span className="w-[15px] shrink-0" />
                    Open in Google Maps <ExternalLink size={12} />
                  </a>
                )}
              </div>

              {/* The QR is served straight from the API so the image is
                  identical to the one embedded in the email. */}
              <div className="bg-white rounded-2xl p-4 flex items-center justify-center">
                <img
                  src={`${apiBaseUrl}/public/ticket/${ticket.ticket_token}/qr.png`}
                  alt="Ticket QR code"
                  className="w-44 h-44"
                />
              </div>

              <p className="text-xs text-center text-muted-foreground">
                Show this QR code at the door.
              </p>

              {ticket.checked_in && (
                <div className="flex items-center justify-center gap-1.5 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 size={16} /> Checked in
                </div>
              )}
              {ticket.status === "cancelled" && (
                <div className="text-sm font-semibold text-red-600 dark:text-red-400 text-center">
                  This registration was cancelled.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
