#!/usr/bin/env bash
#
# explore_org_mess.sh — READ-ONLY exploration of the organizations/contacts
# cross-contamination on the live VPS.
#
# Context: the shared `organizations` table holds BOTH auto-created school
# rows (owner_user_id IS NULL, from imports/registrations) AND partner org
# accounts (owner_user_id set, event-host logins). Intake school matching
# used to latch contacts onto partner rows on same-name hits (fixed in
# app/services/spine/identity.py, 2026-10 — but old bad links remain).
#
# This script changes NOTHING — every statement is a SELECT. Safe to run
# any time, even mid-deploy.
#
# Run on the VPS as root (per docs/HANDOFF_VPS_DEPLOYMENT.md §2, Postgres 16
# on 5432 uses peer auth — no password needed):
#   curl -sSL https://raw.githubusercontent.com/AhmedAlaa612/SpacePointPlatform/main/ops/explore_org_mess.sh -o /tmp/explore_org_mess.sh \
#     && bash /tmp/explore_org_mess.sh
#   # ...or pipe straight through: curl -sSL <url> | bash
#
set -u

PSQL="psql -d spacepoint_unified -X -q -t -A -F	"
# NOTE: no -h flag on purpose — Unix socket + `sudo -u postgres` = peer auth,
# no password. Adding `-h 127.0.0.1` forces TCP/md5 and prompts for one.

q() {
  echo "── $1"
  shift
  # shellcheck disable=SC2086
  sudo -u postgres $PSQL -c "$*" 2>&1
  echo ""
}

echo "================================================================"
echo " ORG/CONTACT MESS EXPLORER (read-only) — $(date -u +%FT%TZ)"
echo "================================================================"
echo ""

q "0. alembic version on this DB" \
  "SELECT version_num FROM alembic_version;"

q "1. table counts (users / contacts / organizations / id_cards)" \
  "SELECT 'users=' || (SELECT count(*) FROM users) \
      || ' contacts=' || (SELECT count(*) FROM contacts) \
      || ' orgs=' || (SELECT count(*) FROM organizations) \
      || ' id_cards=' || (SELECT count(*) FROM id_cards);"

q "2. organizations: partner (login linked) vs plain school rows, by org_type" \
  "SELECT coalesce(org_type,'(null)') || ' | linked=' || count(*) FILTER (WHERE owner_user_id IS NOT NULL) \
      || ' | unlinked=' || count(*) FILTER (WHERE owner_user_id IS NULL) \
      || ' | total=' || count(*) \
   FROM organizations GROUP BY 1 ORDER BY 1;"

q "3. duplicate org names (case-insensitive) — the collision surface" \
  "SELECT lower(name_latin) || ' | rows=' || count(*) \
      || ' | linked=' || count(*) FILTER (WHERE owner_user_id IS NOT NULL) \
      || ' | ids=' || string_agg(left(id::text,8), ',' ORDER BY name_latin) \
   FROM organizations GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC;"

q "4. CONTACTS WRONGLY LINKED TO PARTNER ORGS (contact.organization_id -> org with login)" \
  "SELECT c.full_name || ' | ' || coalesce(c.email,'(no email)') \
      || ' | contact_roles=' || coalesce(array_to_string(c.contact_roles::text[],','),'(none)') \
      || ' | linked_partner_org=' || o.name_latin \
   FROM contacts c JOIN organizations o ON o.id = c.organization_id \
   WHERE o.owner_user_id IS NOT NULL ORDER BY 1 LIMIT 100;"

q "4b. count of 4. (full, not just 100 shown)" \
  "SELECT count(*) FROM contacts c JOIN organizations o ON o.id = c.organization_id \
   WHERE o.owner_user_id IS NOT NULL;"

q "5. partner-linked contacts that ALSO have a user account (roles?)" \
  "SELECT u.full_name || ' | ' || u.email || ' | user_roles=' || array_to_string(u.roles::text[],',') \
      || ' | contact=' || c.full_name || ' | partner_org=' || o.name_latin \
   FROM contacts c JOIN organizations o ON o.id = c.organization_id \
   JOIN users u ON u.contact_id = c.id \
   WHERE o.owner_user_id IS NOT NULL ORDER BY 1 LIMIT 100;"

