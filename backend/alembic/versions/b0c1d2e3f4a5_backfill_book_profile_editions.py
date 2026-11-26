"""Backfill bundle manifest profiles into global SpacePoint lms_book_editions rows.

Revision ID: b0c1d2e3f4a5
Revises: a9b8c7d6e5f4
Create Date: 2026-11-26 16:22:00.000000
"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "lms_books" not in tables or "lms_book_editions" not in tables:
        return

    books = bind.execute(sa.text("SELECT id, created_by, profiles FROM lms_books")).mappings().all()
    for b in books:
        profiles = b.get("profiles") or []
        if not isinstance(profiles, list):
            continue
        existing = bind.execute(
            sa.text(
                "SELECT title, chapter_keys FROM lms_book_editions "
                "WHERE book_id = :book_id AND organization_id IS NULL"
            ),
            {"book_id": b["id"]},
        ).mappings().all()
        seen_titles = {str(r["title"] or "").strip().lower() for r in existing}
        seen_slices = {tuple(str(k) for k in (r["chapter_keys"] or [])) for r in existing}

        for prof in profiles:
            if not isinstance(prof, dict):
                continue
            groups = [str(k).strip() for k in (prof.get("groups") or []) if str(k or "").strip()]
            if not groups:
                continue
            title = str(prof.get("label_en") or prof.get("key") or "Edition").strip()[:200]
            if not title or title.lower() in seen_titles or tuple(groups) in seen_slices:
                continue
            title_ar = str(prof.get("label_ar")).strip()[:200] if prof.get("label_ar") else None
            default_lang = str(prof.get("default_lang")).strip()[:8] if prof.get("default_lang") else None
            desc = str(prof.get("subtitle_en")).strip() if prof.get("subtitle_en") else None
            bind.execute(
                sa.text(
                    "INSERT INTO lms_book_editions "
                    "(id, book_id, organization_id, created_by, title, title_ar, description, chapter_keys, default_lang, created_at, updated_at) "
                    "VALUES (:id, :book_id, NULL, :created_by, :title, :title_ar, :description, CAST(:chapter_keys AS jsonb), :default_lang, NOW(), NOW())"
                ),
                {
                    "id": uuid.uuid4(),
                    "book_id": b["id"],
                    "created_by": b["created_by"],
                    "title": title,
                    "title_ar": title_ar,
                    "description": desc,
                    "chapter_keys": json.dumps(groups),
                    "default_lang": default_lang,
                },
            )
            seen_titles.add(title.lower())
            seen_slices.add(tuple(groups))


def downgrade() -> None:
    # Data backfill only; leave user/staff editions intact.
    pass
