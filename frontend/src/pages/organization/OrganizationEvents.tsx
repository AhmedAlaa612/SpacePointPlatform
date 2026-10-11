import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Building2,
  CalendarDays,
  CheckCircle2,
  Clock,
  ExternalLink,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react"
import { cn, getErrorMessage } from "@/lib/utils"
import { PageHeader, Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import {
  createMyOrganizationEvent,
  deleteMyOrganizationEvent,
  getMyOrganizationContext,
  getMyOrganizationEvents,
  updateMyOrganizationEvent,
  type WebsiteEvent,
  type WebsiteEventInput,
} from "@/api/websiteEvents"
import {
  emptyEventDraft,
  EventEditorModal,
} from "@/pages/operations/website/WebsiteEventsPanel"

const WEBSITE_BASE_URL =
  (import.meta.env.VITE_WEBSITE_URL as string | undefined)?.replace(/\/$/, "") ||
  (typeof window !== "undefined" &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1"
    ? "https://spacepoint.ae"
    : "http://localhost:4321")

export default function OrganizationEvents() {
  const toast = useToast()
  const qc = useQueryClient()

  const ctxQuery = useQuery({
    queryKey: ["my-organization-context"],
    queryFn: getMyOrganizationContext,
  })
  const eventsQuery = useQuery({
    queryKey: ["my-organization-events"],
    queryFn: getMyOrganizationEvents,
  })

  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<WebsiteEvent | null>(null)

  const saveMut = useMutation({
    mutationFn: (payload: WebsiteEventInput) =>
      editing
        ? updateMyOrganizationEvent(editing.id, payload)
        : createMyOrganizationEvent(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["my-organization-events"] })
      setCreating(false)
      setEditing(null)
      toast.success(
        editing
          ? "Event updated!"
          : "Event created! An administrator will review and publish it to the website."
      )
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to save event")),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteMyOrganizationEvent(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["my-organization-events"] })
      toast.success("Event removed")
    },
  })

  if (ctxQuery.isLoading || eventsQuery.isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    )
  }

  const org = ctxQuery.data?.organization
  const megaEvents = ctxQuery.data?.mega_events || []
  const events = eventsQuery.data || []

  if (creating || editing) {
    return (
      <EventEditorModal
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        initial={
          editing
            ? editing
            : emptyEventDraft({
                host_org_name: org?.name_latin || "",
                country: org?.country || "uae",
                city: org?.city || "Abu Dhabi",
              })
        }
        megaEvents={megaEvents}
        isAdmin={false}
        saving={saveMut.isPending}
        onSave={(payload) => saveMut.mutate(payload)}
      />
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <PageHeader
          title={org ? `${org.name_latin} — Events` : "My Organization Events"}
          subtitle="Create and customize your event landing pages."
        />

        <button
          type="button"
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground hover:opacity-90 transition"
        >
          <Plus className="h-4 w-4" />
          Add Event
        </button>
      </div>

      {/* Organization Info Card */}
      {org && (
        <div className="rounded-2xl border border-border bg-card p-5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/15 text-primary">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">{org.name_latin}</h3>
              <p className="text-xs text-muted-foreground">
                {org.org_type.toUpperCase()} • {org.city || org.country.toUpperCase()}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Events List */}
      {events.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-card p-12 text-center space-y-3">
          <CalendarDays className="mx-auto h-10 w-10 text-muted-foreground" />
          <h3 className="text-base font-bold text-foreground">
            No events created yet
          </h3>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            Click &ldquo;Add Event&rdquo; to build a landing page for your competition, workshop, or World Space Week activity.
          </p>
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90"
          >
            <Plus className="h-4 w-4" /> Create Your First Event
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {events.map((ev) => (
            <div
              key={ev.id}
              className="rounded-2xl border border-border bg-card p-5 flex flex-col md:flex-row md:items-center justify-between gap-4"
            >
              <div className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold uppercase",
                      ev.is_published
                        ? "bg-primary/20 text-primary"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {ev.is_published ? (
                      <>
                        <CheckCircle2 className="h-3.5 w-3.5" /> Published Live
                      </>
                    ) : (
                      <>
                        <Clock className="h-3.5 w-3.5" /> Pending Admin Approval
                      </>
                    )}
                  </span>

                  <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-semibold uppercase text-foreground">
                    /events/{ev.country}/{ev.slug}
                  </span>

                  {ev.mega_event_title && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-semibold text-primary">
                      Parent: {ev.mega_event_title}
                      <button
                        type="button"
                        onClick={() =>
                          updateMyOrganizationEvent(ev.id, { mega_event_id: null }).then(() => {
                            void qc.invalidateQueries({ queryKey: ["my-organization-events"] })
                            toast.success("Detached from Featured Event")
                          })
                        }
                        title="Remove from Parent Featured Event"
                        className="ml-0.5 rounded-full px-1 hover:bg-primary/25 text-primary"
                      >
                        ×
                      </button>
                    </span>
                  )}
                </div>

                <h3 className="text-lg font-bold text-foreground">{ev.title}</h3>
                <p className="text-xs text-muted-foreground">
                  {ev.subtitle || ev.tagline} • {ev.city || ev.country.toUpperCase()} •{" "}
                  {ev.date_label || "Date TBA"}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {megaEvents.length > 0 && (
                  <select
                    value={ev.mega_event_id || ""}
                    onChange={(e) =>
                      updateMyOrganizationEvent(ev.id, {
                        mega_event_id: e.target.value || null,
                      }).then(() => {
                        void qc.invalidateQueries({ queryKey: ["my-organization-events"] })
                        toast.success(
                          e.target.value
                            ? "Parent Featured Event assigned"
                            : "Event set as standalone"
                        )
                      })
                    }
                    className="h-9 rounded-xl border border-border bg-background px-3 text-xs font-medium text-foreground"
                    title="Set Parent Featured Event"
                  >
                    <option value="">Parent: None (Standalone)</option>
                    {megaEvents.map((m) => (
                      <option key={m.id} value={m.id}>
                        Parent: {m.title}
                      </option>
                    ))}
                  </select>
                )}

                {ev.is_published && (
                  <a
                    href={`${WEBSITE_BASE_URL}/events/${ev.country}/${ev.slug}`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 rounded-xl border border-border bg-background px-3.5 py-2 text-xs font-semibold text-foreground hover:bg-muted"
                  >
                    <ExternalLink className="h-3.5 w-3.5" /> View Live
                  </a>
                )}

                <button
                  type="button"
                  onClick={() => setEditing(ev)}
                  className="inline-flex items-center gap-1 rounded-xl bg-primary/15 px-3.5 py-2 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Pencil className="h-3.5 w-3.5" /> Open Event
                </button>

                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Remove event "${ev.title}"?`)) {
                      deleteMut.mutate(ev.id)
                    }
                  }}
                  className="rounded-xl border border-border bg-background p-2 text-muted-foreground hover:text-foreground"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
