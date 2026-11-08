import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  Edit3,
  ExternalLink,
  GraduationCap,
  Image as ImageIcon,
  Mail,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Users,
  X,
} from "lucide-react";
import {
  BoothEvent,
  BoothPhoto,
  createBoothEventApi,
  deleteBoothEventApi,
  getBoothAnalyticsApi,
  listBoothEventsApi,
  listBoothPhotosApi,
  resendBoothPhotoEmailApi,
  updateBoothEventApi,
} from "@/api/booth";
import { listInviteCodesApi } from "@/api/lms_admin";
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives";
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common";

export default function BoothOperations() {
  const queryClient = useQueryClient();
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<BoothEvent | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BoothEvent | null>(null);
  const [previewPhoto, setPreviewPhoto] = useState<BoothPhoto | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [copiedSlug, setCopiedSlug] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // 1. Analytics & Events
  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ["booth-analytics", selectedEventId],
    queryFn: () => getBoothAnalyticsApi(selectedEventId || undefined),
  });

  const { data: events = [], isLoading: eventsLoading } = useQuery({
    queryKey: ["booth-events"],
    queryFn: listBoothEventsApi,
  });

  const { data: inviteCodes = [] } = useQuery({
    queryKey: ["lms-admin-invite-codes"],
    queryFn: listInviteCodesApi,
  });

  // Selected event (default to first active event if not selected)
  const activeEvent = selectedEventId
    ? events.find((e) => e.id === selectedEventId) || events[0]
    : events[0];

  // 2. Photos query
  const {
    data: photosData = { items: [], total: 0, page: 1, limit: 25 },
    isLoading: photosLoading,
    refetch: refetchPhotos,
  } = useQuery({
    queryKey: ["booth-photos", activeEvent?.id, page, search],
    queryFn: () =>
      activeEvent
        ? listBoothPhotosApi(activeEvent.id, { page, limit: 25, search: search || undefined })
        : Promise.resolve({ items: [], total: 0, page: 1, limit: 25 }),
    enabled: !!activeEvent,
  });

  // 3. Form State for Create / Edit
  const [formData, setFormData] = useState({
    name: "",
    slug: "",
    description: "",
    is_active: true,
    invitation_code_id: "",
    auto_create_lms_account: true,
    email_subject: "",
  });

  const openCreateModal = () => {
    setFormData({
      name: "",
      slug: "",
      description: "",
      is_active: true,
      invitation_code_id: "",
      auto_create_lms_account: true,
      email_subject: "",
    });
    setAddModalOpen(true);
  };

  const openEditModal = (ev: BoothEvent) => {
    setEditTarget(ev);
    setFormData({
      name: ev.name,
      slug: ev.slug,
      description: ev.description || "",
      is_active: ev.is_active,
      invitation_code_id: ev.invitation_code_id || "",
      auto_create_lms_account: ev.auto_create_lms_account,
      email_subject: ev.email_subject || "",
    });
  };

  // 4. Mutations
  const createMutation = useMutation({
    mutationFn: () =>
      createBoothEventApi({
        name: formData.name,
        slug: formData.slug || undefined,
        description: formData.description || undefined,
        is_active: formData.is_active,
        invitation_code_id: formData.invitation_code_id || undefined,
        auto_create_lms_account: formData.auto_create_lms_account,
        email_subject: formData.email_subject || undefined,
      }),
    onSuccess: (newEvent) => {
      queryClient.invalidateQueries({ queryKey: ["booth-events"] });
      setAddModalOpen(false);
      setSelectedEventId(newEvent.id);
      showToast("Booth event created successfully!");
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      editTarget
        ? updateBoothEventApi(editTarget.id, {
            name: formData.name,
            slug: formData.slug || undefined,
            description: formData.description || undefined,
            is_active: formData.is_active,
            invitation_code_id: formData.invitation_code_id || undefined,
            auto_create_lms_account: formData.auto_create_lms_account,
            email_subject: formData.email_subject || undefined,
          })
        : Promise.reject(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["booth-events"] });
      setEditTarget(null);
      showToast("Booth event updated!");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => (deleteTarget ? deleteBoothEventApi(deleteTarget.id) : Promise.reject()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["booth-events"] });
      setDeleteTarget(null);
      setSelectedEventId(null);
      showToast("Event deleted");
    },
  });

  const resendEmailMutation = useMutation({
    mutationFn: (photoId: string) => resendBoothPhotoEmailApi(photoId),
    onSuccess: () => {
      refetchPhotos();
      showToast("Photo email dispatched successfully!");
    },
    onError: (err: any) => {
      showToast(`Email error: ${err.response?.data?.detail || err.message}`);
    },
    onSettled: () => setResendingId(null),
  });

  const handleCopyKioskLink = (slug: string) => {
    const url = `https://selfie.spacepoint.ae?event=${slug}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedSlug(slug);
      setTimeout(() => setCopiedSlug(null), 2000);
    });
  };

  const studentCodes = inviteCodes.filter((c) => c.kind === "student");

  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto">
      {/* Toast Alert */}
      {toastMessage && (
        <div className="fixed top-4 right-4 z-50 bg-emerald-600 text-white px-5 py-3 rounded-xl shadow-xl flex items-center gap-2 text-sm font-medium animate-in fade-in slide-in-from-top-2">
          <CheckCircle2 className="w-5 h-5" />
          {toastMessage}
        </div>
      )}

      {/* Header */}
      <PageHeader
        title="CubeSat Booth Operations"
        subtitle="Manage event photobooths, auto-enroll participants into SpacePoint LMS, and track student onboarding analytics."
        action={
          <button
            onClick={openCreateModal}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            New Event
          </button>
        }
      />

      {/* Analytics Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Photos Captured</span>
            <Camera className="w-5 h-5 text-purple-400" />
          </div>
          <div className="text-3xl font-extrabold text-white">
            {analyticsLoading ? <Spinner /> : analytics?.total_photos ?? 0}
          </div>
          <p className="text-xs text-slate-500 mt-1">Satellite selfies taken across booths</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">LMS Accounts Created</span>
            <GraduationCap className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="text-3xl font-extrabold text-white">
            {analyticsLoading ? <Spinner /> : analytics?.new_lms_users_created ?? 0}
          </div>
          <p className="text-xs text-slate-500 mt-1">New students automatically registered</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Students Logged In</span>
            <Users className="w-5 h-5 text-sky-400" />
          </div>
          <div className="text-3xl font-extrabold text-white">
            {analyticsLoading ? <Spinner /> : analytics?.logged_in_students ?? 0}
          </div>
          <p className="text-xs text-slate-500 mt-1">Activated accounts with recorded logins</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Login Conversion</span>
            <Sparkles className="w-5 h-5 text-amber-400" />
          </div>
          <div className="text-3xl font-extrabold text-white">
            {analyticsLoading ? <Spinner /> : `${analytics?.login_conversion_rate ?? 0}%`}
          </div>
          <p className="text-xs text-slate-500 mt-1">From booth selfie to LMS active learner</p>
        </div>
      </div>

      {/* Events Selector & Tabs */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2 overflow-x-auto pb-1 max-w-full">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider whitespace-nowrap mr-2">
              Events:
            </span>
            {eventsLoading ? (
              <Spinner />
            ) : events.length === 0 ? (
              <span className="text-sm text-slate-500">No events yet. Click 'New Event' to create one.</span>
            ) : (
              events.map((ev) => {
                const isSelected = activeEvent?.id === ev.id;
                return (
                  <button
                    key={ev.id}
                    onClick={() => {
                      setSelectedEventId(ev.id);
                      setPage(1);
                    }}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition whitespace-nowrap ${
                      isSelected
                        ? "bg-purple-600 text-white shadow-sm"
                        : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                    }`}
                  >
                    <span>{ev.name}</span>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded-full ${
                        isSelected ? "bg-purple-800 text-purple-200" : "bg-slate-700 text-slate-400"
                      }`}
                    >
                      {ev.total_photos}
                    </span>
                  </button>
                );
              })
            )}
          </div>

          {activeEvent && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleCopyKioskLink(activeEvent.slug)}
                className="flex items-center gap-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700 transition"
                title="Copy Kiosk URL for tablets/booths"
              >
                {copiedSlug === activeEvent.slug ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedSlug === activeEvent.slug ? "Copied!" : "Kiosk Link"}</span>
              </button>

              <button
                onClick={() => openEditModal(activeEvent)}
                className="p-1.5 text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg border border-slate-700 transition"
                title="Edit Event"
              >
                <Edit3 className="w-4 h-4" />
              </button>

              <button
                onClick={() => setDeleteTarget(activeEvent)}
                className="p-1.5 text-rose-400 hover:text-rose-300 bg-slate-800 hover:bg-rose-950/40 rounded-lg border border-slate-700 transition"
                title="Delete Event"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>

        {/* Active Event Details Banner */}
        {activeEvent && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-4 text-xs text-slate-400">
            <div className="flex flex-wrap items-center gap-3">
              <span>
                Slug: <code className="text-purple-300 font-mono bg-purple-950/40 px-1.5 py-0.5 rounded">{activeEvent.slug}</code>
              </span>
              <span>
                Status:{" "}
                <span className={`px-2 py-0.5 rounded-full font-semibold ${activeEvent.is_active ? "bg-emerald-950 text-emerald-400 border border-emerald-800" : "bg-slate-800 text-slate-500"}`}>
                  {activeEvent.is_active ? "Active" : "Archived"}
                </span>
              </span>
              <span>
                LMS Provisioning:{" "}
                <span className={`px-2 py-0.5 rounded-full font-semibold ${activeEvent.auto_create_lms_account ? "bg-purple-950 text-purple-300 border border-purple-800" : "bg-slate-800 text-slate-400"}`}>
                  {activeEvent.auto_create_lms_account ? "Enabled" : "Off"}
                </span>
              </span>
              {activeEvent.invitation_code_str && (
                <span>
                  Linked Invite Code:{" "}
                  <span className="font-mono bg-slate-800 text-slate-200 px-1.5 py-0.5 rounded border border-slate-700">
                    {activeEvent.invitation_code_str}
                  </span>
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-300">{photosData.total}</span> total captures logged
            </div>
          </div>
        )}
      </div>

      {/* Participant Photos & Logs Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        {/* Table Search & Controls */}
        <div className="p-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
          <div className="relative flex-1 min-w-[240px] max-w-md">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search participants by name or email..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="w-full pl-9 pr-3 py-1.5 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-purple-500"
            />
          </div>

          <button
            onClick={() => refetchPhotos()}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg border border-slate-700 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>

        {/* Table Content */}
        {photosLoading ? (
          <div className="p-12 flex justify-center">
            <Spinner />
          </div>
        ) : photosData.items.length === 0 ? (
          <div className="p-12 text-center">
            <EmptyState
              title="No photos captured yet"
              description="Photos captured from the booth kiosk will show up here live, along with student LMS creation status and delivery reports."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-slate-950 text-xs uppercase font-semibold text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Photo</th>
                  <th className="py-3 px-4">Participant</th>
                  <th className="py-3 px-4">LMS Student Status</th>
                  <th className="py-3 px-4">Logged In?</th>
                  <th className="py-3 px-4">Email Delivery</th>
                  <th className="py-3 px-4">Captured At</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {photosData.items.map((photo) => (
                  <tr key={photo.id} className="hover:bg-slate-800/40 transition">
                    {/* Thumbnail */}
                    <td className="py-3 px-4">
                      {photo.photo_url ? (
                        <button
                          onClick={() => setPreviewPhoto(photo)}
                          className="group relative w-12 h-12 rounded-lg overflow-hidden border border-slate-700 bg-slate-950 flex items-center justify-center hover:border-purple-500 transition"
                        >
                          <img
                            src={photo.photo_url}
                            alt="Capture"
                            className="w-full h-full object-cover group-hover:scale-105 transition"
                          />
                        </button>
                      ) : (
                        <div className="w-12 h-12 rounded-lg border border-slate-800 bg-slate-950 flex items-center justify-center text-slate-600">
                          <ImageIcon className="w-5 h-5" />
                        </div>
                      )}
                    </td>

                    {/* Participant */}
                    <td className="py-3 px-4">
                      <div className="font-semibold text-white">{photo.participant_name}</div>
                      <div className="text-xs text-slate-400 font-mono">{photo.participant_email}</div>
                      {photo.satellite_id && (
                        <span className="text-[10px] text-slate-500 font-mono">
                          Booth: {photo.satellite_id}
                        </span>
                      )}
                    </td>

                    {/* LMS Student Status */}
                    <td className="py-3 px-4">
                      {photo.is_new_lms_user ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                          <Sparkles className="w-3 h-3" />
                          New Student Account
                        </span>
                      ) : photo.user_id ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-950 text-purple-300 border border-purple-800">
                          Existing Student
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400">
                          Guest (No LMS)
                        </span>
                      )}
                    </td>

                    {/* Logged in status */}
                    <td className="py-3 px-4">
                      {photo.student_logged_in ? (
                        <div className="inline-flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          <span>Logged in</span>
                        </div>
                      ) : photo.is_new_lms_user ? (
                        <div className="inline-flex items-center gap-1.5 text-xs text-amber-400">
                          <Clock className="w-3.5 h-3.5" />
                          <span>Pending Activation</span>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-500">—</span>
                      )}
                    </td>

                    {/* Email Delivery */}
                    <td className="py-3 px-4">
                      {photo.email_sent ? (
                        <div className="inline-flex items-center gap-1.5 text-xs text-emerald-400">
                          <Check className="w-3.5 h-3.5" />
                          <span>Sent</span>
                        </div>
                      ) : (
                        <div className="text-xs text-rose-400 font-medium" title={photo.email_error || "Pending send"}>
                          Failed / Pending
                        </div>
                      )}
                    </td>

                    {/* Captured At */}
                    <td className="py-3 px-4 text-xs text-slate-400">
                      {new Date(photo.created_at).toLocaleString("en-AE", {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button
                          onClick={() => {
                            setResendingId(photo.id);
                            resendEmailMutation.mutate(photo.id);
                          }}
                          disabled={resendingId === photo.id}
                          className="p-1.5 text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg border border-slate-700 transition"
                          title="Resend Photo Email"
                        >
                          <Mail className={`w-3.5 h-3.5 ${resendingId === photo.id ? "animate-spin" : ""}`} />
                        </button>

                        {photo.photo_url && (
                          <a
                            href={photo.photo_url}
                            target="_blank"
                            rel="noreferrer"
                            className="p-1.5 text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg border border-slate-700 transition"
                            title="Open High-Res Photo"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {photosData.total > photosData.limit && (
          <div className="p-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <span>
              Showing {(page - 1) * photosData.limit + 1} to{" "}
              {Math.min(page * photosData.limit, photosData.total)} of {photosData.total} photos
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 rounded-md transition"
              >
                Previous
              </button>
              <button
                disabled={page * photosData.limit >= photosData.total}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 rounded-md transition"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal: Create Event */}
      <Modal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        title="Create CubeSat Booth Event"
      >
        <div className="space-y-4">
          <Field label="Event Name" required>
            <input
              type="text"
              placeholder="e.g. Sharjah Entrepreneurship Festival 2026"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            />
          </Field>

          <Field label="Event Slug (URL identifier)" hint="Used in the booth URL: selfie.spacepoint.ae?event=your-slug">
            <input
              type="text"
              placeholder="e.g. sef-2026 (leave empty to auto-generate)"
              value={formData.slug}
              onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono"
            />
          </Field>

          <Field label="Linked LMS Invite Code" hint="Attaches course/cohort access grants to participants who join from this event.">
            <select
              value={formData.invitation_code_id}
              onChange={(e) => setFormData({ ...formData, invitation_code_id: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            >
              <option value="">-- No Invite Code linked --</option>
              {studentCodes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} {c.label ? `(${c.label})` : ""} - {c.used_count}/{c.max_uses} uses
                </option>
              ))}
            </select>
          </Field>

          <div className="pt-2">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.auto_create_lms_account}
                onChange={(e) => setFormData({ ...formData, auto_create_lms_account: e.target.checked })}
                className="mt-1 rounded bg-slate-950 border-slate-700 text-purple-600 focus:ring-purple-500"
              />
              <div>
                <span className="text-sm font-semibold text-white">Automatically create SpacePoint LMS student accounts</span>
                <p className="text-xs text-slate-400">
                  New participants will receive their photo along with a secure activation link to set their password and access their space missions.
                </p>
              </div>
            </label>
          </div>

          <Field label="Email Subject (Optional override)">
            <input
              type="text"
              placeholder="e.g. Your CubeSat Photo — SpacePoint × SEF"
              value={formData.email_subject}
              onChange={(e) => setFormData({ ...formData, email_subject: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            />
          </Field>
        </div>

        <ModalActions
          onCancel={() => setAddModalOpen(false)}
          onConfirm={() => createMutation.mutate()}
          confirmText="Create Event"
          confirmDisabled={!formData.name.trim() || createMutation.isPending}
        />
      </Modal>

      {/* Modal: Edit Event */}
      <Modal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        title={`Edit Event: ${editTarget?.name}`}
      >
        <div className="space-y-4">
          <Field label="Event Name" required>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            />
          </Field>

          <Field label="Event Slug">
            <input
              type="text"
              value={formData.slug}
              onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono"
            />
          </Field>

          <Field label="Linked LMS Invite Code">
            <select
              value={formData.invitation_code_id}
              onChange={(e) => setFormData({ ...formData, invitation_code_id: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            >
              <option value="">-- No Invite Code linked --</option>
              {studentCodes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} {c.label ? `(${c.label})` : ""} - {c.used_count}/{c.max_uses} uses
                </option>
              ))}
            </select>
          </Field>

          <div className="pt-2">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.auto_create_lms_account}
                onChange={(e) => setFormData({ ...formData, auto_create_lms_account: e.target.checked })}
                className="mt-1 rounded bg-slate-950 border-slate-700 text-purple-600 focus:ring-purple-500"
              />
              <div>
                <span className="text-sm font-semibold text-white">Automatically create SpacePoint LMS student accounts</span>
                <p className="text-xs text-slate-400">
                  New participants will receive their photo along with a secure activation link.
                </p>
              </div>
            </label>
          </div>

          <div className="pt-2">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                className="rounded bg-slate-950 border-slate-700 text-purple-600 focus:ring-purple-500"
              />
              <span className="text-sm font-semibold text-white">Event is Active (Accepts captures)</span>
            </label>
          </div>

          <Field label="Email Subject">
            <input
              type="text"
              value={formData.email_subject}
              onChange={(e) => setFormData({ ...formData, email_subject: e.target.value })}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white"
            />
          </Field>
        </div>

        <ModalActions
          onCancel={() => setEditTarget(null)}
          onConfirm={() => updateMutation.mutate()}
          confirmText="Save Changes"
          confirmDisabled={!formData.name.trim() || updateMutation.isPending}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={`Delete Event: ${deleteTarget?.name}?`}
        description="This will permanently remove the event and all associated capture logs. Uploaded photos on R2 will remain untouched."
        confirmText="Delete"
        danger
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => deleteMutation.mutate()}
      />

      {/* Photo Preview Modal */}
      {previewPhoto && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full overflow-hidden shadow-2xl animate-in zoom-in-95">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="font-bold text-white text-base">{previewPhoto.participant_name}</h3>
                <p className="text-xs text-slate-400">{previewPhoto.participant_email}</p>
              </div>
              <button
                onClick={() => setPreviewPhoto(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 bg-slate-950 flex justify-center">
              {previewPhoto.photo_url ? (
                <img
                  src={previewPhoto.photo_url}
                  alt={previewPhoto.participant_name}
                  className="max-h-[60vh] max-w-full rounded-xl object-contain border border-slate-800 shadow-md"
                />
              ) : (
                <div className="p-12 text-slate-600">No preview URL available</div>
              )}
            </div>

            <div className="p-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <div>
                Captured: {new Date(previewPhoto.created_at).toLocaleString()}
                {previewPhoto.satellite_id && ` | Satellite: ${previewPhoto.satellite_id}`}
              </div>
              {previewPhoto.photo_url && (
                <a
                  href={previewPhoto.photo_url}
                  target="_blank"
                  download
                  rel="noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Download High-Res
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
