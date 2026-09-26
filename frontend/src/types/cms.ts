export type ArticleStatus = "draft" | "in_review" | "changes_requested" | "published" | "archived";

export interface Article {
  id: string;
  slug: string;
  title: string;
  summary: string | null;
  content_markdown: string;
  content_html: string;
  category: string;
  author_id: string | null;
  author_display_name: string;
  author_role: string | null;
  author_initials: string | null;
  cover_image_url: string | null;
  status: ArticleStatus;
  reviewer_feedback: string | null;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  featured_order: number | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArticleCreateInput {
  title: string;
  summary?: string | null;
  category: string;
  cover_image_url?: string | null;
  content_markdown: string;
  slug?: string | null;
  author_display_name?: string | null;
  author_role?: string | null;
  author_initials?: string | null;
  submit_for_review?: boolean;
}

export interface ArticleUpdateInput {
  title?: string;
  summary?: string | null;
  category?: string;
  content_markdown?: string;
  cover_image_url?: string | null;
  submit_for_review?: boolean;
}

export interface ArticleReviewInput {
  action: "approve" | "request_changes" | "unpublish" | "archive";
  reviewer_feedback?: string | null;
  featured_order?: number | null;
}

export type SponsorTier = "client" | "partner" | "supporter" | "academic";

export interface Sponsor {
  id: string;
  name: string;
  logo_url: string;
  website_url: string | null;
  tier: SponsorTier;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SponsorCreateInput {
  name: string;
  logo_url: string;
  website_url?: string | null;
  tier: SponsorTier;
  display_order?: number;
  is_active?: boolean;
}

export interface SponsorUpdateInput {
  name?: string;
  logo_url?: string;
  website_url?: string | null;
  tier?: SponsorTier;
  display_order?: number;
  is_active?: boolean;
}

export interface MediaClipping {
  id: string;
  publisher_name: string;
  article_title: string;
  article_url: string;
  published_date: string;
  logo_url: string | null;
  is_arabic: boolean;
  snippet: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MediaClippingCreateInput {
  publisher_name: string;
  article_title: string;
  article_url: string;
  published_date: string;
  logo_url?: string | null;
  is_arabic?: boolean;
  snippet?: string | null;
  display_order?: number;
  is_active?: boolean;
}

export interface MediaClippingUpdateInput {
  publisher_name?: string;
  article_title?: string;
  article_url?: string;
  published_date?: string;
  logo_url?: string | null;
  is_arabic?: boolean;
  snippet?: string | null;
  display_order?: number;
  is_active?: boolean;
}

export interface StudentMission {
  id: string;
  student_name: string;
  project_title: string;
  category: string;
  description: string;
  docx_url: string | null;
  photo_url: string | null;
  metrics_json: Record<string, any>;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StudentMissionCreateInput {
  student_name: string;
  project_title: string;
  category: string;
  description: string;
  docx_url?: string | null;
  photo_url?: string | null;
  metrics_json?: Record<string, any>;
  display_order?: number;
  is_active?: boolean;
}

export interface StudentMissionUpdateInput {
  student_name?: string;
  project_title?: string;
  category?: string;
  description?: string;
  docx_url?: string | null;
  photo_url?: string | null;
  metrics_json?: Record<string, any>;
  display_order?: number;
  is_active?: boolean;
}

export type WebsiteLeadType = "workshop_booking" | "newsletter" | "inquiry";
export type WebsiteLeadStatus = "new" | "contacted" | "converted" | "archived";

export interface WebsiteLead {
  id: string;
  lead_type: WebsiteLeadType;
  contact_name: string | null;
  email: string;
  phone: string | null;
  organization_name: string | null;
  program_interest: string | null;
  details: Record<string, any>;
  status: WebsiteLeadStatus;
  created_at: string;
  updated_at: string;
}
