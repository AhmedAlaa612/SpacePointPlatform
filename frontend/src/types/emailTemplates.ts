// Email Templates System — every system email, editable + pausable.

export interface EmailTemplate {
  id: string
  key: string
  name: string
  category: string
  description: string
  subject: string
  body_html: string
  placeholders: string[]
  attachment_labels: string[]
  is_paused: boolean
  is_internal: boolean
  updated_at?: string | null
}

export interface EmailTemplatePreview {
  subject: string
  body_html: string
}
