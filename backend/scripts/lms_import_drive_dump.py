"""Turn a downloaded Drive course dump into real LMS content (2026-08-09) —
the second half of LM1-9, the manifest-driven importer described in
docs/LMS_EXECUTION_PLAN.md §8b. Drives the `/lms/admin/*` authoring API
(same one `pages/lms-authoring/*` uses) rather than writing to the DB
directly, so position/conflict/content-validation logic already in
`routers/lms/admin.py` is reused, not reimplemented.

FOLDER CONTRACT (§8b, operator-confirmed 2026-08-08)
    <dump-dir>/
      <N>- <Course Name>/                    one Course per top-level folder
        <N>- <Video Title>.mp4                one CourseModule + video item
        ...
        <Course> - Content and Questions.xlsx  quiz questions, one sheet
        (anything else in the folder is ignored — e.g. a notes/talking-points doc)

    The Excel: columns `Video Name | Video Description | Question Text |
    Option A | Option B | Option C | Option D | Correct Answer`. Rows group
    by `Video Name` (exact match against a video filename in the same
    folder); each video's rows become one `quiz` module item —
    "each module has a video and a quiz" (operator's words), not
    mid-video pop-quizzes — so no timestamp data is needed at all.

WHAT THIS DOES NOT DO
    Doesn't create a `LearningPath` — stringing courses together in order
    is a second pass once more than one course exists and the operator has
    named the path (§8b, still open). This just gets each course itself
    into the catalogue, unpublished, ready for review.

USAGE
    python -m scripts.lms_import_drive_dump <dump-dir> \
        --api-base-url http://localhost:8000 \
        --email dev-admin@spacepoint.ae --password devadmin123 \
        [--only "1- Introduction"] [--dry-run]

    Credentials can also come from LMS_IMPORT_EMAIL / LMS_IMPORT_PASSWORD
    env vars instead of the command line (keeps them out of shell history).

IDEMPOTENCY
    `<dump-dir>/.lms_import_manifest.json` maps folder/file name -> created
    course/module/item UUID. A re-run skips anything already in the
    manifest rather than duplicating it — this is a first-pass importer,
    not a sync engine; fixing a typo in the Excel after the first import
    means editing the course by hand via /lms-authoring, same as any other
    authored content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import openpyxl
import requests

_LEADING_NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[-–—.]\s*")
_TRAILING_NUMBER_RE = re.compile(r"[\s\-–—]+(\d+(?:\.\d+)?)\s*$")
_OPTION_COLUMNS = ["Option A", "Option B", "Option C", "Option D"]
_CORRECT_LETTER_TO_COLUMN = {"A": 0, "B": 1, "C": 2, "D": 3}


def _clean_title(name: str) -> str:
    """Strip the leading "N- " / "N.M- " ordering prefix and, for video
    files, the extension. The operator's own words: the numbers are "just in
    the drive to let me know the sequence" — never meant to show up in a
    title anywhere.

    Some filenames redundantly repeat the same number at the *end* too
    (e.g. "1- Intro-1.mp4", "2- What is a satellite-2.mp4") — stripped only
    when the trailing number is the exact same one just stripped from the
    front, so a title that genuinely ends in a number (e.g. "Sputnik 1")
    is never touched.

    Checks for ".mp4" specifically rather than "any dot in the name" —
    `Path(name).stem` mis-happily treats course folders named like
    "2.1 - CDHS Continued" as a file with extension ".1 - CDHS Continued",
    stripping everything after the first dot."""
    stem = name[:-4] if name.lower().endswith(".mp4") else name

    leading_match = _LEADING_NUMBER_RE.match(stem)
    stem = _LEADING_NUMBER_RE.sub("", stem, count=1).strip()

    if leading_match:
        trailing_match = _TRAILING_NUMBER_RE.search(stem)
        if trailing_match and trailing_match.group(1) == leading_match.group(1):
            stem = stem[:trailing_match.start()].strip()

    return stem


def _leading_number(name: str) -> float:
    match = _LEADING_NUMBER_RE.match(name)
    return float(match.group(1)) if match else 0.0


def _option_text(raw) -> str:
    """openpyxl hands back numeric-looking options (e.g. a year) as floats —
    `1957.0`, not `"1957"`. Cast cleanly so students never see the `.0`."""
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


def _load_questions_by_video(xlsx_path: Path) -> dict[str, list[dict]]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(min_row=2, values_only=True))  # skip header

    by_video: dict[str, list[dict]] = {}
    for row in rows:
        if not row or not row[0]:
            continue
        video_name, _description, prompt, opt_a, opt_b, opt_c, opt_d, correct = row[:8]
        options_raw = [opt_a, opt_b, opt_c, opt_d]
        correct_index = _CORRECT_LETTER_TO_COLUMN.get(str(correct).strip().upper())
        question = {
            "prompt": str(prompt).strip(),
            "options": [
                {"text": _option_text(opt), "is_correct": i == correct_index}
                for i, opt in enumerate(options_raw)
                if opt is not None
            ],
        }
        by_video.setdefault(str(video_name).strip(), []).append(question)
    return by_video


class LmsAdminClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    @classmethod
    def login(cls, base_url: str, email: str, password: str) -> "LmsAdminClient":
        resp = requests.post(f"{base_url.rstrip('/')}/auth/login", json={"email": email, "password": password})
        resp.raise_for_status()
        return cls(base_url, resp.json()["access_token"])

    def create_course(self, title: str) -> str:
        resp = self.session.post(f"{self.base_url}/lms/admin/courses", json={"title": title})
        resp.raise_for_status()
        return resp.json()["id"]

    def create_module(self, course_id: str, title: str, position: int) -> str:
        resp = self.session.post(
            f"{self.base_url}/lms/admin/courses/{course_id}/modules",
            json={"title": title, "position": position},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def create_item(self, module_id: str, *, kind: str, title: str | None = None, content: dict | None = None) -> str:
        resp = self.session.post(
            f"{self.base_url}/lms/admin/modules/{module_id}/items",
            json={"kind": kind, "title": title, "content": content or {}},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def upload_video(self, item_id: str, video_path: Path) -> dict:
        with open(video_path, "rb") as fh:
            resp = self.session.post(
                f"{self.base_url}/lms/admin/items/{item_id}/video",
                files={"file": (video_path.name, fh, "video/mp4")},
            )
        resp.raise_for_status()
        return resp.json()


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True))


def _import_course(client: LmsAdminClient, manifest: Manifest, course_dir: Path, *, dry_run: bool) -> None:
    course_key = f"course:{course_dir.name}"
    course_id = manifest.get(course_key)
    if course_id:
        print(f"[skip] course {course_dir.name!r} already imported ({course_id})")
    else:
        title = _clean_title(course_dir.name)
        print(f"[new]  course {course_dir.name!r} -> {title!r}")
        if not dry_run:
            course_id = client.create_course(title)
            manifest.set(course_key, course_id)
        else:
            course_id = "<dry-run>"

    videos = sorted(
        (p for p in course_dir.iterdir() if p.suffix.lower() == ".mp4"),
        key=lambda p: _leading_number(p.name),
    )
    xlsx_candidates = list(course_dir.glob("*.xlsx"))
    questions_by_video = _load_questions_by_video(xlsx_candidates[0]) if xlsx_candidates else {}
    if not xlsx_candidates:
        print(f"  (no *.xlsx found in {course_dir.name} — modules will have a video but no quiz)")

    for position, video_path in enumerate(videos, start=1):
        module_key = f"module:{course_dir.name}/{video_path.name}"
        module_id = manifest.get(module_key)
        if module_id:
            print(f"  [skip] module {video_path.name!r} already imported ({module_id})")
            continue

        module_title = _clean_title(video_path.name)
        print(f"  [new]  module {position}: {video_path.name!r} -> {module_title!r}")
        if dry_run:
            questions = questions_by_video.get(video_path.name, [])
            print(f"         video: {video_path.name} ({video_path.stat().st_size / 1_048_576:.1f} MB)")
            print(f"         quiz: {len(questions)} question(s)" if questions else "         quiz: none matched")
            continue

        module_id = client.create_module(course_id, module_title, position)
        manifest.set(module_key, module_id)

        video_item_id = client.create_item(module_id, kind="video", title=module_title)
        manifest.set(f"item:video:{module_key}", video_item_id)
        print(f"         uploading video ({video_path.stat().st_size / 1_048_576:.1f} MB)...")
        client.upload_video(video_item_id, video_path)

        questions = questions_by_video.get(video_path.name, [])
        if questions:
            client.create_item(
                module_id, kind="quiz", title=f"{module_title} — Quiz",
                content={"pass_threshold": 0, "questions": questions},
            )
            print(f"         quiz: {len(questions)} question(s)")
        else:
            print(f"         quiz: no matching rows for {video_path.name!r} in the Excel — skipped")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("USAGE")[0])
    parser.add_argument("dump_dir", help="Local folder containing the downloaded course folders")
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument("--email", default=os.environ.get("LMS_IMPORT_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("LMS_IMPORT_PASSWORD"))
    parser.add_argument("--only", help="Import just one course folder by name (e.g. '1- Introduction')")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, touch nothing")
    args = parser.parse_args()

    dump_dir = Path(args.dump_dir)
    if not dump_dir.is_dir():
        print(f"error: {dump_dir} is not a directory", file=sys.stderr)
        return 1

    if not args.dry_run and not (args.email and args.password):
        print(
            "error: --email/--password (or LMS_IMPORT_EMAIL/LMS_IMPORT_PASSWORD) "
            "are required unless --dry-run",
            file=sys.stderr,
        )
        return 1

    course_dirs = sorted(
        (p for p in dump_dir.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: _leading_number(p.name),
    )
    if args.only:
        course_dirs = [p for p in course_dirs if p.name == args.only]
        if not course_dirs:
            print(f"error: no folder named {args.only!r} directly under {dump_dir}", file=sys.stderr)
            return 1

    manifest = Manifest(dump_dir / ".lms_import_manifest.json")
    client = None
    if not args.dry_run:
        print(f"Logging in to {args.api_base_url} as {args.email}...")
        client = LmsAdminClient.login(args.api_base_url, args.email, args.password)

    for course_dir in course_dirs:
        print(f"\n=== {course_dir.name} ===")
        _import_course(client, manifest, course_dir, dry_run=args.dry_run)

    print("\nDry run complete — nothing was created." if args.dry_run else "\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
