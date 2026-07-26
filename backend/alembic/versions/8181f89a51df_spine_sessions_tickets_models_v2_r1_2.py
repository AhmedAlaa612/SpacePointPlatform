"""spine + sessions + tickets models (V2 R1-2)

Autogenerate also picked up a large amount of pre-existing drift between the
SQL-first baseline and current models (TEXT->String type mismatches, idx_->ix_
index renames, two orphaned tables with no models) — none of that belongs in
this revision, so it was stripped out by hand; only the new spine/sessions
tables below are genuinely part of R1-2. Autogenerate also inlined the two
use_alter=True foreign keys (contacts<->touchpoints, organizations<->contacts)
directly into their CREATE TABLE statements in an order that would fail at
runtime (contacts was placed before touchpoints despite depending on it) —
those two constraints are added via explicit create_foreign_key calls after
every table exists instead. Two column widths were also widened past what the
V1/V2 spec text literally stated, because the spec's own listed enum values
don't fit its own stated VARCHAR length: cohorts.status VARCHAR(16)->(24)
('registration_open' is 17 chars) and identity_aliases.alias_type
VARCHAR(24)->(32) ('legacy_inventory_instructor' is 27 chars).

Revision ID: 8181f89a51df
Revises: b2d8a91c0002
Create Date: 2026-07-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8181f89a51df'
down_revision: Union[str, None] = 'b2d8a91c0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── spine ────────────────────────────────────────────────────────────────
    op.create_table('organizations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name_latin', sa.String(length=255), nullable=False),
        sa.Column('name_arabic', sa.String(length=255), nullable=True),
        sa.Column('org_type', sa.String(length=24), nullable=False),
        sa.Column('country', sa.String(length=64), nullable=True),
        sa.Column('city', sa.String(length=64), nullable=True),
        sa.Column('primary_contact_id', sa.UUID(), nullable=True),  # FK added below, once contacts exists
        sa.Column('owner_user_id', sa.UUID(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('contacts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('full_name_latin', sa.String(length=255), nullable=False),
        sa.Column('full_name_arabic', sa.String(length=255), nullable=True),
        sa.Column('contact_roles', postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column('primary_phone_e164', sa.String(length=20), nullable=True),
        sa.Column('whatsapp_e164', sa.String(length=20), nullable=True),
        sa.Column('secondary_phones', postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('preferred_language', sa.String(length=8), nullable=False),
        sa.Column('country', sa.String(length=64), nullable=True),
        sa.Column('city', sa.String(length=64), nullable=True),
        sa.Column('date_of_birth', sa.Date(), nullable=True),
        sa.Column('age_band', sa.String(length=16), nullable=True),
        sa.Column('is_minor', sa.Boolean(), nullable=False),
        sa.Column('lifecycle_stage', sa.String(length=24), nullable=False),
        sa.Column('owner_user_id', sa.UUID(), nullable=True),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.Column('source_touchpoint_id', sa.UUID(), nullable=True),  # FK added below, once touchpoints exists
        sa.Column('merged_into_id', sa.UUID(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['merged_into_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contacts_contact_roles', 'contacts', ['contact_roles'], unique=False, postgresql_using='gin')
    op.create_index('ix_contacts_email', 'contacts', ['email'], unique=False)
    op.create_index('ix_contacts_primary_phone_e164', 'contacts', ['primary_phone_e164'], unique=False)
    op.create_index('ix_contacts_whatsapp_e164', 'contacts', ['whatsapp_e164'], unique=False)

    op.create_table('touchpoints',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('contact_id', sa.UUID(), nullable=True),
        sa.Column('channel', sa.String(length=24), nullable=False),
        sa.Column('touchpoint_type', sa.String(length=32), nullable=False),
        sa.Column('direction', sa.String(length=8), nullable=True),
        sa.Column('campaign_id', sa.UUID(), nullable=True),
        sa.Column('content_item_id', sa.UUID(), nullable=True),
        sa.Column('utm_source', sa.String(length=128), nullable=True),
        sa.Column('utm_medium', sa.String(length=128), nullable=True),
        sa.Column('utm_campaign', sa.String(length=128), nullable=True),
        sa.Column('utm_content', sa.String(length=128), nullable=True),
        sa.Column('utm_term', sa.String(length=128), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_platform_id', sa.String(length=256), nullable=True),
        sa.Column('raw_payload_ref', sa.String(length=512), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_touchpoints_contact_occurred', 'touchpoints', ['contact_id', 'occurred_at'], unique=False)
    op.create_index(
        'uq_touchpoints_channel_raw_platform_id', 'touchpoints', ['channel', 'raw_platform_id'],
        unique=True, postgresql_where=sa.text('raw_platform_id IS NOT NULL'),
    )

    # Both sides of the two circular references now exist — add the deferred FKs.
    op.create_foreign_key(
        'fk_organizations_primary_contact_id', 'organizations', 'contacts',
        ['primary_contact_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_contacts_source_touchpoint_id', 'contacts', 'touchpoints',
        ['source_touchpoint_id'], ['id'], ondelete='SET NULL',
    )

    op.create_table('contact_relationships',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('contact_id', sa.UUID(), nullable=False),
        sa.Column('related_contact_id', sa.UUID(), nullable=False),
        sa.Column('relation', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['related_contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contact_id', 'related_contact_id', 'relation', name='uq_contact_relationship'),
    )

    op.create_table('consent_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('contact_id', sa.UUID(), nullable=False),
        sa.Column('consent_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('withdrawn_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('jurisdiction', sa.String(length=8), nullable=True),
        sa.Column('guardian_contact_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['guardian_contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_consent_records_contact_type', 'consent_records', ['contact_id', 'consent_type'], unique=False)

    op.create_table('identity_aliases',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('contact_id', sa.UUID(), nullable=False),
        sa.Column('alias_type', sa.String(length=32), nullable=False),
        sa.Column('alias_value_hash', sa.String(length=64), nullable=False),
        sa.Column('alias_value_plain', sa.String(length=256), nullable=True),
        sa.Column('matched_by', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alias_type', 'alias_value_hash', name='uq_identity_alias_type_hash'),
    )

    op.create_table('merge_reviews',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('candidate_a', sa.UUID(), nullable=False),
        sa.Column('candidate_b', sa.UUID(), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['candidate_a'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['candidate_b'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── sessions ─────────────────────────────────────────────────────────────
    op.create_table('programs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('program_type', sa.String(length=24), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('pricing_model', sa.String(length=24), nullable=False),
        sa.Column('default_capacity', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )

    op.create_table('cohorts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('program_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('starts_on', sa.Date(), nullable=True),
        sa.Column('ends_on', sa.Date(), nullable=True),
        sa.Column('location', sa.String(length=128), nullable=True),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('lead_instructor_user_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('staffing_status', sa.String(length=16), nullable=False),
        sa.Column('madar_invitation_batch', sa.String(length=64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.Column('visibility', sa.String(length=12), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['lead_instructor_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('cohort_instructors',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('cohort_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cohort_id', 'user_id', name='uq_cohort_instructor'),
    )

    op.create_table('session_meetings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('cohort_id', sa.UUID(), nullable=False),
        sa.Column('meeting_date', sa.Date(), nullable=False),
        sa.Column('starts_at', sa.Time(), nullable=True),
        sa.Column('topic', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cohort_id', 'meeting_date', 'starts_at', name='uq_session_meeting_slot'),
    )

    op.create_table('import_batches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.Column('cohort_id', sa.UUID(), nullable=True),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('counts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('registrations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('contact_id', sa.UUID(), nullable=False),
        sa.Column('payer_contact_id', sa.UUID(), nullable=True),
        sa.Column('cohort_id', sa.UUID(), nullable=False),
        sa.Column('price_charged', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('payment_status', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('source_campaign_id', sa.UUID(), nullable=True),
        sa.Column('source_touchpoint_id', sa.UUID(), nullable=True),
        sa.Column('is_repeat', sa.Boolean(), nullable=False),
        sa.Column('ticket_token', sa.String(length=64), nullable=False),
        sa.Column('ticket_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('registered_via', sa.String(length=16), nullable=False),
        sa.Column('import_batch_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['import_batch_id'], ['import_batches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['payer_contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_touchpoint_id'], ['touchpoints.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contact_id', 'cohort_id', name='uq_registration_contact_cohort'),
        sa.UniqueConstraint('ticket_token'),
    )

    op.create_table('attendance_records',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('registration_id', sa.UUID(), nullable=False),
        sa.Column('session_meeting_id', sa.UUID(), nullable=False),
        sa.Column('att_status', sa.String(length=12), nullable=False),
        sa.Column('method', sa.String(length=8), nullable=False),
        sa.Column('recorded_by_user_id', sa.UUID(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['registration_id'], ['registrations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_meeting_id'], ['session_meetings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('registration_id', 'session_meeting_id', name='uq_attendance_registration_meeting'),
    )

    op.create_table('instructor_interests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('cohort_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cohort_id', 'user_id', name='uq_instructor_interest'),
    )

    op.create_table('session_reports',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('cohort_id', sa.UUID(), nullable=False),
        sa.Column('session_meeting_id', sa.UUID(), nullable=True),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('file_ref', sa.String(length=512), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_meeting_id'], ['session_meetings.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── activities (quiz schema — engine lands week 13-14) ──────────────────
    op.create_table('activities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('activity_type', sa.String(length=16), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('activity_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('activity_id', sa.UUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('definition', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('activity_id', 'version', name='uq_activity_version'),
    )

    op.create_table('activity_assignments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('activity_version_id', sa.UUID(), nullable=False),
        sa.Column('program_id', sa.UUID(), nullable=True),
        sa.Column('cohort_id', sa.UUID(), nullable=True),
        sa.Column('assigned_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('(program_id IS NULL) != (cohort_id IS NULL)', name='ck_activity_assignment_exactly_one_target'),
        sa.ForeignKeyConstraint(['activity_version_id'], ['activity_versions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('activity_assignments')
    op.drop_table('activity_versions')
    op.drop_table('activities')

    op.drop_table('session_reports')
    op.drop_table('instructor_interests')
    op.drop_table('attendance_records')
    op.drop_table('registrations')
    op.drop_table('import_batches')
    op.drop_table('session_meetings')
    op.drop_table('cohort_instructors')
    op.drop_table('cohorts')
    op.drop_table('programs')

    op.drop_table('merge_reviews')
    op.drop_table('identity_aliases')
    op.drop_table('consent_records')
    op.drop_table('contact_relationships')

    # Drop the two circular FKs before their target tables so nothing dangling remains.
    op.drop_constraint('fk_contacts_source_touchpoint_id', 'contacts', type_='foreignkey')
    op.drop_constraint('fk_organizations_primary_contact_id', 'organizations', type_='foreignkey')

    op.drop_index('uq_touchpoints_channel_raw_platform_id', table_name='touchpoints')
    op.drop_index('ix_touchpoints_contact_occurred', table_name='touchpoints')
    op.drop_table('touchpoints')

    op.drop_index('ix_contacts_whatsapp_e164', table_name='contacts')
    op.drop_index('ix_contacts_primary_phone_e164', table_name='contacts')
    op.drop_index('ix_contacts_email', table_name='contacts')
    op.drop_index('ix_contacts_contact_roles', table_name='contacts')
    op.drop_table('contacts')

    op.drop_table('organizations')
