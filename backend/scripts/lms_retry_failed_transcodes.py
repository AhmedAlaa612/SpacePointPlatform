"""Re-upload the source video for any module in a course whose transcode
didn't finish ready — the fix for arq's job_timeout being too short for a
real ffmpeg encode (see backend/app/workers/main.py) doesn't retroactively
fix jobs that already timed out; those rows are stuck (or failed) and need a
fresh upload to re-enqueue transcoding under the corrected timeout.

Matches each module back to its original file in --dump-dir by the module's
position and the file's leading "N- " number — the same convention
lms_import_drive_dump.py uses, so this points at the exact same directory
you already downloaded the course into.

USAGE
    python -m scripts.lms_retry_failed_transcodes \
        --api-base-url http://localhost:8000 \
        --course-name "Introduction" \
        --dump-dir lms-drive-dump \
        --email admin@spacepoint.ae --password '...' \
        [--dry-run]

Credentials can also come from LMS_IMPORT_EMAIL / LMS_IMPORT_PASSWORD env
vars instead of the command line (keeps them out of shell history). Unlike
lms_import_drive_dump.py's --dry-run, login always happens here even in
--dry-run — this script has to read live transcode status from the API to
know what needs retrying, not just reason about local files.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import requests

_LEADING_NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[-–—.]\s*")


def _leading_number(name: str) -> float | None:
    match = _LEADING_NUMBER_RE.match(name)
    return float(match.group(1)) if match else None


def _find_source_file(dump_dir: Path, position: int) -> Path | None:
    candidates = [
        p for p in dump_dir.glob("*.mp4")
        if _leading_number(p.name) == position
    ]
    if len(candidates) > 1:
        print(f"  warning: {len(candidates)} files match position {position}, using {candidates[0].name}", file=sys.stderr)
    return candidates[0] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("USAGE")[0])
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--course-name", required=True, help="Exact course title, e.g. 'Introduction'")
    parser.add_argument("--dump-dir", required=True, help="Folder containing the original <N>- <Title>.mp4 files")
    parser.add_argument("--email", default=os.environ.get("LMS_IMPORT_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("LMS_IMPORT_PASSWORD"))
    parser.add_argument("--dry-run", action="store_true", help="Print what would be re-uploaded, touch nothing")
    args = parser.parse_args()

    dump_dir = Path(args.dump_dir)
    if not dump_dir.is_dir():
        print(f"error: {dump_dir} is not a directory", file=sys.stderr)
        return 1

    if not (args.email and args.password):
        print(
            "error: --email/--password (or LMS_IMPORT_EMAIL/LMS_IMPORT_PASSWORD) are required — "
            "even for --dry-run, since this reads live course/module status from the API",
            file=sys.stderr,
        )
        return 1

    base_url = args.api_base_url.rstrip("/")
    session = requests.Session()
    print(f"Logging in to {base_url} as {args.email}...")
    resp = session.post(f"{base_url}/auth/login", json={"email": args.email, "password": args.password})
    resp.raise_for_status()
    session.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"

    resp = session.get(f"{base_url}/lms/admin/courses")
    resp.raise_for_status()
    course = next((c for c in resp.json() if c["title"] == args.course_name), None)
    if course is None:
        print(f"error: no course titled {args.course_name!r}", file=sys.stderr)
        return 1

    resp = session.get(f"{base_url}/lms/admin/courses/{course['id']}/modules")
    resp.raise_for_status()
    modules = sorted(resp.json(), key=lambda m: m["position"])

    retried = 0
    for module in modules:
        resp = session.get(f"{base_url}/lms/admin/modules/{module['id']}/items")
        resp.raise_for_status()
        video_item = next((i for i in resp.json() if i["kind"] == "video"), None)
        if video_item is None:
            continue

        status = video_item["content"].get("transcode_status")
        if status == "ready":
            continue

        source = _find_source_file(dump_dir, module["position"])
        if source is None:
            print(f"[skip] module {module['position']} ({module['title']!r}, status={status!r}) — no matching file in {dump_dir}")
            continue

        print(f"[retry] module {module['position']} ({module['title']!r}, was {status!r}) <- {source.name} ({source.stat().st_size / 1e6:.1f} MB)")
        retried += 1
        if args.dry_run:
            continue

        with open(source, "rb") as fh:
            resp = session.post(
                f"{base_url}/lms/admin/items/{video_item['id']}/video",
                files={"file": (source.name, fh, "video/mp4")},
            )
        resp.raise_for_status()
        print(f"         -> {resp.json()}")

    print(f"\n{'Would retry' if args.dry_run else 'Retried'} {retried} video(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
