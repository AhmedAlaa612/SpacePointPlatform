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
# Paste-friendly: no tabs, no variable word-splitting. Run on the VPS as
# root using the usual invocation (peer auth over the Unix socket):
#   bash /tmp/explore_org_mess.sh
#
set -u

run() {
  echo "--- $1"
  sudo -u postgres psql -P pager=off spacepoint_unified -c "$2" 2>&1
  echo ""
}

echo "=================================================================="
echo " ORG/CONTACT MESS EXPLORER (read-only)"
echo "=================================================================="
echo ""

run "0. alembic version" \
"SELECT version_num FROM alembic_version;"

run "1. counts users/contacts/orgs/id_cards" \
"SELECT 'users=' || (SELECT count(*) FROM users) || ' contacts=' || (SELECT count(*) FROM contacts) || ' orgs=' || (SELECT count(*) FROM organizations) || ' id_cards=' || (SELECT count(*) FROM id_cards);"

run "2. orgs partner-vs-school by org_type" \
"SELECT coalesce(org_type,'(null)') || ' linked=' || count(*) FILTER (WHERE owner_user_id IS NOT NULL) || ' unlinked=' || count(*) FILTER (WHERE owner_user_id IS NULL) || ' total=' || count(*) FROM organizations GROUP BY 1 ORDER BY 1;"

run "3. duplicate org names" \
"SELECT lower(name_latin) || ' rows=' || count(*) || ' linked=' || count(*) FILTER (WHERE owner_user_id IS NOT NULL) || ' ids=' || string_agg(left(id::text,8),',') FROM organizations GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC;"

run "4. contacts wrongly on partner orgs (100)" \
"SELECT c.full_name || ' ' || coalesce(c.email,'(noemail)') || ' roles=' || coalesce(c.contact_roles::text,'(none)') || ' partner=' || o.name_latin FROM contacts c JOIN organizations o ON o.id = c.organization_id WHERE o.owner_user_id IS NOT NULL ORDER BY 1 LIMIT 100;"

run "4b. full count of 4" \
"SELECT count(*) FROM contacts c JOIN organizations o ON o.id = c.organization_id WHERE o.owner_user_id IS NOT NULL;"

run "5. those contacts user accounts" \
"SELECT u.full_name || ' ' || u.email || ' uroles=' || u.roles::text || ' contact=' || c.full_name || ' partner=' || o.name_latin FROM contacts c JOIN organizations o ON o.id = c.organization_id JOIN users u ON u.contact_id = c.id WHERE o.owner_user_id IS NOT NULL ORDER BY 1 LIMIT 100;"

run "6. users holding organization role" \
"SELECT u.email || ' roles=' || u.roles::text || ' card=' || coalesce(u.card_number::text,'(null)') || ' display=' || CASE WHEN u.card_number IS NULL THEN '(none)' WHEN u.roles = ARRAY['organization'::user_role] THEN 'SP-ORG-' || lpad(u.card_number::text,4,'0') || '-UAE' WHEN 'student'::user_role = ANY(u.roles) THEN 'SP-ST-' || lpad(u.card_number::text,4,'0') || '-UAE' ELSE 'SP-' || lpad(u.card_number::text,4,'0') || '-UAE' END FROM users u WHERE 'organization'::user_role = ANY(u.roles) ORDER BY 1;"

run "7. junk org names" \
"SELECT left(id::text,8) || ' linked=' || CASE WHEN owner_user_id IS NULL THEN 'no' ELSE 'yes' END || ' ' || name_latin FROM organizations WHERE name_latin ILIKE '%different%' OR name_latin LIKE '%(%' OR char_length(name_latin) > 60 ORDER BY 1 LIMIT 50;"

run "8. students with school link count" \
"SELECT count(*) FROM users u JOIN contacts c ON c.id = u.contact_id WHERE 'student'::user_role = ANY(u.roles) AND c.organization_id IS NOT NULL;"

run "8b. sample of 8" \
"SELECT u.full_name || ' ' || u.email || ' school=' || o.name_latin || ' schoollogin=' || CASE WHEN o.owner_user_id IS NULL THEN 'no' ELSE 'YES-partner' END FROM users u JOIN contacts c ON c.id = u.contact_id JOIN organizations o ON o.id = c.organization_id WHERE 'student'::user_role = ANY(u.roles) AND c.organization_id IS NOT NULL ORDER BY 1 LIMIT 30;"

run "9. orphans (expect 0/0/0)" \
"SELECT 'c_orph=' || (SELECT count(*) FROM contacts c LEFT JOIN organizations o ON o.id=c.organization_id WHERE c.organization_id IS NOT NULL AND o.id IS NULL) || ' o_orph=' || (SELECT count(*) FROM organizations o LEFT JOIN users u ON u.id=o.owner_user_id WHERE o.owner_user_id IS NOT NULL AND u.id IS NULL) || ' u_orph=' || (SELECT count(*) FROM users u LEFT JOIN contacts c ON c.id=u.contact_id WHERE u.contact_id IS NOT NULL AND c.id IS NULL);"

run "10. orgs hosting website events" \
"SELECT o.name_latin || ' login=' || CASE WHEN o.owner_user_id IS NULL THEN 'no' ELSE 'yes' END || ' events=' || count(e.id) FROM organizations o JOIN website_events e ON e.organization_id = o.id GROUP BY o.id, o.name_latin, o.owner_user_id ORDER BY 1 LIMIT 50;"

run "11. stored id_cards for pure-org users" \
"SELECT u.email || ' stored=' || coalesce(i.card_id,'(null)') || ' role=' || i.role::text FROM id_cards i JOIN users u ON u.id = i.user_id WHERE u.roles = ARRAY['organization'::user_role] ORDER BY 1 LIMIT 50;"

echo "DONE - no writes were made."
