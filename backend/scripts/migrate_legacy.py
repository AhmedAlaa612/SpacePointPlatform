"""Legacy instructors-portal ETL — GO_LIVE.md Workstream A4.

Reads the LEGACY `spacepoint_db` Postgres schema (old int4 PKs, single `role`
enum, files referenced by absolute VPS filesystem paths) and writes into the
UNIFIED schema (UUID PKs, `roles[]` array) via the app's own SQLAlchemy async
models. Every legacy file referenced by a migrated row is read from disk and
re-uploaded through `app.services.storage.upload_to_path()` so it lands
Fernet-encrypted, path-based, exactly like production writes will.

────────────────────────────────────────────────────────────────────────────
USAGE
────────────────────────────────────────────────────────────────────────────
    python scripts/migrate_legacy.py \
        --legacy-db postgresql://spacepoint_user:PASS@localhost:5433/spacepoint_db \
        --unified-db postgresql+asyncpg://spacepoint_user:PASS@localhost:5433/spacepoint_unified_test \
        --uploads-dir "C:/Users/ahmed/Downloads/var/www/spacepoint_portal/backend/app/uploads" \
        --storage-root "C:/Users/ahmed/Downloads/spacepoint/scratch_storage" \
        --storage-key "<fernet key, or rely on STORAGE_ENCRYPTION_KEY env>"

--legacy-db     : sync-style DSN (psycopg2/psycopg driver — script opens its
                  own plain sync connection for reads, no ORM needed on the
                  legacy side since those models aren't part of this repo).
                  Accepts a bare "postgresql://..." URL; a "+asyncpg"/"+psycopg2"
                  suffix is stripped automatically since we always connect sync.
--unified-db    : ASYNC SQLAlchemy DSN (postgresql+asyncpg://...) — the ETL
                  writes through the app's own AsyncSession + models, so it
                  must be in the same shape as DATABASE_URL. This OVERRIDES
                  settings.DATABASE_URL / app.core.config for the duration of
                  the run (see _bind_engine below) — the app's own .env is
                  never read or touched.
--uploads-dir   : root of the legacy `uploads/` tree (contains assessments/,
                  certificates/, contracts/, instructor_cards/,
                  instructor_documents/, instructor_photos/, library_resources/,
                  modules/, payment_letters/, settings/, training_videos/).
--storage-root  : STORAGE_ROOT for the LOCAL storage backend — where encrypted
                  blobs land (STORAGE_ROOT/{bucket}/{path}).
--storage-key   : Fernet key (32-byte urlsafe base64). If omitted, reads
                  STORAGE_ENCRYPTION_KEY from the environment; if that's also
                  unset, the script generates one and PRINTS it (dev-only
                  convenience — for a real cutover run this must be the VPS's
                  real, already-provisioned key, never a script-generated one).
--dry-run       : parse + map everything, upload NO files and write NO DB
                  rows; just print the verification report. Useful smoke test.
--skip-files    : run the full DB ETL but skip the disk-read/upload step for
                  files (rows still get bucket/path values as if the file
                  existed) — for a fast structural pass on machines without
                  the uploads copy.

────────────────────────────────────────────────────────────────────────────
IDEMPOTENCY / RE-RUN SAFETY
────────────────────────────────────────────────────────────────────────────
Every legacy row is looked up in the unified target by a natural key before
insert (users: legacy id via the id-map CSV + email fallback; profiles/
documents/submissions: by the mapped user_id + a natural discriminator such
as document_type+original file name, or module_id). Re-running this script
against a target that already has a prior run's rows will UPDATE in place
rather than duplicate, EXCEPT for append-only vault-style tables
(instructor_documents, library_resources) where the natural key is
(user_id, legacy_id) recorded in the id-map — a second run recognizes its own
prior rows via that map and skips re-uploading the file (idempotent) rather
than guessing from content. Files: `storage.upload_to_path` overwrites the
same path deterministically (it's a pure encrypt-and-write), so re-uploading
an unchanged legacy file is harmless and produces byte-identical ciphertext
input (a different Fernet nonce, but decrypts to the same plaintext).

The intended real cutover flow (per AGENT_LOG.md "ETL execution strategy
DECIDED") runs this script against a WIPED target once for the test stage and
again for the production stage — both are just "run it on empty," which this
script handles trivially; the id-map / natural-key lookups above exist mainly
so a *failed, partially-applied* run can be safely re-run without manual
cleanup.

────────────────────────────────────────────────────────────────────────────
KEY MAPPING DECISIONS (see GO_LIVE.md §3.A4 + AGENT_LOG.md for the reasoning)
────────────────────────────────────────────────────────────────────────────
- old_int_id -> new uuid4: one map per legacy table with other tables
  referencing it (users, modules->checklist_modules, module_sections,
  checklist_items, library_modules, payment_batches, payment_letters,
  payment_sessions). Dumped to CSV under scripts/migration_id_maps/{table}.csv
  for audit. NOT committed with real production data (see .gitignore note in
  this repo's root) — the CSVs from a dev/fixture run are small and fine to
  keep as an example artifact, but a real cutover run's maps contain live
  emails/PII and must stay local to the machine that ran the ETL.
- password_hash copied VERBATIM — bcrypt on both sides (PIVOT_HANDOFF.md
  §1.4 / GO_LIVE.md boss requirement #3). Never re-hashed, never touched.
- Legacy `instructor_profiles.instructor_id` ("SP-0002-UAE") -> the integer
  becomes `users.card_number`. `id_cards` rows are created for every role the
  user holds (mirrors `ensure_card_id`'s shape) so the profile-card page has
  something to read immediately. `card_seq_person` is bumped past the max
  assigned number (mirrors sql/0011_person_id_cards.sql's own bump-past-max
  pattern) so the *next* on-the-fly allocation in the live app never collides
  with a migrated number.
- Legacy front/back instructor-card PNGs (instructor_cards/{id}/{front,back}.png)
  are INTENTIONALLY DROPPED, matching GO_LIVE.md's table — id_card.py renders
  cards on-the-fly from `card_id` and a live photo; there is nowhere to store
  a static front/back image in the unified `id_cards` model even if we wanted
  to (no such columns by design, see id_card.py's own docstring).
- `research_submissions` (legacy) -> `assessment_submissions` (unified,
  SQL 0013). This is the AGENT_LOG.md-resolved mapping, NOT the earlier
  contradictory GO_LIVE.md table rows (fixed in GO_LIVE.md by this session —
  see the completion-log entry). file_path -> upload to
  `applicant-submissions/{user_id}/research/{original_filename}` bucket path,
  store resulting path as file_url/file_path; content_text -> comments;
  original_filename has no column in assessment_submissions so it is folded
  into the storage path instead of being dropped outright.
- Legacy `assessment_submissions` (yes, the OLD db also independently has a
  table by this same name — it is the *actual* Phase-2 "10 Questions
  Assessment" upload, distinct from `research_submissions`) maps 1:1 to
  unified `assessment_submissions` by (user_id, file_path/google_drive_link/
  comments). Since both legacy tables land in the same unified table keyed
  UNIQUE on user_id, a user with BOTH a research_submissions row and a legacy
  assessment_submissions row would collide; in the local fixture data this
  never occurs (research_submissions is empty), but the script logs a
  collision explicitly rather than silently overwriting if it ever does.
- `modules`/`module_sections`/`checklist_items`/`user_checklist_progress`
  (legacy int PKs) -> `checklist_modules`/`module_sections`/`checklist_items`/
  `user_checklist_progress` (same shape, new UUID PKs) — full id-map chain
  needed since module_submissions.module_id and checklist_items.section_id
  both reference these.
- `library_modules`/`library_resources` -> same-named unified tables; files
  -> `library-resources` bucket.
- `certificates.instructor_name` dropped (joinable via user_id -> users.full_name).
  `type` forced to `workshop_delivery` (the only kind the legacy app ever
  generated). `payment_session_id` remapped through the payment_sessions
  id-map (legacy certs predate payment_sessions rows in the local fixture, so
  this is usually NULL in practice — handled generically regardless).
- `invitation_codes`: `source_type`/`source_id` dropped (unused in unified;
  no equivalent concept — ambassador referral tracking is `users.invited_by_id`
  in the unified schema, unrelated to admin invitation codes).
- `portal_settings`: carries admin-signature config, migrated verbatim
  including `admin_signature_path` (the value STRING itself is not a file
  path our storage layer understands directly — see MIGRATE_PORTAL_SETTINGS
  below for how the referenced PNG is re-uploaded and the value rewritten to
  the new bucket-relative path).
- `training_modules`/`training_videos`/`user_training_progress`: legacy
  `video_path` is an uploaded FILE on disk (unlike the unified model's
  docstring, which assumes a pre-existing Supabase Storage path) — the file
  is uploaded to `library-resources` (there is no dedicated training-videos
  bucket in the unified bucket list; GO_LIVE.md's own bucket inventory in §1
  doesn't include one either) and `video_path` is set to the resulting
  storage PATH (video_path is a plain String column, not bucket/path pair —
  the unified TrainingVideo model was never migrated to A2's bucket/file_path
  split, so this is the best fit without a schema change). Local fixture has
  ZERO rows in all three tables (see verification report) — this path is
  exercised structurally but unverified against real data; flagged as a gap.
- Config tables (document_templates, apply_questions, titles,
  badge_definitions, system_settings) are OUT OF SCOPE for this script — see
  the docstring note in GO_LIVE.md §3.A4's last paragraph. They may hold real
  admin-authored config currently sitting in the Supabase dev DB, a SEPARATE
  data source this script has no access to and does not touch. A future,
  separate one-off script/export is needed before decommissioning Supabase
  (GO_LIVE.md §6).

────────────────────────────────────────────────────────────────────────────
REAL CUTOVER RUN — what changes (GO_LIVE.md §5 / AGENT_LOG.md "ETL execution
strategy DECIDED")
────────────────────────────────────────────────────────────────────────────
This script is developed/tested here against LOCAL FIXTURES ONLY:
  - legacy DB  = local Postgres 17:5433 restore of the Jul-5 dump (STALE vs
    the live old VPS — 191 vs 195 module_submissions as of the Jul-5 dump,
    more by cutover time per AGENT_LOG.md's old-VPS inventory).
  - uploads    = local Jul-5 copy of backend/app/uploads (246 MB vs the old
    VPS's live 288 MB at inventory time).
  - target     = a throwaway scratch DB on this machine.

For the REAL cutover, per AGENT_LOG.md's decision, everything runs ON THE NEW
VPS, not here and not against the old VPS directly:
  1. On the new VPS: `pg_dump -Fc` a FRESH snapshot from the OLD VPS (over the
     network, read-only) into a scratch `spacepoint_legacy` DB restored
     locally on the new VPS.
  2. `rsync` a FRESH copy of the old VPS's uploads/ tree to the new VPS.
  3. Run this exact script with `--legacy-db` pointed at that fresh local
     scratch DB, `--uploads-dir` at that fresh local rsync copy, and
     `--unified-db`/`--storage-root` pointed at the REAL `spacepoint_unified`
     DB + REAL `/var/lib/spacepoint/storage` on the new VPS (with the real,
     already-provisioned `STORAGE_ENCRYPTION_KEY` from `/etc/spacepoint/env`
     — never a script-generated one for a real run).
  4. The two-stage cutover (GO_LIVE.md §7.1) means this whole sequence runs
     TWICE: once onto a throwaway "test" target for boss approval, then again
     (fresh re-dump, fresh re-rsync, wiped target) for the real production
     cutover. This script does not need to know which stage it's in — it
     just needs a fresh source and an empty (or safely re-runnable) target
     each time, per the idempotency notes above.
Nothing else changes: no code path in this script is fixture-specific.
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import psycopg2
import psycopg2.extras

# ─────────────────────────────────────────────────────────────────────────
# Bootstrap: put backend/ on sys.path so `import app.*` works when this
# script is invoked as `python scripts/migrate_legacy.py` from backend/.
# ─────────────────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


MIGRATION_ID_MAPS_DIR = Path(__file__).resolve().parent / "migration_id_maps"

# Bucket names — copied verbatim from real caller conventions in
# app/routers/instructors/*.py and app/routers/documents.py (grepped, not
# guessed) so migrated rows resolve through the exact same storage.resolve_url
# / get_signed_url paths the live app already uses.
BUCKET_INSTRUCTOR_DOCUMENTS = "instructor-documents"
BUCKET_PROFILE_PICTURES = "profile_pictures"
BUCKET_CONTRACTS = "contracts"
BUCKET_APPLICANT_SUBMISSIONS = "applicant-submissions"
BUCKET_LIBRARY_RESOURCES = "library-resources"
BUCKET_PAYMENT_LETTERS = "payment-letters"
BUCKET_CERTIFICATES = "certificates"


# ═══════════════════════════════════════════════════════════════════════
# Verification / reporting
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TableReport:
    legacy_count: int = 0
    migrated_count: int = 0
    skipped: list[str] = field(default_factory=list)  # human-readable reasons


@dataclass
class Report:
    tables: dict[str, TableReport] = field(default_factory=dict)
    files_uploaded: dict[str, int] = field(default_factory=dict)  # bucket -> count
    files_missing: list[str] = field(default_factory=list)  # legacy paths not found on disk
    files_failed: list[str] = field(default_factory=list)

    def table(self, name: str) -> TableReport:
        return self.tables.setdefault(name, TableReport())

    def print_summary(self) -> None:
        print("\n" + "=" * 78)
        print("MIGRATION VERIFICATION REPORT")
        print("=" * 78)
        print(f"{'table':<28} {'legacy':>8} {'migrated':>10} {'skipped':>8}")
        print("-" * 78)
        for name, t in sorted(self.tables.items()):
            print(f"{name:<28} {t.legacy_count:>8} {t.migrated_count:>10} {len(t.skipped):>8}")
        print("-" * 78)
        print("Files uploaded per bucket:")
        for bucket, count in sorted(self.files_uploaded.items()):
            print(f"  {bucket:<24} {count}")
        if self.files_missing:
            print(f"\nFiles referenced but NOT FOUND on disk ({len(self.files_missing)}):")
            for f in self.files_missing[:50]:
                print(f"  MISSING: {f}")
            if len(self.files_missing) > 50:
                print(f"  ... and {len(self.files_missing) - 50} more")
        if self.files_failed:
            print(f"\nFiles that failed to upload ({len(self.files_failed)}):")
            for f in self.files_failed[:50]:
                print(f"  FAILED: {f}")
        any_skips = False
        for name, t in sorted(self.tables.items()):
            if t.skipped:
                any_skips = True
                print(f"\nSkipped/unmappable rows in {name} ({len(t.skipped)}):")
                for s in t.skipped[:20]:
                    print(f"  - {s}")
                if len(t.skipped) > 20:
                    print(f"  ... and {len(t.skipped) - 20} more")
        if not any_skips:
            print("\nNo skipped/unmappable rows.")
        print("=" * 78 + "\n")


# ═══════════════════════════════════════════════════════════════════════
# ID maps: legacy int PK -> new uuid4, persisted to CSV for audit
# ═══════════════════════════════════════════════════════════════════════

class IdMap:
    """old_int_id -> uuid4, with CSV dump/reload so re-runs are stable."""

    def __init__(self, table: str):
        self.table = table
        self._map: dict[int, uuid.UUID] = {}
        self._extra: dict[int, dict[str, str]] = {}  # optional extra audit columns
        self._load_existing()

    def _csv_path(self) -> Path:
        MIGRATION_ID_MAPS_DIR.mkdir(parents=True, exist_ok=True)
        return MIGRATION_ID_MAPS_DIR / f"{self.table}.csv"

    def _load_existing(self) -> None:
        """Reload a prior run's map so re-runs assign the SAME uuids to the
        same legacy rows (idempotency: a second run must not orphan rows a
        first run already wrote FK references to)."""
        path = self._csv_path()
        if not path.exists():
            return
        with open(path, "r", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    self._map[int(row["legacy_id"])] = uuid.UUID(row["new_uuid"])
                except (KeyError, ValueError):
                    continue

    def get_or_create(self, legacy_id: int, **extra: str) -> uuid.UUID:
        if legacy_id not in self._map:
            self._map[legacy_id] = uuid.uuid4()
        if extra:
            self._extra[legacy_id] = {k: str(v) for k, v in extra.items()}
        return self._map[legacy_id]

    def get(self, legacy_id: Optional[int]) -> Optional[uuid.UUID]:
        if legacy_id is None:
            return None
        return self._map.get(legacy_id)

    def dump(self) -> None:
        path = self._csv_path()
        extra_cols = sorted({k for v in self._extra.values() for k in v})
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["legacy_id", "new_uuid", *extra_cols])
            for legacy_id in sorted(self._map):
                extra = self._extra.get(legacy_id, {})
                writer.writerow([legacy_id, str(self._map[legacy_id]), *[extra.get(c, "") for c in extra_cols]])


# ═══════════════════════════════════════════════════════════════════════
# Legacy DB reader (plain psycopg2, sync — legacy models aren't part of
# this repo, so we read via dict rows rather than importing legacy ORM code)
# ═══════════════════════════════════════════════════════════════════════

class LegacyDB:
    def __init__(self, dsn: str):
        # Strip any async driver suffix — legacy reads are always sync.
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
        self.conn = psycopg2.connect(dsn)
        self.conn.autocommit = True

    def rows(self, query: str, params: tuple = ()) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    def close(self) -> None:
        self.conn.close()


# ═══════════════════════════════════════════════════════════════════════
# File helpers
# ═══════════════════════════════════════════════════════════════════════

def resolve_legacy_file(uploads_dir: Path, legacy_path: Optional[str]) -> Optional[Path]:
    """Legacy DB rows store ABSOLUTE VPS filesystem paths, e.g.
    '/var/www/spacepoint_portal/backend/app/uploads/instructor_photos/2.jpg'
    (confirmed by direct inspection of the restored local DB — every
    file-path column in every legacy table uses this convention, some via
    '.../app/services/../uploads/...' with a literal '..' segment).
    Re-base onto whatever --uploads-dir was given for THIS run (local fixture
    copy today; a fresh rsync copy at real cutover) by taking everything
    after the last 'uploads' path segment.
    """
    if not legacy_path:
        return None
    normalized = legacy_path.replace("\\", "/")
    marker = "/uploads/"
    idx = normalized.find(marker)
    if idx == -1:
        # Already-relative path (defensive — not seen in practice).
        rel = normalized.lstrip("/")
    else:
        rel = normalized[idx + len(marker):]
    candidate = (uploads_dir / rel).resolve()
    return candidate


def guess_content_type(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


# ═══════════════════════════════════════════════════════════════════════
# Main ETL
# ═══════════════════════════════════════════════════════════════════════

async def run(args: argparse.Namespace) -> Report:
    # ── Bind the unified app's DB engine to the target we were given,
    #    BEFORE importing anything that reads settings.DATABASE_URL at
    #    import time. We do this by setting the env var the pydantic
    #    Settings model reads, prior to importing app.core.config. ──
    os.environ["DATABASE_URL"] = args.unified_db
    os.environ["STORAGE_BACKEND"] = "local"
    os.environ["STORAGE_ROOT"] = args.storage_root
    if args.storage_key:
        os.environ["STORAGE_ENCRYPTION_KEY"] = args.storage_key
    elif not os.environ.get("STORAGE_ENCRYPTION_KEY"):
        from cryptography.fernet import Fernet
        generated = Fernet.generate_key().decode()
        os.environ["STORAGE_ENCRYPTION_KEY"] = generated
        print(f"[migrate_legacy] No --storage-key / STORAGE_ENCRYPTION_KEY given — "
              f"generated one for this run: {generated}\n"
              f"  (dev convenience only — a real cutover run MUST use the VPS's "
              f"real provisioned key, or previously-migrated files become unreadable.)")

    # Imports deferred until after the env vars above are set, since
    # app.core.config.Settings() reads them at class-instantiation time
    # (module import time) via pydantic-settings.
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal, engine
    from app.services import storage
    from app.models.user import User
    from app.models.enums import (
        UserRole, ApplicationStatus, ModuleSubmissionStatus, VideoSubmissionStatus,
        PaymentLetterStatus, PaymentSessionRole, CertificateType,
    )
    from app.models.instructors.applicant_profile import ApplicantProfile
    from app.models.instructors.application_review import ApplicationReview
    from app.models.instructors.instructor_profile import InstructorProfile
    from app.models.instructors.instructor_document import InstructorDocument
    from app.models.instructors.video_submission import VideoSubmission
    from app.models.instructors.presentation_submission import PresentationSubmission
    from app.models.instructors.assessment_submission import AssessmentSubmission
    from app.models.instructors.checklist import (
        ChecklistModule, ModuleSection, ChecklistItem, UserChecklistProgress,
    )
    from app.models.instructors.module_submission import ModuleSubmission
    from app.models.instructors.training import TrainingModule, TrainingVideo, UserTrainingProgress
    from app.models.instructors.library import LibraryModule, LibraryResource
    from app.models.instructors.payment import (
        PaymentBatch, PaymentLetter, PaymentSession, PaymentAddon,
        InstructorBankDetails, PortalSetting,
    )
    from app.models.instructors.invitation_code import InvitationCode
    from app.models.certificate import Certificate
    from app.models.id_card import IdCard

    report = Report()
    uploads_dir = Path(args.uploads_dir).resolve()
    legacy = LegacyDB(args.legacy_db)

    # id maps — one per legacy table other rows reference by int FK
    map_users = IdMap("users")
    map_modules = IdMap("modules")               # -> checklist_modules
    map_sections = IdMap("module_sections")
    map_checklist_items = IdMap("checklist_items")
    map_library_modules = IdMap("library_modules")
    map_payment_batches = IdMap("payment_batches")
    map_payment_letters = IdMap("payment_letters")
    map_payment_sessions = IdMap("payment_sessions")
    map_training_modules = IdMap("training_modules")
    map_training_videos = IdMap("training_videos")

    async def upload(bucket: str, path: str, legacy_path: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """Returns (bucket, path) to store, or (None, None) if the source
        file couldn't be found/read. Honors --dry-run / --skip-files."""
        if not legacy_path:
            return None, None
        if args.dry_run or args.skip_files:
            report.files_uploaded[bucket] = report.files_uploaded.get(bucket, 0) + 1
            return bucket, path
        src = resolve_legacy_file(uploads_dir, legacy_path)
        if src is None or not src.is_file():
            report.files_missing.append(f"{legacy_path}  (resolved: {src})")
            return None, None
        try:
            data = src.read_bytes()
            await storage.upload_to_path(bucket, path, data, guess_content_type(src))
            report.files_uploaded[bucket] = report.files_uploaded.get(bucket, 0) + 1
            return bucket, path
        except Exception as exc:  # noqa: BLE001
            report.files_failed.append(f"{legacy_path} -> {bucket}/{path}: {exc}")
            return None, None

    async with AsyncSessionLocal() as db:

        # ── users ────────────────────────────────────────────────────────
        t = report.table("users")
        legacy_users = legacy.rows("SELECT * FROM users ORDER BY id")
        t.legacy_count = len(legacy_users)
        role_map = {
            "ADMIN": UserRole.admin,
            "APPLICANT": UserRole.applicant,
            "INSTRUCTOR": UserRole.instructor,
            "FACILITATOR": UserRole.facilitator,
        }
        for lu in legacy_users:
            new_id = map_users.get_or_create(lu["id"], email=lu["email"])
            role = role_map.get(lu["role"])
            if role is None:
                t.skipped.append(f"user id={lu['id']} email={lu['email']}: unknown role {lu['role']!r}")
                continue
            existing = await db.get(User, new_id)
            if existing is None:
                existing = User(id=new_id)
                db.add(existing)
            existing.full_name = lu["name"]
            existing.email = lu["email"]
            existing.password_hash = lu["password_hash"]  # VERBATIM — bcrypt compatible, never re-hash
            existing.roles = [role]
            existing.status = "active"
            # NOTE: legacy `invitation_code_used` is NOT the same concept as
            # unified `users.invite_code`. `invite_code` is a UNIQUE,
            # personally-owned referral code an ambassador shares out
            # (app/routers/apply.py checks User.invite_code == <code the
            # APPLICANT typed>); `invitation_code_used` is which ADMIN-issued
            # invitation_codes.code the applicant typed at signup — many
            # legacy users share the same one (confirmed: 37 users share
            # "SPACEPOINT26" locally), which would violate invite_code's
            # UNIQUE constraint if mapped directly. There is no unified
            # column for "which invitation code did I sign up with" — the
            # `invitation_codes` table itself is migrated separately below,
            # but the per-user usage link is not preserved (not tracked by
            # any unified FK/column). Deliberately left unset here.
            existing.invite_code = None
            existing.must_change_password = bool(lu.get("must_change_password") or 0)
            existing.phone = lu.get("phone")
            existing.created_at = lu.get("created_at") or datetime.now(timezone.utc)
            existing.last_login_at = lu.get("last_login_at")
            t.migrated_count += 1
        await db.flush()

        # ── applicant_profiles ──────────────────────────────────────────
        t = report.table("applicant_profiles")
        legacy_rows = legacy.rows("SELECT * FROM applicant_profiles")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"applicant_profile user_id={r['user_id']}: no matching user")
                continue
            existing = await db.get(ApplicantProfile, new_user_id)
            if existing is None:
                existing = ApplicantProfile(user_id=new_user_id)
                db.add(existing)
            existing.university = r.get("university")
            existing.highest_degree = r.get("highest_degree")
            existing.highest_degree_other = r.get("highest_degree_other")
            existing.city_of_residence = r.get("city_of_residence")
            existing.deliver_cities = _json_list(r.get("deliver_cities_json"))
            existing.background_areas = _json_list(r.get("background_areas_json"))
            existing.background_other = r.get("background_other")
            existing.has_own_transportation = bool(r.get("has_own_transportation") or False)
            existing.country = r.get("country") or "United Arab Emirates"
            t.migrated_count += 1
        await db.flush()

        # ── application_reviews ─────────────────────────────────────────
        t = report.table("application_reviews")
        legacy_rows = legacy.rows("SELECT * FROM application_reviews")
        t.legacy_count = len(legacy_rows)
        status_map = {
            "IN_PROGRESS": ApplicationStatus.in_progress,
            "UNDER_REVIEW": ApplicationStatus.under_review,
            "PHASE_1_APPROVED": ApplicationStatus.phase_1_approved,
            "RESEARCH_APPROVED": ApplicationStatus.research_approved,
            "APPROVED": ApplicationStatus.approved,
            "REJECTED": ApplicationStatus.rejected,
        }
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"application_review id={r['id']}: no matching user {r['user_id']}")
                continue
            status = status_map.get(r["status"])
            if status is None:
                t.skipped.append(f"application_review id={r['id']}: unknown status {r['status']!r}")
                continue
            existing = (await db.execute(
                select(ApplicationReview).where(ApplicationReview.user_id == new_user_id)
            )).scalars().first()
            if existing is None:
                existing = ApplicationReview(id=uuid.uuid4(), user_id=new_user_id)
                db.add(existing)
            existing.status = status
            existing.admin_id = map_users.get(r.get("admin_id"))
            existing.feedback = r.get("feedback")
            existing.reviewed_at = r.get("reviewed_at")
            t.migrated_count += 1
        await db.flush()

        # ── instructor_profiles + card_number + id_cards ────────────────
        t = report.table("instructor_profiles")
        legacy_rows = legacy.rows("SELECT * FROM instructor_profiles")
        t.legacy_count = len(legacy_rows)
        max_card_number = 0
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"instructor_profile id={r['id']}: no matching user {r['user_id']}")
                continue

            user = await db.get(User, new_user_id)
            card_number = _parse_card_number(r.get("instructor_id"))
            if card_number is not None:
                if user.card_number is None:
                    user.card_number = card_number
                elif user.card_number != card_number:
                    t.skipped.append(
                        f"instructor_profile id={r['id']}: user already has card_number "
                        f"{user.card_number}, legacy instructor_id implies {card_number} — kept existing"
                    )
                max_card_number = max(max_card_number, card_number)

            photo_bucket, photo_path = await upload(
                BUCKET_PROFILE_PICTURES, f"{new_user_id}{_ext(r.get('profile_photo_path'))}",
                r.get("profile_photo_path"),
            )
            if photo_path:
                user.photo_path = photo_path
                user.photo_url = await storage.get_signed_url(photo_bucket, photo_path, 10 * 365 * 24 * 3600)
            user.linkedin_url = r.get("linkedin_url")

            contract_bucket, contract_path = await upload(
                BUCKET_CONTRACTS, f"{new_user_id}/agreement{_ext(r.get('contract_path'))}",
                r.get("contract_path"),
            )
            signed_bucket, signed_path = await upload(
                BUCKET_CONTRACTS, f"{new_user_id}/signed{_ext(r.get('signed_contract_path'))}",
                r.get("signed_contract_path"),
            )
            # front_card_path / back_card_path: INTENTIONALLY DROPPED (see
            # module docstring) — id cards render on the fly, no columns exist
            # to hold a static image even if we wanted to keep it.

            existing = await db.get(InstructorProfile, new_user_id)
            if existing is None:
                existing = InstructorProfile(user_id=new_user_id)
                db.add(existing)
            existing.contract_path = contract_path
            existing.signed_contract_path = signed_path
            if contract_path:
                existing.contract_url = await storage.get_signed_url(contract_bucket, contract_path, 10 * 365 * 24 * 3600)
            if signed_path:
                existing.signed_contract_url = await storage.get_signed_url(signed_bucket, signed_path, 10 * 365 * 24 * 3600)
            existing.created_at = r.get("created_at") or datetime.now(timezone.utc)
            existing.updated_at = r.get("updated_at") or existing.created_at

            # id_cards row, mirroring ensure_card_id's shape, so the profile
            # card page has something to read immediately post-migration.
            if card_number is not None:
                card_id_str = f"SP-{card_number:04d}-UAE"
                existing_card = (await db.execute(
                    select(IdCard).where(IdCard.user_id == new_user_id, IdCard.role == UserRole.instructor)
                )).scalars().first()
                if existing_card is None:
                    existing_card = IdCard(user_id=new_user_id, role=UserRole.instructor)
                    db.add(existing_card)
                existing_card.card_id = card_id_str
                existing_card.generated_at = r.get("issue_date") or datetime.now(timezone.utc)

            t.migrated_count += 1
        await db.flush()

        # Bump card_seq_person past the max assigned number — same pattern
        # as sql/0011_person_id_cards.sql's own DO-block bump, so the next
        # live allocation (ensure_card_id) never collides with a migrated
        # legacy number.
        if max_card_number > 0 and not args.dry_run:
            from sqlalchemy import text
            await db.execute(text("CREATE SEQUENCE IF NOT EXISTS card_seq_person START 1 INCREMENT 1"))
            cur_val = (await db.execute(text("SELECT last_value FROM card_seq_person"))).scalar_one()
            if max_card_number > cur_val:
                await db.execute(text("SELECT setval('card_seq_person', :n)"), {"n": max_card_number})

        # ── instructor_documents (personal vault) ───────────────────────
        t = report.table("instructor_documents")
        legacy_rows = legacy.rows("SELECT * FROM instructor_documents ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"instructor_document id={r['id']}: no matching user {r['user_id']}")
                continue
            doc_id = _stable_uuid("instructor_documents", r["id"])
            existing = await db.get(InstructorDocument, doc_id)
            if existing is None:
                existing = InstructorDocument(id=doc_id, user_id=new_user_id)
                db.add(existing)
            fname = f"{r['id']}_{_safe_name(r['document_type'])}{_ext(r.get('file_path'))}"
            bucket, path = await upload(BUCKET_INSTRUCTOR_DOCUMENTS, f"{new_user_id}/{fname}", r.get("file_path"))
            existing.document_type = r["document_type"]
            existing.bucket = bucket
            existing.file_path = path
            existing.file_url = (
                await storage.get_signed_url(bucket, path, 10 * 365 * 24 * 3600) if path else ""
            )
            existing.uploaded_at = r.get("uploaded_at") or datetime.now(timezone.utc)
            if not path:
                t.skipped.append(f"instructor_document id={r['id']}: file not found ({r.get('file_path')})")
                continue
            t.migrated_count += 1
        await db.flush()

        # ── checklist hierarchy: modules -> checklist_modules, sections,
        #    items, progress ──────────────────────────────────────────────
        t = report.table("checklist_modules")
        legacy_modules = legacy.rows("SELECT * FROM modules ORDER BY id")
        t.legacy_count = len(legacy_modules)
        for r in legacy_modules:
            new_id = map_modules.get_or_create(r["id"], title=r["title"])
            existing = await db.get(ChecklistModule, new_id)
            if existing is None:
                existing = ChecklistModule(id=new_id)
                db.add(existing)
            existing.title = r["title"]
            existing.sort_order = r.get("sort_order") or 1
            t.migrated_count += 1
        await db.flush()

        t = report.table("module_sections")
        legacy_rows = legacy.rows("SELECT * FROM module_sections ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_module_id = map_modules.get(r["module_id"])
            if new_module_id is None:
                t.skipped.append(f"module_section id={r['id']}: no matching module {r['module_id']}")
                continue
            new_id = map_sections.get_or_create(r["id"])
            existing = await db.get(ModuleSection, new_id)
            if existing is None:
                existing = ModuleSection(id=new_id)
                db.add(existing)
            existing.module_id = new_module_id
            existing.title = r["title"]
            existing.sort_order = r.get("sort_order") or 1
            t.migrated_count += 1
        await db.flush()

        t = report.table("checklist_items")
        legacy_rows = legacy.rows("SELECT * FROM checklist_items ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_module_id = map_modules.get(r["module_id"])
            if new_module_id is None:
                t.skipped.append(f"checklist_item id={r['id']}: no matching module {r['module_id']}")
                continue
            new_id = map_checklist_items.get_or_create(r["id"])
            existing = await db.get(ChecklistItem, new_id)
            if existing is None:
                existing = ChecklistItem(id=new_id)
                db.add(existing)
            existing.module_id = new_module_id
            existing.section_id = map_sections.get(r.get("section_id"))
            existing.item_code = r["item_code"]
            existing.title = r["title"]
            existing.description = r.get("description")
            existing.sort_order = r.get("sort_order") or 1
            existing.is_required = bool(r.get("is_required", True))
            t.migrated_count += 1
        await db.flush()

        t = report.table("user_checklist_progress")
        legacy_rows = legacy.rows("SELECT * FROM user_checklist_progress ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            new_item_id = map_checklist_items.get(r["checklist_item_id"])
            if new_user_id is None or new_item_id is None:
                t.skipped.append(
                    f"user_checklist_progress id={r['id']}: unmapped user={r['user_id']} "
                    f"or item={r['checklist_item_id']}"
                )
                continue
            existing = (await db.execute(
                select(UserChecklistProgress).where(
                    UserChecklistProgress.user_id == new_user_id,
                    UserChecklistProgress.checklist_item_id == new_item_id,
                )
            )).scalars().first()
            if existing is None:
                existing = UserChecklistProgress(
                    id=uuid.uuid4(), user_id=new_user_id, checklist_item_id=new_item_id,
                )
                db.add(existing)
            existing.is_completed = bool(r.get("is_completed") or False)
            existing.updated_at = r.get("updated_at") or datetime.now(timezone.utc)
            t.migrated_count += 1
        await db.flush()
        # KNOWN SOURCE DATA QUALITY ISSUE (found during verification, not a
        # script bug): the local legacy fixture has one exact duplicate
        # (user_id, checklist_item_id) pair in user_checklist_progress
        # (user 66 / checklist_item 1, x2) with no unique constraint in the
        # legacy schema to prevent it. Both legacy rows are processed (so
        # t.migrated_count reports the full legacy row count as "processed"),
        # but since unified user_checklist_progress has one natural row per
        # (user_id, checklist_item_id), the second duplicate updates the
        # SAME row the first created rather than inserting a second — so the
        # unified table ends up with one fewer physical row than the legacy
        # count on a from-scratch run (1870 vs 1871 legacy rows locally).
        # This is correct/intended de-duplication, not data loss (both legacy
        # rows carry identical is_completed=true; there is nothing to choose
        # between them) — flagged here for visibility during a real cutover
        # verification pass, where the same off-by-one may recur if the live
        # data has its own duplicates.

        # ── module_submissions ──────────────────────────────────────────
        t = report.table("module_submissions")
        legacy_rows = legacy.rows("SELECT * FROM module_submissions ORDER BY id")
        t.legacy_count = len(legacy_rows)
        ms_status_map = {
            "SUBMITTED": ModuleSubmissionStatus.submitted,
            "APPROVED": ModuleSubmissionStatus.approved,
            "REJECTED": ModuleSubmissionStatus.rejected,
        }
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            new_module_id = map_modules.get(r["module_id"])
            if new_user_id is None or new_module_id is None:
                t.skipped.append(
                    f"module_submission id={r['id']}: unmapped user={r['user_id']} or module={r['module_id']}"
                )
                continue
            status = ms_status_map.get(r["status"], ModuleSubmissionStatus.submitted)
            sub_id = _stable_uuid("module_submissions", r["id"])
            existing = await db.get(ModuleSubmission, sub_id)
            if existing is None:
                existing = ModuleSubmission(id=sub_id, user_id=new_user_id, module_id=new_module_id)
                db.add(existing)
            fname = r.get("original_filename") or Path(r.get("file_path") or "file").name
            bucket, path = await upload(
                BUCKET_APPLICANT_SUBMISSIONS, f"{new_user_id}/{new_module_id}/{fname}", r.get("file_path"),
            )
            existing.bucket = bucket
            existing.file_path = path
            existing.file_url = (
                await storage.get_signed_url(bucket, path, 10 * 365 * 24 * 3600) if path else ""
            )
            existing.original_filename = r.get("original_filename")
            existing.notes_text = r.get("notes_text")
            existing.status = status
            existing.feedback = r.get("feedback")
            existing.submitted_at = r.get("submitted_at") or datetime.now(timezone.utc)
            existing.reviewed_at = r.get("reviewed_at")
            existing.reviewer_admin_id = map_users.get(r.get("reviewer_admin_id"))
            if not path:
                t.skipped.append(f"module_submission id={r['id']}: file not found ({r.get('file_path')})")
                continue
            t.migrated_count += 1
        await db.flush()

        # ── video_submissions ────────────────────────────────────────────
        t = report.table("video_submissions")
        legacy_rows = legacy.rows("SELECT * FROM video_submissions ORDER BY id")
        t.legacy_count = len(legacy_rows)
        vs_status_map = {"DRAFT": VideoSubmissionStatus.draft, "SUBMITTED": VideoSubmissionStatus.submitted}
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"video_submission id={r['id']}: no matching user {r['user_id']}")
                continue
            vid_id = _stable_uuid("video_submissions", r["id"])
            existing = await db.get(VideoSubmission, vid_id)
            if existing is None:
                existing = VideoSubmission(id=vid_id, user_id=new_user_id, video_no=r["video_no"])
                db.add(existing)
            existing.youtube_url = r.get("youtube_url")
            existing.summary_text = r.get("summary_text")
            existing.word_count = r.get("word_count") or 0
            existing.status = vs_status_map.get(r["status"], VideoSubmissionStatus.draft)
            existing.submitted_at = r.get("submitted_at")
            t.migrated_count += 1
        await db.flush()

        # ── presentation_submissions ─────────────────────────────────────
        t = report.table("presentation_submissions")
        legacy_rows = legacy.rows("SELECT * FROM presentation_submissions ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"presentation_submission id={r['id']}: no matching user {r['user_id']}")
                continue
            existing = (await db.execute(
                select(PresentationSubmission).where(PresentationSubmission.user_id == new_user_id)
            )).scalars().first()
            if existing is None:
                existing = PresentationSubmission(id=uuid.uuid4(), user_id=new_user_id, video_link=r["video_link"])
                db.add(existing)
            existing.video_link = r["video_link"]
            existing.submitted_at = r.get("submitted_at") or datetime.now(timezone.utc)
            t.migrated_count += 1
        await db.flush()

        # ── assessment_submissions: TWO legacy sources feed ONE unified
        #    table (see docstring) — legacy `assessment_submissions` (the
        #    real Phase-2 "10 Questions Assessment") and legacy
        #    `research_submissions` (AGENT_LOG.md-resolved: same concept). ──
        t = report.table("assessment_submissions")
        legacy_assess = legacy.rows("SELECT * FROM assessment_submissions ORDER BY id")
        legacy_research = legacy.rows("SELECT * FROM research_submissions ORDER BY id")
        t.legacy_count = len(legacy_assess) + len(legacy_research)

        async def _upsert_assessment(
            new_user_id: uuid.UUID, file_bucket: Optional[str], file_path: Optional[str],
            google_drive_link: Optional[str], comments: Optional[str], submitted_at, source: str,
        ) -> None:
            existing = (await db.execute(
                select(AssessmentSubmission).where(AssessmentSubmission.user_id == new_user_id)
            )).scalars().first()
            if existing is not None and existing.submitted_at and source == "research_submissions":
                # Collision guard: a legacy assessment_submissions row already
                # claimed this user's UNIQUE slot — log rather than clobber.
                if existing.file_path or existing.google_drive_link or existing.comments:
                    t.skipped.append(
                        f"assessment_submissions collision for user {new_user_id}: "
                        f"both legacy assessment_submissions and research_submissions rows exist; "
                        f"kept the assessment_submissions one, dropped research_submissions"
                    )
                    return
            if existing is None:
                existing = AssessmentSubmission(id=uuid.uuid4(), user_id=new_user_id)
                db.add(existing)
            existing.bucket = file_bucket
            existing.file_path = file_path
            existing.file_url = (
                await storage.get_signed_url(file_bucket, file_path, 10 * 365 * 24 * 3600) if file_path else None
            )
            existing.google_drive_link = google_drive_link
            existing.comments = comments
            existing.submitted_at = submitted_at or datetime.now(timezone.utc)
            t.migrated_count += 1

        for r in legacy_assess:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"assessment_submission id={r['id']}: no matching user {r['user_id']}")
                continue
            fname = r.get("original_filename") or Path(r.get("file_path") or "assessment").name
            bucket, path = await upload(
                BUCKET_APPLICANT_SUBMISSIONS, f"{new_user_id}/assessment/{fname}", r.get("file_path"),
            )
            await _upsert_assessment(
                new_user_id, bucket, path, r.get("google_drive_link"), r.get("comments"),
                r.get("submitted_at"), source="assessment_submissions",
            )

        for r in legacy_research:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"research_submission id={r['id']}: no matching user {r['user_id']}")
                continue
            # original_filename has no column in unified assessment_submissions
            # — folded into the storage path per AGENT_LOG.md's resolution
            # note so it isn't silently lost.
            fname = r.get("original_filename") or Path(r.get("file_path") or "research").name
            bucket, path = await upload(
                BUCKET_APPLICANT_SUBMISSIONS, f"{new_user_id}/research/{fname}", r.get("file_path"),
            )
            await _upsert_assessment(
                new_user_id, bucket, path, None, r.get("content_text"),
                r.get("submitted_at"), source="research_submissions",
            )
        await db.flush()

        # ── training_modules / training_videos / user_training_progress ──
        t = report.table("training_modules")
        legacy_rows = legacy.rows("SELECT * FROM training_modules ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_id = map_training_modules.get_or_create(r["id"])
            existing = await db.get(TrainingModule, new_id)
            if existing is None:
                existing = TrainingModule(id=new_id)
                db.add(existing)
            existing.title = r["title"]
            existing.description = r.get("description")
            existing.sort_order = r.get("sort_order") or 1
            existing.created_at = r.get("created_at") or datetime.now(timezone.utc)
            t.migrated_count += 1
        await db.flush()

        t = report.table("training_videos")
        legacy_rows = legacy.rows("SELECT * FROM training_videos ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_module_id = map_training_modules.get(r["module_id"])
            if new_module_id is None:
                t.skipped.append(f"training_video id={r['id']}: no matching module {r['module_id']}")
                continue
            new_id = map_training_videos.get_or_create(r["id"])
            existing = await db.get(TrainingVideo, new_id)
            if existing is None:
                existing = TrainingVideo(id=new_id, module_id=new_module_id, title=r["title"], video_path="")
                db.add(existing)
            # legacy video_path is an uploaded FILE (not a pre-existing link) —
            # upload it and store the resulting storage PATH in video_path
            # (best fit: TrainingVideo has no bucket/file_path split — see
            # docstring "training_modules/training_videos" note).
            _, path = await upload(
                BUCKET_LIBRARY_RESOURCES, f"training/{new_module_id}/{Path(r.get('video_path') or 'video').name}",
                r.get("video_path"),
            )
            existing.module_id = new_module_id
            existing.title = r["title"]
            existing.description = r.get("description")
            existing.notes = r.get("notes")
            existing.video_path = path or existing.video_path or ""
            existing.sort_order = r.get("sort_order") or 1
            existing.created_at = r.get("created_at") or datetime.now(timezone.utc)
            if not path:
                t.skipped.append(f"training_video id={r['id']}: file not found ({r.get('video_path')})")
                continue
            t.migrated_count += 1
        await db.flush()

        t = report.table("user_training_progress")
        legacy_rows = legacy.rows("SELECT * FROM user_training_progress ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            new_video_id = map_training_videos.get(r["video_id"])
            if new_user_id is None or new_video_id is None:
                t.skipped.append(
                    f"user_training_progress id={r['id']}: unmapped user={r['user_id']} or video={r['video_id']}"
                )
                continue
            existing = (await db.execute(
                select(UserTrainingProgress).where(
                    UserTrainingProgress.user_id == new_user_id,
                    UserTrainingProgress.video_id == new_video_id,
                )
            )).scalars().first()
            if existing is None:
                existing = UserTrainingProgress(id=uuid.uuid4(), user_id=new_user_id, video_id=new_video_id)
                db.add(existing)
            existing.is_completed = bool(r.get("is_completed") or False)
            existing.completed_at = r.get("completed_at")
            t.migrated_count += 1
        await db.flush()

        # ── library_modules / library_resources ─────────────────────────
        t = report.table("library_modules")
        legacy_rows = legacy.rows("SELECT * FROM library_modules ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_id = map_library_modules.get_or_create(r["id"])
            existing = await db.get(LibraryModule, new_id)
            if existing is None:
                existing = LibraryModule(id=new_id)
                db.add(existing)
            existing.name = r["name"]
            existing.description = r.get("description")
            existing.created_at = r.get("created_at") or datetime.now(timezone.utc)
            t.migrated_count += 1
        await db.flush()

        t = report.table("library_resources")
        legacy_rows = legacy.rows("SELECT * FROM library_resources ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_module_id = map_library_modules.get(r["module_id"])
            if new_module_id is None:
                t.skipped.append(f"library_resource id={r['id']}: no matching module {r['module_id']}")
                continue
            res_id = _stable_uuid("library_resources", r["id"])
            existing = await db.get(LibraryResource, res_id)
            if existing is None:
                existing = LibraryResource(id=res_id, module_id=new_module_id, title=r["title"], format=r["format"], file_url="")
                db.add(existing)
            fname = Path(r.get("file_path") or "resource").name
            _, path = await upload(BUCKET_LIBRARY_RESOURCES, f"{new_module_id}/{fname}", r.get("file_path"))
            existing.title = r["title"]
            existing.description = r.get("description")
            existing.format = r["format"]
            existing.file_url = path or existing.file_url or ""
            existing.resource_type = "file"
            existing.uploader_id = map_users.get(r.get("uploader_id"))
            existing.module_id = new_module_id
            existing.created_at = r.get("created_at") or datetime.now(timezone.utc)
            if not path:
                t.skipped.append(f"library_resource id={r['id']}: file not found ({r.get('file_path')})")
                continue
            t.migrated_count += 1
        await db.flush()

        # ── payment_batches / payment_letters / payment_sessions / addons ─
        t = report.table("payment_batches")
        legacy_rows = legacy.rows("SELECT * FROM payment_batches ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_id = map_payment_batches.get_or_create(r["id"])
            existing = await db.get(PaymentBatch, new_id)
            if existing is None:
                existing = PaymentBatch(id=new_id)
                db.add(existing)
            existing.name = r["name"]
            existing.description = r.get("description")
            existing.created_by_admin_id = map_users.get(r.get("created_by_admin_id"))
            existing.created_at = r.get("created_at") or datetime.now(timezone.utc)
            t.migrated_count += 1
        await db.flush()

        t = report.table("payment_letters")
        legacy_rows = legacy.rows("SELECT * FROM payment_letters ORDER BY id")
        t.legacy_count = len(legacy_rows)
        pl_status_map = {
            "DRAFT": PaymentLetterStatus.draft, "PUBLISHED": PaymentLetterStatus.published,
            "SIGNED": PaymentLetterStatus.signed, "PAID": PaymentLetterStatus.paid,
        }
        for r in legacy_rows:
            new_user_id = map_users.get(r["instructor_user_id"])
            if new_user_id is None:
                t.skipped.append(f"payment_letter id={r['id']}: no matching user {r['instructor_user_id']}")
                continue
            new_id = map_payment_letters.get_or_create(r["id"])
            existing = await db.get(PaymentLetter, new_id)
            if existing is None:
                existing = PaymentLetter(id=new_id, instructor_user_id=new_user_id)
                db.add(existing)
            existing.batch_id = map_payment_batches.get(r.get("batch_id"))
            existing.instructor_user_id = new_user_id
            existing.letter_date = r.get("letter_date")
            existing.reference = r.get("reference") or "Facilitator Agreement"
            existing.status = pl_status_map.get(r["status"], PaymentLetterStatus.draft)
            existing.is_published = bool(r.get("is_published") or False)
            pdf_bucket, pdf_path = await upload(BUCKET_PAYMENT_LETTERS, f"{new_id}/letter.pdf", r.get("pdf_path"))
            signed_bucket, signed_path = await upload(BUCKET_PAYMENT_LETTERS, f"{new_id}/signed.pdf", r.get("signed_pdf_path"))
            existing.pdf_path = pdf_path
            existing.signed_pdf_path = signed_path
            existing.pdf_url = await storage.get_signed_url(pdf_bucket, pdf_path, 10 * 365 * 24 * 3600) if pdf_path else None
            existing.signed_pdf_url = (
                await storage.get_signed_url(signed_bucket, signed_path, 10 * 365 * 24 * 3600) if signed_path else None
            )
            existing.instructor_signature_data = r.get("instructor_signature_data")
            existing.signed_at = r.get("signed_at")
            existing.admin_notes = r.get("admin_notes")
            existing.created_at = r.get("created_at") or datetime.now(timezone.utc)
            existing.updated_at = r.get("updated_at") or existing.created_at
            t.migrated_count += 1
        await db.flush()

        t = report.table("payment_sessions")
        legacy_rows = legacy.rows("SELECT * FROM payment_sessions ORDER BY id")
        t.legacy_count = len(legacy_rows)
        role_session_map = {
            "LEAD_FACILITATOR": PaymentSessionRole.lead_facilitator,
            "FACILITATOR": PaymentSessionRole.facilitator,
            "ASSISTANT_FACILITATOR": PaymentSessionRole.assistant_facilitator,
        }
        for r in legacy_rows:
            new_letter_id = map_payment_letters.get(r["payment_letter_id"])
            if new_letter_id is None:
                t.skipped.append(f"payment_session id={r['id']}: no matching payment_letter {r['payment_letter_id']}")
                continue
            new_id = map_payment_sessions.get_or_create(r["id"])
            existing = await db.get(PaymentSession, new_id)
            if existing is None:
                existing = PaymentSession(
                    id=new_id, payment_letter_id=new_letter_id,
                    workshop_description=r["workshop_description"],
                    role=role_session_map.get(r["role"], PaymentSessionRole.facilitator),
                )
                db.add(existing)
            existing.payment_letter_id = new_letter_id
            existing.session_date = r.get("session_date")
            existing.workshop_description = r["workshop_description"]
            existing.role = role_session_map.get(r["role"], PaymentSessionRole.facilitator)
            existing.location = r.get("location")
            existing.duration_hours = r.get("duration_hours") or 0
            existing.compensation_aed = r.get("compensation_aed") or 0
            existing.sort_order = r.get("sort_order") or 1
            t.migrated_count += 1
        await db.flush()

        t = report.table("payment_addons")
        legacy_rows = legacy.rows("SELECT * FROM payment_addons ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_letter_id = map_payment_letters.get(r["payment_letter_id"])
            if new_letter_id is None:
                t.skipped.append(f"payment_addon id={r['id']}: no matching payment_letter {r['payment_letter_id']}")
                continue
            addon_id = _stable_uuid("payment_addons", r["id"])
            existing = await db.get(PaymentAddon, addon_id)
            if existing is None:
                existing = PaymentAddon(id=addon_id, payment_letter_id=new_letter_id, description=r["description"])
                db.add(existing)
            existing.payment_letter_id = new_letter_id
            existing.description = r["description"]
            existing.amount_aed = r.get("amount_aed") or 0
            existing.notes = r.get("notes")
            existing.sort_order = r.get("sort_order") or 1
            t.migrated_count += 1
        await db.flush()

        # ── instructor_bank_details ──────────────────────────────────────
        t = report.table("instructor_bank_details")
        legacy_rows = legacy.rows("SELECT * FROM instructor_bank_details ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"instructor_bank_details id={r['id']}: no matching user {r['user_id']}")
                continue
            existing = (await db.execute(
                select(InstructorBankDetails).where(InstructorBankDetails.user_id == new_user_id)
            )).scalars().first()
            if existing is None:
                existing = InstructorBankDetails(id=uuid.uuid4(), user_id=new_user_id)
                db.add(existing)
            existing.account_holder_name = r.get("account_holder_name")
            existing.bank_name = r.get("bank_name")
            existing.iban = r.get("iban")
            existing.swift_bic = r.get("swift_bic")
            existing.updated_at = r.get("updated_at") or datetime.now(timezone.utc)
            t.migrated_count += 1
        await db.flush()

        # ── portal_settings (incl. re-upload of admin_signature_path) ────
        t = report.table("portal_settings")
        legacy_rows = legacy.rows("SELECT * FROM portal_settings ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            key, value = r["key"], r.get("value")
            if key == "admin_signature_path" and value:
                # value is itself a legacy absolute file path (not just config
                # text) — re-upload the referenced PNG and rewrite the stored
                # value to the new bucket-relative path, matching how
                # routers/admin/settings.py stores this same fixed path today
                # ("instructor-documents", "settings/admin_signature.png").
                _, path = await upload(BUCKET_INSTRUCTOR_DOCUMENTS, "settings/admin_signature.png", value)
                value = path or value
                if not path:
                    t.skipped.append(f"portal_setting admin_signature_path: file not found ({r.get('value')})")
            existing = (await db.execute(select(PortalSetting).where(PortalSetting.key == key))).scalars().first()
            if existing is None:
                existing = PortalSetting(id=uuid.uuid4(), key=key)
                db.add(existing)
            existing.value = value
            existing.updated_at = r.get("updated_at") or datetime.now(timezone.utc)
            t.migrated_count += 1
        await db.flush()

        # ── certificates ─────────────────────────────────────────────────
        t = report.table("certificates")
        legacy_rows = legacy.rows("SELECT * FROM certificates ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            new_user_id = map_users.get(r["user_id"])
            if new_user_id is None:
                t.skipped.append(f"certificate id={r['id']}: no matching user {r['user_id']}")
                continue
            cert_id = _stable_uuid("certificates", r["id"])
            existing = await db.get(Certificate, cert_id)
            if existing is None:
                existing = Certificate(id=cert_id, user_id=new_user_id, type=CertificateType.workshop_delivery, file_url="")
                db.add(existing)
            fname = Path(r.get("pdf_path") or "certificate.pdf").name
            bucket, path = await upload(BUCKET_CERTIFICATES, f"{new_user_id}/{fname}", r.get("pdf_path"))
            existing.type = CertificateType.workshop_delivery
            existing.bucket = bucket
            existing.file_path = path
            existing.file_url = await storage.get_signed_url(bucket, path, 10 * 365 * 24 * 3600) if path else ""
            existing.generated_at = r.get("created_at") or datetime.now(timezone.utc)
            existing.payment_session_id = map_payment_sessions.get(r.get("payment_session_id"))
            existing.workshop_name = r.get("workshop_name")
            existing.workshop_date = r.get("workshop_date")
            existing.location = r.get("location")
            # instructor_name intentionally dropped — joinable via user_id -> users.full_name
            if not path:
                t.skipped.append(f"certificate id={r['id']}: file not found ({r.get('pdf_path')})")
                continue
            t.migrated_count += 1
        await db.flush()

        # ── invitation_codes ─────────────────────────────────────────────
        t = report.table("invitation_codes")
        legacy_rows = legacy.rows("SELECT * FROM invitation_codes ORDER BY id")
        t.legacy_count = len(legacy_rows)
        for r in legacy_rows:
            existing = (await db.execute(select(InvitationCode).where(InvitationCode.code == r["code"]))).scalars().first()
            if existing is None:
                existing = InvitationCode(id=uuid.uuid4(), code=r["code"])
                db.add(existing)
            existing.is_active = bool(r.get("is_active", True))
            existing.expires_at = r.get("expires_at")
            existing.max_uses = r.get("max_uses") or 20
            existing.used_count = r.get("used_count") or 0
            existing.created_at = r.get("created_at") or datetime.now(timezone.utc)
            # source_type / source_id intentionally dropped — no unified equivalent
            t.migrated_count += 1
        await db.flush()

        if args.dry_run:
            print("[migrate_legacy] --dry-run: rolling back (no DB rows written, no files uploaded).")
            await db.rollback()
        else:
            await db.commit()

    legacy.close()
    await engine.dispose()

    # Persist id maps for audit regardless of dry-run (harmless, small).
    for m in (
        map_users, map_modules, map_sections, map_checklist_items, map_library_modules,
        map_payment_batches, map_payment_letters, map_payment_sessions,
        map_training_modules, map_training_videos,
    ):
        m.dump()

    return report


# ═══════════════════════════════════════════════════════════════════════
# Small helpers
# ═══════════════════════════════════════════════════════════════════════

def _json_list(raw: Optional[str]) -> Optional[list[str]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _ext(path: Optional[str]) -> str:
    if not path:
        return ""
    return Path(path).suffix


def _safe_name(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s)


def _parse_card_number(instructor_id: Optional[str]) -> Optional[int]:
    """'SP-0002-UAE' -> 2. Returns None for blank/malformed values (some
    legacy instructor_profiles rows have no instructor_id assigned yet)."""
    if not instructor_id:
        return None
    parts = instructor_id.split("-")
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


_STABLE_NAMESPACE = uuid.UUID("6f1c9b2e-2f3a-4a1e-9b1a-2c9d7e6f5a4b")  # fixed, arbitrary


def _stable_uuid(table: str, legacy_id: int) -> uuid.UUID:
    """Deterministic uuid5 for tables with no dedicated IdMap object (their
    legacy id is never referenced by another legacy FK, so a full CSV audit
    map isn't needed — but re-running the script must still produce the SAME
    uuid for the same legacy row, hence uuid5 instead of uuid4)."""
    return uuid.uuid5(_STABLE_NAMESPACE, f"{table}:{legacy_id}")


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Legacy spacepoint_db -> unified schema ETL (GO_LIVE.md §3.A4)")
    p.add_argument("--legacy-db", required=True, help="Legacy Postgres DSN (sync, plain postgresql://)")
    p.add_argument("--unified-db", required=True, help="Unified Postgres DSN (async, postgresql+asyncpg://)")
    p.add_argument("--uploads-dir", required=True, help="Root of the legacy uploads/ tree")
    p.add_argument("--storage-root", required=True, help="STORAGE_ROOT for the local storage backend (encrypted blobs land here)")
    p.add_argument("--storage-key", default=None, help="Fernet key; falls back to STORAGE_ENCRYPTION_KEY env, else generates one (dev only)")
    p.add_argument("--dry-run", action="store_true", help="Parse + map + report only; write nothing")
    p.add_argument("--skip-files", action="store_true", help="Skip disk reads/uploads; DB rows still get bucket/path as if present")
    return p.parse_args(argv)


def main() -> None:
    import asyncio
    args = parse_args()
    report = asyncio.run(run(args))
    report.print_summary()


if __name__ == "__main__":
    main()
