import { api } from "@/api/client";

export interface BoothEvent {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  is_active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  invitation_code_id: string | null;
  invitation_code_str: string | null;
  auto_create_lms_account: boolean;
  email_subject: string | null;
  created_at: string;
  total_photos: number;
  new_lms_users_created: number;
  logged_in_students: number;
}

export interface BoothPhoto {
  id: string;
  event_id: string;
  participant_name: string;
  participant_email: string;
  storage_path: string;
  satellite_id: string | null;
  user_id: string | null;
  is_new_lms_user: boolean;
  email_sent: boolean;
  email_sent_at: string | null;
  email_error: string | null;
  created_at: string;
  student_logged_in: boolean;
  last_login_at: string | null;
  photo_url: string | null;
}

export interface BoothAnalytics {
  total_photos: number;
  new_lms_users_created: number;
  logged_in_students: number;
  login_conversion_rate: number;
}

export const getBoothAnalyticsApi = (eventId?: string) =>
  api.get<BoothAnalytics>("/operations/booth/analytics", { params: { event_id: eventId } }).then((r) => r.data);

export const listBoothEventsApi = () =>
  api.get<BoothEvent[]>("/operations/booth/events").then((r) => r.data);

export const getBoothEventApi = (id: string) =>
  api.get<BoothEvent>(`/operations/booth/events/${id}`).then((r) => r.data);

export const createBoothEventApi = (data: Partial<BoothEvent>) =>
  api.post<BoothEvent>("/operations/booth/events", data).then((r) => r.data);

export const updateBoothEventApi = (id: string, data: Partial<BoothEvent>) =>
  api.patch<BoothEvent>(`/operations/booth/events/${id}`, data).then((r) => r.data);

export const deleteBoothEventApi = (id: string) =>
  api.delete<{ success: boolean }>(`/operations/booth/events/${id}`).then((r) => r.data);

export const listBoothPhotosApi = (
  eventId: string,
  params: { page?: number; limit?: number; search?: string } = {}
) =>
  api
    .get<{ items: BoothPhoto[]; total: number; page: number; limit: number }>(
      `/operations/booth/events/${eventId}/photos`,
      { params }
    )
    .then((r) => r.data);

export const resendBoothPhotoEmailApi = (photoId: string) =>
  api.post<{ success: boolean; message: string }>(`/operations/booth/photos/${photoId}/resend-email`).then((r) => r.data);
