"""Pull a privately-shared Google Drive folder to local disk via OAuth
(2026-08-09) — the private-folder sibling of `lms_download_drive_dump.py`.

WHY THIS EXISTS
    `lms_download_drive_dump.py` (gdown, no auth) only works on a folder
    shared "Anyone with the link". The boss's course-content folder turned
    out to be shared with the operator's specific Google account instead —
    gdown gets a permission error on that. This script authenticates as
    the operator's own account (OAuth, "Desktop app" client), so it can see
    whatever that account can already see in Drive, no re-sharing needed.

    Mirrors the whole folder tree onto local disk, preserving structure —
    course folders as subfolders, video files, the `*Content and
    Questions.xlsx` sheet, whatever else is in there. This script only gets
    the bytes onto disk; turning them into courses is `lms_import_drive_dump.py`.

SETUP (one-time — see the operator's own notes for the full Cloud Console walkthrough)
    1. Google Cloud Console: enable the Drive API, create an OAuth 2.0
       "Desktop app" client, download its JSON as `credentials.json`.
    2. First run of this script opens a browser for a one-time consent
       screen, then caches a refresh token at `--token-path` (default
       `.lms_drive_token.json`, gitignored) — every run after that is
       silent, no browser needed. That cached token can be copied to the
       VPS to run headlessly there too (no login flow required on a box
       with no browser) — see the module docstring in
       `lms_import_drive_dump.py` for the VPS-side sequel.

USAGE
    python -m scripts.lms_drive_oauth_download <folder_url_or_id> \
        --credentials path/to/credentials.json [--dest DIR] [--token-path PATH]

IDEMPOTENCY
    Skips a file already on disk with a matching size (same discipline as
    `lms_download_drive_dump.py`) — a re-run after an interruption resumes
    rather than re-downloading everything.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

FOLDER_ID_RE = re.compile(r"[-\w]{25,}")
_FOLDER_MIME = "application/vnd.google-apps.folder"
# Google-native docs (Sheets/Docs/Slides) have no direct byte content —
# export them to a real file format instead of downloading them raw.
_EXPORT_MIME = {
    "application/vnd.google-apps.spreadsheet":
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.document":
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.presentation":
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
}

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _extract_folder_id(url_or_id: str) -> str:
    match = FOLDER_ID_RE.search(url_or_id)
    if not match:
        raise ValueError(
            f"Couldn't find a Drive folder ID in {url_or_id!r} — pass the folder's "
            "share link (drive.google.com/drive/folders/<id>) or the bare ID."
        )
    return match.group(0)


def _get_credentials(credentials_path: Path | None, token_path: Path):
    """`credentials_path` is only ever read on the *first* consent flow — a
    cached token already carries its own client_id/secret (baked in by
    `to_json()`), so a plain refresh needs nothing but the token file. That
    matters on the VPS: copy over `token_path`'s file alone (no browser
    there to complete a fresh consent) and this never touches
    `credentials_path` at all, so it doesn't need to exist there."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path or not credentials_path.exists():
                raise SystemExit(
                    "error: no valid cached token at "
                    f"{token_path} and --credentials wasn't given (or doesn't exist) — "
                    "pass --credentials path/to/credentials.json for the first-time consent flow, "
                    "or copy over an already-authorized token file instead."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return creds


def _list_children(service, folder_id: str) -> list[dict]:
    items: list[dict] = []
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageToken=page_token,
            pageSize=200,
        ).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def _download_file(service, file_id: str, mime_type: str, dest: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    if mime_type in _EXPORT_MIME:
        export_mime, suffix = _EXPORT_MIME[mime_type]
        if dest.suffix.lower() != suffix:
            dest = dest.with_suffix(suffix)
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=file_id)

    buffer = io.FileIO(dest, "wb")
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.close()


def _name_is_wanted(name: str, only_files: set[str] | None) -> bool:
    return only_files is None or name.strip().lower() in only_files


def _walk_and_download(
    service, folder_id: str, dest: Path, *, dry_run: bool, only_files: set[str] | None = None,
) -> None:
    """`only_files`, when given, is a set of exact (case-insensitive) file
    names — everything else in the folder is skipped without downloading a
    byte. Folders themselves are always traversed (the filter only applies
    to files) since the point is finding specific files that might sit
    alongside a lot of ones you don't want yet — e.g. one video + the
    course's quiz spreadsheet, not the other 8 videos."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in _list_children(service, folder_id):
        name = item["name"]
        mime_type = item["mimeType"]
        if mime_type == _FOLDER_MIME:
            print(f"[dir]  {dest / name}")
            if not dry_run:
                _walk_and_download(service, item["id"], dest / name, dry_run=dry_run, only_files=only_files)
            continue

        if not _name_is_wanted(name, only_files):
            print(f"[skip] {dest / name} (not in --only-file list)")
            continue

        target = dest / name
        remote_size = int(item.get("size", 0) or 0)
        if target.exists() and remote_size and target.stat().st_size == remote_size:
            print(f"[skip] {target} (already on disk, size matches)")
            continue

        print(f"[file] {target}")
        if not dry_run:
            _download_file(service, item["id"], mime_type, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("SETUP")[0])
    parser.add_argument("folder", help="Drive folder URL or ID (must be visible to the OAuth account)")
    parser.add_argument(
        "--credentials", default=None,
        help="Path to the OAuth client JSON from Cloud Console — only needed for the first-time "
             "consent flow; not read at all once --token-path already has a valid cached token "
             "(e.g. copied over from a machine that already did the consent flow)",
    )
    parser.add_argument("--dest", default="lms-drive-dump", help="Destination directory")
    parser.add_argument("--token-path", default=".lms_drive_token.json", help="Where to cache the refresh token")
    parser.add_argument("--dry-run", action="store_true", help="List what would be downloaded, don't fetch bytes")
    parser.add_argument(
        "--only-file", action="append", dest="only_files", default=None, metavar="NAME",
        help="Download only files with this exact name (repeatable) — everything else in the "
             "folder is skipped, no bytes pulled. E.g. one video + the quiz spreadsheet, not the "
             "whole course, to go easy on a slow connection while testing.",
    )
    args = parser.parse_args()

    try:
        folder_id = _extract_folder_id(args.folder)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    credentials_path = Path(args.credentials) if args.credentials else None

    try:
        from googleapiclient.discovery import build
    except ImportError:
        print(
            "error: google-api-python-client / google-auth-oauthlib aren't installed. "
            "Run `pip install -r requirements.txt` first.",
            file=sys.stderr,
        )
        return 1

    creds = _get_credentials(credentials_path, Path(args.token_path))
    service = build("drive", "v3", credentials=creds)

    only_files = {n.strip().lower() for n in args.only_files} if args.only_files else None

    dest = Path(args.dest)
    print(f"Drive folder ID: {folder_id}")
    print(f"Destination:     {dest.resolve()}")
    if only_files:
        print(f"Only files:      {', '.join(sorted(only_files))}")
    _walk_and_download(service, folder_id, dest, dry_run=args.dry_run, only_files=only_files)
    print("Done." if not args.dry_run else "Dry run complete — nothing downloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
