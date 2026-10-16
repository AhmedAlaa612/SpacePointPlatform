import { api } from "@/api/client";
import type {
  AvailableSlot,
  MentorAvailability,
  MentorBooking,
  MentorCreateIn,
  MentorDomain,
  MentorProfile,
  MentorPublicApplyIn,
  MentorPublicApplyOut,
} from "@/types/mentors";

// ── Public APIs ──────────────────────────────────────────────────────────────

export interface PublicMentorFilterParams {
  domain?: string;
  company?: string;
  mode?: "email" | "calendar";
  q?: string;
  limit?: number;
  offset?: number;
}

export async function getPublicMentors(params?: PublicMentorFilterParams): Promise<MentorProfile[]> {
  const { data } = await api.get<MentorProfile[]>("/mentors", { params });
  return data;
}

export async function getPublicMentor(slug: string): Promise<MentorProfile> {
  const { data } = await api.get<MentorProfile>(`/mentors/${slug}`);
  return data;
}

export async function getMentorAvailableSlots(slug: string, date: string, tz?: string): Promise<AvailableSlot[]> {
  const { data } = await api.get<AvailableSlot[]>(`/mentors/${slug}/slots`, {
    params: { date, tz },
  });
  return data;
}

export interface BookMentorInput {
  mentee_name: string;
  mentee_email: string;
  topics: string;
  scheduled_start?: string | null;
  booking_type?: "session" | "inquiry";
}

export async function bookMentorSession(slug: string, payload: BookMentorInput): Promise<MentorBooking> {
  const { data } = await api.post<MentorBooking>(`/mentors/${slug}/book`, payload);
  return data;
}

export async function cancelBookingByToken(cancelToken: string): Promise<{ status: string; message: string }> {
  const { data } = await api.post<{ status: string; message: string }>(`/bookings/${cancelToken}/cancel`);
  return data;
}

// ── Operations APIs ──────────────────────────────────────────────────────────

export async function getMentorDomains(isActive?: boolean): Promise<MentorDomain[]> {
  const params = isActive !== undefined ? { is_active: isActive } : undefined;
  const { data } = await api.get<MentorDomain[]>("/operations/mentor-domains", { params });
  return data;
}

export interface CreateMentorDomainInput {
  name: string;
  slug?: string;
  category?: string;
  display_order?: number;
  is_active?: boolean;
}

export async function createMentorDomain(payload: CreateMentorDomainInput): Promise<MentorDomain> {
  const { data } = await api.post<MentorDomain>("/operations/mentor-domains", payload);
  return data;
}

export async function updateMentorDomain(id: string, payload: Partial<CreateMentorDomainInput>): Promise<MentorDomain> {
  const { data } = await api.put<MentorDomain>(`/operations/mentor-domains/${id}`, payload);
  return data;
}

export async function deleteMentorDomain(id: string): Promise<void> {
  await api.delete(`/operations/mentor-domains/${id}`);
}

export async function getMentorApplications(): Promise<MentorProfile[]> {
  const { data } = await api.get<MentorProfile[]>("/operations/mentors/applications");
  return data;
}

export async function getAllMentors(status?: string, isActive?: boolean): Promise<MentorProfile[]> {
  const params: Record<string, any> = {};
  if (status) params.status = status;
  if (isActive !== undefined) params.is_active = isActive;
  const { data } = await api.get<MentorProfile[]>("/operations/mentors", { params });
  return data;
}

export async function reviewMentorApplication(
  mentorId: string,
  decision: "approved" | "rejected",
  reason?: string
): Promise<MentorProfile> {
  const { data } = await api.post<MentorProfile>(`/operations/mentors/${mentorId}/review`, {
    decision,
    reason,
  });
  return data;
}

export async function updateMentorStatus(
  mentorId: string,
  isActive: boolean,
  status?: "applied" | "approved" | "rejected" | "suspended"
): Promise<MentorProfile> {
  const { data } = await api.put<MentorProfile>(`/operations/mentors/${mentorId}/status`, {
    is_active: isActive,
    status,
  });
  return data;
}

// ── Mentor Self-Service APIs ─────────────────────────────────────────────────

export interface MentorApplyInput {
  headline: string;
  company: string;
  bio: string;
  missions_history?: string;
  what_i_can_help_with?: string;
  domain_ids?: string[];
  contact_mode?: "email" | "calendar";
  session_duration_minutes?: number;
  google_meet_url?: string;
  invite_code?: string;
  is_published?: boolean;
  photo_url?: string;
  contact_email?: string | null;
  show_contact_button?: boolean;
  linkedin_url?: string | null;
}

export async function applyToBecomeMentor(payload: MentorApplyInput): Promise<MentorProfile> {
  const { data } = await api.post<MentorProfile>("/mentor/apply", payload);
  return data;
}

export async function getMyMentorProfile(): Promise<MentorProfile> {
  const { data } = await api.get<MentorProfile>("/mentor/me");
  return data;
}

export async function updateMyMentorProfile(payload: Partial<MentorApplyInput>): Promise<MentorProfile> {
  const { data } = await api.put<MentorProfile>("/mentor/profile", payload);
  return data;
}

export async function uploadMyMentorPhoto(file: File): Promise<{ photo_url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await api.post<{ photo_url: string }>("/mentor/photo", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getMyAvailability(): Promise<MentorAvailability[]> {
  const { data } = await api.get<MentorAvailability[]>("/mentor/availability");
  return data;
}

export async function setMyAvailability(rules: Partial<MentorAvailability>[]): Promise<MentorAvailability[]> {
  const { data } = await api.put<MentorAvailability[]>("/mentor/availability", rules);
  return data;
}

export async function getMyMentorBookings(): Promise<MentorBooking[]> {
  const { data } = await api.get<MentorBooking[]>("/mentor/bookings");
  return data;
}

export async function createMentorDirectlyApi(payload: MentorCreateIn): Promise<MentorProfile> {
  const { data } = await api.post<MentorProfile>("/operations/mentors", payload);
  return data;
}

export async function applyPublicMentorApi(payload: MentorPublicApplyIn): Promise<MentorPublicApplyOut> {
  const { data } = await api.post<MentorPublicApplyOut>("/mentors/apply-public", payload);
  return data;
}

