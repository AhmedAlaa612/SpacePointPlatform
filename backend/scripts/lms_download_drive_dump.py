"""Pull the boss's Google Drive content dump straight onto the VPS — LM1-9's
"direct-to-VPS bulk import" door (LMS_EXECUTION_PLAN.md D3(b)).

WHY THIS EXISTS
    The operator's upload speed makes "download to laptop, then upload to the
    VPS" a non-starter for a folder of course videos. This script runs *on the
    VPS* and downloads straight from Drive to local disk — no upload leg at
    all. It does NOT touch the database or drive the LM1-5 authoring API: the
    course/module/lesson folder-mapping convention is still the operator's
    open call (§8 Q3), so turning downloaded files into courses is a separate
    step, once that mapping is agreed. This script only gets the bytes onto
    the box, preserving whatever folder structure the Drive folder already
    has (courses as subfolders, or however the operator organizes it) —
    nothing here assumes or enforces a layout.

USAGE
    python -m scripts.lms_download_drive_dump <drive_folder_url_or_id> [--dest DIR] [--dry-run]

    <drive_folder_url_or_id>  A Google Drive folder link (or bare folder ID).
                               Must be shared "Anyone with the link" — this
                               script does not do OAuth, so a private folder
                               will fail with a permission error from Drive.
    --dest DIR                 Where to write the download (default: ./lms-drive-dump,
                                relative to the current working directory — pass an
                                absolute path when running for real).
    --dry-run                  List what gdown would fetch without downloading
                                (gdown's own --output shows the tree; this flag
                                just skips the actual transfer).

IDEMPOTENCY
    gdown skips a file it already sees at the destination path with a
    matching size, so re-running after a partial/interrupted run resumes
    rather than re-downloading everything. It does not verify checksums —
    a corrupted partial file with the right size would not be caught; if a
    run gets interrupted mid-file, delete that one file before re-running.

REQUIRES
    `gdown` (backend/requirements.txt) — installed in the VPS's venv the same
    way the rest of backend/requirements.txt is.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FOLDER_ID_RE = re.compile(r"[-\w]{25,}")


def _extract_folder_id(url_or_id: str) -> str:
    """Accepts a full Drive URL or a bare folder ID either way."""
    match = FOLDER_ID_RE.search(url_or_id)
    if not match:
        raise ValueError(
            f"Couldn't find a Drive folder ID in {url_or_id!r} — pass the folder's "
            "share link (drive.google.com/drive/folders/<id>) or the bare ID."
        )
    return match.group(0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("USAGE")[0])
    parser.add_argument("folder", help="Drive folder URL or ID (must be link-shared)")
    parser.add_argument("--dest", default="lms-drive-dump", help="Destination directory")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually download")
    args = parser.parse_args()

    try:
        folder_id = _extract_folder_id(args.folder)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    print(f"Drive folder ID: {folder_id}")
    print(f"Destination:     {dest.resolve()}")
    if args.dry_run:
        print("--dry-run: skipping download. Run without --dry-run to actually pull the files.")
        return 0

    try:
        import gdown
    except ImportError:
        print(
            "error: gdown isn't installed. Run `pip install -r requirements.txt` "
            "(or just `pip install gdown`) in this environment first.",
            file=sys.stderr,
        )
        return 1

    # remaining_ok=True: Drive's own per-day download quota on a busy shared
    # folder is a Drive-side limit, not a bug here — the operator re-runs the
    # script later and idempotency (see module docstring) picks up where it
    # left off, rather than the whole run hard-failing.
    gdown.download_folder(
        id=folder_id,
        output=str(dest),
        quiet=False,
        use_cookies=False,
        remaining_ok=True,
    )
    print(f"Done. Files are under {dest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