q "6. users holding the organization role (account, roles, card)" \
  "SELECT u.email || ' | roles=' || array_to_string(u.roles::text[],',') \
      || ' | card_number=' || coalesce(u.card_number::text,'(null)') \
      || ' | display=' || CASE \
           WHEN u.card_number IS NULL THEN '(none)' \
           WHEN u.roles = ARRAY['organization'::user_role] THEN 'SP-ORG-' || lpad(u.card_number::text,4,'0') || '-UAE' \
           WHEN 'student'::user_role = ANY(u.roles) THEN 'SP-ST-' || lpad(u.card_number::text,4,'0') || '-UAE' \
           ELSE 'SP-' || lpad(u.card_number::text,4,'0') || '-UAE' END \
   FROM users u WHERE 'organization'::user_role = ANY(u.roles) ORDER BY 1;"

q "7. suspect junk org names (likely import garbage: parens / 'different' / 60+ chars)" \
  "SELECT left(id::text,8) || ' | linked=' || coalesce(owner_user_id::text,'no') || ' | ' || name_latin \
   FROM organizations \
   WHERE name_latin ILIKE '%different%' OR name_latin LIKE '%(%' OR char_length(name_latin) > 60 \
   ORDER BY 1 LIMIT 50;"

q "8. students carrying a school link (population that leaked into the old Organizations tab)" \
  "SELECT count(*) FROM users u JOIN contacts c ON c.id = u.contact_id \
   WHERE 'student'::user_role = ANY(u.roles) AND c.organization_id IS NOT NULL;"

q "8b. sample of 8. (student | school | school login?)" \
  "SELECT u.full_name || ' | ' || u.email || ' | school=' || o.name_latin \
      || ' | school_has_login=' || CASE WHEN o.owner_user_id IS NULL THEN 'no' ELSE 'YES-linked-to-partner' END \
   FROM users u JOIN contacts c ON c.id = u.contact_id \
   JOIN organizations o ON o.id = c.organization_id \
   WHERE 'student'::user_role = ANY(u.roles) AND c.organization_id IS NOT NULL \
   ORDER BY 1 LIMIT 30;"

q "9. orphan checks (all should be 0: contact->org / org->owner / user->contact)" \
  "SELECT 'contacts_orphan_org=' || (SELECT count(*) FROM contacts c LEFT JOIN organizations o ON o.id=c.organization_id WHERE c.organization_id IS NOT NULL AND o.id IS NULL) \
      || ' orgs_orphan_owner=' || (SELECT count(*) FROM organizations o LEFT JOIN users u ON u.id=o.owner_user_id WHERE o.owner_user_id IS NOT NULL AND u.id IS NULL) \
      || ' users_orphan_contact=' || (SELECT count(*) FROM users u LEFT JOIN contacts c ON c.id=u.contact_id WHERE u.contact_id IS NOT NULL AND c.id IS NULL);"

q "10. partner orgs actually hosting website events (org | events)" \
  "SELECT o.name_latin || ' | login=' || CASE WHEN o.owner_user_id IS NULL THEN 'no' ELSE 'yes' END \
      || ' | events=' || count(e.id) \
   FROM organizations o JOIN website_events e ON e.organization_id = o.id \
   GROUP BY o.id, o.name_latin, o.owner_user_id ORDER BY 1 LIMIT 50;"

q "11. stored id_cards strings for pure-org users (stale SP- prefix shows here until next card view rewrites it)" \
  "SELECT u.email || ' | stored=' || coalesce(i.card_id,'(null)') || ' | role=' || i.role::text \
   FROM id_cards i JOIN users u ON u.id = i.user_id \
   WHERE u.roles = ARRAY['organization'::user_role] ORDER BY 1 LIMIT 50;"

echo "DONE — no writes were made."
