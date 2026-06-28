-- 0008 — explicit document-template render type (letter | certificate) + system flag.
-- Replaces the old "infer the document type from substrings in the template key" logic.
-- Safe to run once on the live Supabase project (mirrors the startup migration).

ALTER TABLE document_templates
  ADD COLUMN IF NOT EXISTS type      VARCHAR(20) NOT NULL DEFAULT 'letter',
  ADD COLUMN IF NOT EXISTS is_system BOOLEAN     NOT NULL DEFAULT FALSE;

-- existing certificate templates: anything with a base image or a cert-ish key
UPDATE document_templates
   SET type = 'certificate'
 WHERE type <> 'certificate'
   AND (template_file_url IS NOT NULL OR key ILIKE '%certificate%');

-- workshop-delivery certificate: its text used to be hardcoded in
-- services/documents/certificate.py; now it's an editable, non-deletable system
-- template, auto-used when an instructor signs a payment letter.
INSERT INTO document_templates (id, key, name, type, is_system, roles, body_text)
SELECT gen_random_uuid(), 'workshop_delivery', 'Workshop Facilitation Certificate',
       'certificate', TRUE, ARRAY[]::varchar[],
       'in recognition of his/her outstanding contribution as a facilitator to the <b>{workshop_name}</b>, delivered on <b>{workshop_date}</b> at <b>{location}</b>'
WHERE NOT EXISTS (SELECT 1 FROM document_templates WHERE key = 'workshop_delivery');
