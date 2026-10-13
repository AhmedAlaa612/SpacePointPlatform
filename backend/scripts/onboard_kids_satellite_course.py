"""Onboard the Kids Satellite Course into the LMS from the VPS.

This script runs on the VPS (or locally with access to the API and Drive token):
1. Authenticates against Google Drive headlessly using a refresh token (e.g. `fresh_token.json`).
2. Downloads the 9 course videos, 27 quiz diagram images, and questions spreadsheet.
3. Uploads the quiz images to the LMS public storage bucket (`lms-quiz-images`) via `POST /lms/admin/quiz-images`.
4. Parses the spreadsheet and attaches the diagrams, explanations, and options to each question.
5. Drives the LMS Admin API to create the Course, 3 Modules, Video items, and Quiz items.
6. Streams the video MP4s to `POST /lms/admin/items/{id}/video` so `spacepoint-worker-video`
   can transcode them to HLS and push to Cloudflare R2 in the background.

USAGE (on the VPS):
    python -m scripts.onboard_kids_satellite_course \
        --token /path/to/fresh_token.json \
        --email admin@spacepoint.ae --password <ADMIN_PASS> \
        [--dry-run]

IDEMPOTENCY:
    Records created course/module/item/image IDs in `.kids_course_manifest.json`
    so re-running after an interruption resumes safely without duplicating content.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

import openpyxl
import requests

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Google Drive folder IDs for the Kids course
DRIVE_VIDEOS_FOLDER_ID = "1fYZysn-z9XF0W9u3EbpNP37zsSbrzCVu"  # LMS videos in mp4
DRIVE_IMAGES_FOLDER_ID = "15qM2sRg6lRDUGLw0iVfbwrfC1OG6p_y5"  # Test Qs -> Images folder
DRIVE_EXCEL_FOLDER_ID  = "1iPr1bFN3ix3RLp6KcckojrJJeYoI2XtU"  # Questions bank excel

_OPTION_COLUMNS = ["Option A", "Option B", "Option C", "Option D"]
_CORRECT_LETTER_TO_INDEX = {"A": 0, "B": 1, "C": 2, "D": 3}


def _clean_option_text(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw).strip()


class GoogleDriveClient:
    def __init__(self, token_path: Path):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not token_path.exists():
            raise FileNotFoundError(f"Drive token file not found at: {token_path}")

        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_path.write_text(creds.to_json())
            else:
                raise RuntimeError(f"Drive credentials in {token_path} are invalid and cannot be refreshed.")
        self.service = build("drive", "v3", credentials=creds)

    def list_children(self, folder_id: str) -> list[dict]:
        items: list[dict] = []
        page_token = None
        while True:
            resp = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageToken=page_token,
                pageSize=100,
            ).execute()
            items.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return items

    def download_file(self, file_id: str, dest: Path) -> None:
        from googleapiclient.http import MediaIoBaseDownload

        dest.parent.mkdir(parents=True, exist_ok=True)
        request = self.service.files().get_media(fileId=file_id)
        with io.FileIO(dest, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()


class LmsAdminClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    @classmethod
    def login(cls, base_url: str, email: str, password: str) -> "LmsAdminClient":
        url = f"{base_url.rstrip('/')}/auth/login"
        resp = requests.post(url, json={"email": email, "password": password})
        resp.raise_for_status()
        return cls(base_url, resp.json()["access_token"])

    def create_course(self, title: str, description: str = "") -> str:
        resp = self.session.post(
            f"{self.base_url}/lms/admin/courses",
            json={"title": title, "description": description},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def create_module(self, course_id: str, title: str, position: int) -> str:
        resp = self.session.post(
            f"{self.base_url}/lms/admin/courses/{course_id}/modules",
            json={"title": title, "position": position},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def create_item(
        self, module_id: str, *, kind: str, title: str | None = None, content: dict | None = None,
    ) -> str:
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

    def upload_quiz_image(self, image_path: Path) -> str:
        """Uploads a quiz diagram to /lms/admin/quiz-images and returns the served URL."""
        with open(image_path, "rb") as fh:
            resp = self.session.post(
                f"{self.base_url}/lms/admin/quiz-images",
                files={"file": (image_path.name, fh, "image/png")},
            )
        resp.raise_for_status()
        return resp.json()["url"]

    def reorder_items(self, module_id: str, item_ids: list[str]) -> None:
        resp = self.session.post(
            f"{self.base_url}/lms/admin/modules/{module_id}/items/reorder",
            json={"item_ids": item_ids},
        )
        resp.raise_for_status()


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True))


def _download_all_assets(drive: GoogleDriveClient, staging_dir: Path) -> dict[str, Path]:
    """Downloads videos, images, and excel sheet into staging_dir, skipping matching files."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    videos_dir = staging_dir / "videos"
    images_dir = staging_dir / "images"
    excel_dir  = staging_dir / "excel"

    print("\n--- 1. Syncing Videos from Google Drive ---")
    video_files = drive.list_children(DRIVE_VIDEOS_FOLDER_ID)
    for vf in video_files:
        name = vf["name"]
        target = videos_dir / name
        size = int(vf.get("size", 0) or 0)
        if target.exists() and size and target.stat().st_size == size:
            print(f"  [skip] {name} ({size / (1024*1024):.1f} MB already on disk)")
        else:
            print(f"  [download] {name} ({size / (1024*1024):.1f} MB)...")
            drive.download_file(vf["id"], target)

    print("\n--- 2. Syncing Images from Google Drive ---")
    image_files = drive.list_children(DRIVE_IMAGES_FOLDER_ID)
    drive_id_to_image_path: dict[str, Path] = {}
    for imf in image_files:
        name = imf["name"]
        target = images_dir / name
        size = int(imf.get("size", 0) or 0)
        if target.exists() and size and target.stat().st_size == size:
            print(f"  [skip] {name} (already on disk)")
        else:
            print(f"  [download] {name}...")
            drive.download_file(imf["id"], target)
        drive_id_to_image_path[imf["id"]] = target
        # Also map filename stem
        drive_id_to_image_path[target.name] = target

    print("\n--- 3. Syncing Excel Spreadsheet from Google Drive ---")
    excel_files = drive.list_children(DRIVE_EXCEL_FOLDER_ID)
    excel_path: Path | None = None
    for ef in excel_files:
        if ef["name"].endswith(".xlsx"):
            target = excel_dir / ef["name"]
            size = int(ef.get("size", 0) or 0)
            if not target.exists() or (size and target.stat().st_size != size):
                print(f"  [download] {ef['name']}...")
                drive.download_file(ef["id"], target)
            else:
                print(f"  [skip] {ef['name']} (already on disk)")
            excel_path = target
            break

    if not excel_path or not excel_path.exists():
        raise FileNotFoundError("Could not find or download Satellite Quiz Excel file.")

    return {
        "videos_dir": videos_dir,
        "images_dir": images_dir,
        "excel_path": excel_path,
        "drive_id_to_image_path": drive_id_to_image_path,
    }


def _parse_quiz_questions(
    excel_path: Path,
    image_urls_by_drive_id: dict[str, str],
) -> dict[str, list[dict]]:
    """Reads Excel and produces questions grouped by reference (e.g. M1-CH1, M2-CH2)."""
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    sheet_name = "Picture Questions Only" if "Picture Questions Only" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))[1:]  # skip header

    grouped: dict[str, list[dict]] = {}
    for r in rows:
        if not r or not r[0]:
            continue
        mod, ch, ref, topic, qnum, prompt, qtype, a, b, c, d, correct, exp, img_file, _, drive_url = r[:16]
        options_raw = [a, b, c, d]
        correct_letter = str(correct).strip().upper()
        correct_index = _CORRECT_LETTER_TO_INDEX.get(correct_letter)
        if correct_index is None:
            print(f"  [WARN] Unparsed correct answer '{correct}' for question: {prompt}")

        # Extract drive ID from URL
        drive_id_match = re.search(r"[-\w]{25,}", str(drive_url or ""))
        drive_id = drive_id_match.group(0) if drive_id_match else None

        img_filename = Path(str(img_file)).name if img_file else None
        image_url = None
        if drive_id and drive_id in image_urls_by_drive_id:
            image_url = image_urls_by_drive_id[drive_id]
        elif img_filename and img_filename in image_urls_by_drive_id:
            image_url = image_urls_by_drive_id[img_filename]

        options = [
            {"text": _clean_option_text(opt), "is_correct": i == correct_index}
            for i, opt in enumerate(options_raw)
            if opt is not None and str(opt).strip() != ""
        ]

        question_dict = {
            "prompt": str(prompt).strip(),
            "explanation": str(exp).strip() if exp else None,
            "options": options,
        }
        if image_url:
            question_dict["image_url"] = image_url

        ref_key = str(ref).strip().upper()
        grouped.setdefault(ref_key, []).append(question_dict)

    return grouped


def run_onboarding(
    *,
    token_path: Path,
    api_base_url: str,
    email: str | None,
    password: str | None,
    staging_dir: Path,
    course_title: str,
    course_description: str,
    dry_run: bool,
) -> None:
    manifest_path = staging_dir / ".kids_course_manifest.json"
    manifest = Manifest(manifest_path)

    print(f"Connecting to Google Drive with token: {token_path}")
    drive = GoogleDriveClient(token_path)

    # 1. Download files
    assets = _download_all_assets(drive, staging_dir)
    videos_dir: Path = assets["videos_dir"]
    images_dir: Path = assets["images_dir"]
    excel_path: Path = assets["excel_path"]
    drive_id_to_image_path: dict[str, Path] = assets["drive_id_to_image_path"]

    # 2. Login to API if not dry-run
    client: LmsAdminClient | None = None
    if not dry_run:
        if not (email and password):
            raise ValueError("--email and --password (or env LMS_IMPORT_EMAIL/LMS_IMPORT_PASSWORD) required.")
        print(f"\nLogging in to LMS Admin API at {api_base_url} as {email}...")
        client = LmsAdminClient.login(api_base_url, email, password)

    # 3. Upload images and resolve URLs
    print("\n--- 4. Hosting Quiz Diagram Images ---")
    image_urls: dict[str, str] = {}
    for drive_id_or_name, img_path in drive_id_to_image_path.items():
        cache_key = f"img_url:{img_path.name}"
        stored_url = manifest.get(cache_key)
        if stored_url:
            image_urls[drive_id_or_name] = stored_url
        elif not dry_run and client:
            print(f"  [upload] {img_path.name} to /lms/admin/quiz-images...")
            url = client.upload_quiz_image(img_path)
            manifest.set(cache_key, url)
            image_urls[drive_id_or_name] = url
        else:
            image_urls[drive_id_or_name] = f"/files/lms-quiz-images/{img_path.name}"

    # 4. Parse Excel with hosted image URLs
    print("\n--- 5. Parsing Quiz Questions & Attaching Diagrams ---")
    quiz_by_ref = _parse_quiz_questions(excel_path, image_urls)
    for ref, qs in sorted(quiz_by_ref.items()):
        img_count = sum(1 for q in qs if q.get("image_url"))
        print(f"  {ref}: {len(qs)} question(s) ({img_count} with diagrams)")

    # 5. Course Structure Definition
    # 3 Modules with chapters mapped to videos and quizzes
    COURSE_PLAN = [
        {
            "module_pos": 1,
            "module_title": "Module 1: Introduction to Satellites",
            "items": [
                {
                    "kind": "video",
                    "title": "Chapter 1: Satellite Motion & Gravity",
                    "video_filename": "Copy of Module 1 chapter 1.mp4",
                },
                {
                    "kind": "quiz",
                    "title": "Chapter 1: Satellite Motion — Quiz",
                    "quiz_ref": "M1-CH1",
                },
                {
                    "kind": "video",
                    "title": "Chapter 2: Satellite Orbits & TV Satellites",
                    "video_filename": "Copy of Module 1 chapter 2.mp4",
                },
                {
                    "kind": "quiz",
                    "title": "Chapter 2: Satellite Orbits & TV Satellites — Quiz",
                    "quiz_ref": "M1-CH2",
                },
                {
                    "kind": "video",
                    "title": "Chapter 3: What is a CubeSat?",
                    "video_filename": "Copy of Module 1 chapter 3.mp4",
                },
                {
                    "kind": "quiz",
                    "title": "Chapter 3: What is a CubeSat? — Quiz",
                    "quiz_ref": "M1-CH3",
                },
            ],
        },
        {
            "module_pos": 2,
            "module_title": "Module 2: Satellite Subsystems",
            "items": [
                {
                    "kind": "video",
                    "title": "Chapter 1: The Satellite's Brain & CDHS",
                    "video_filename": "Copy of Module 2 Chapter 1.mp4",
                },
                {
                    "kind": "quiz",
                    "title": "Chapter 1: Satellite Brain & CDHS — Quiz",
                    "quiz_ref": "M2-CH1",
                },
                {
                    "kind": "video",
                    "title": "Chapter 2: Satellite Power & Solar Panels",
                    "video_filename": "Copy of Module 2 Chapter 2.mp4",
                },
                {
                    "kind": "quiz",
                    "title": "Chapter 2: Satellite Power & Solar Panels — Quiz",
                    "quiz_ref": "M2-CH2",
                },
                {
                    "kind": "video",
                    "title": "Chapter 3: Attitude Determination & Control (ADCS)",
                    "video_filename": "Copy of Module 2 Chapter 3.mp4",
                },
                {
                    "kind": "quiz",
                    "title": "Chapter 3: ADCS & Reaction Wheels — Quiz",
                    "quiz_ref": "M2-CH3",
                },
                {
                    "kind": "video",
                    "title": "Chapter 4: Thermal & Structures",
                    "video_filename": "Copy of Module 2Chapter 4.mp4",
                },
            ],
        },
        {
            "module_pos": 3,
            "module_title": "Module 3: Space Missions & Orbits",
            "items": [
                {
                    "kind": "video",
                    "title": "Chapter 1: Satellite Communication & Antennas",
                    "video_filename": "Copy of Module 3 Chapter1.mp4",
                },
                {
                    "kind": "quiz",
                    "title": "Chapter 1: Satellite Communication — Quiz",
                    "quiz_ref": "M3-CH1",
                },
                {
                    "kind": "video",
                    "title": "Chapter 2: Earth Observation & Payloads",
                    "video_filename": "Copy of  Module 3 Chapter2.mp4",
                },
                {
                    "kind": "quiz",
                    "title": "Chapter 2: Earth Observation & Payloads — Quiz",
                    "quiz_ref": "M3-CH2",
                },
                {
                    "kind": "video",
                    "title": "Chapter 3: Weather Satellites & Space Operations",
                    "video_filename": "Copy of Module 3 Chapter3.mp4",
                },
            ],
        },
    ]

    print("\n--- 6. Creating Course & Curriculum Structure ---")
    course_key = f"course:{course_title}"
    course_id = manifest.get(course_key)
    if course_id:
        print(f"[course exists] {course_title!r} ({course_id})")
    elif not dry_run and client:
        print(f"[create course] {course_title!r}...")
        course_id = client.create_course(course_title, course_description)
        manifest.set(course_key, course_id)
        print(f"  Created course id: {course_id}")
    else:
        course_id = "<dry-run-course-id>"
        print(f"[dry-run course] {course_title!r}")

    for mod_data in COURSE_PLAN:
        m_pos = mod_data["module_pos"]
        m_title = mod_data["module_title"]
        module_key = f"module:{course_title}:M{m_pos}"
        module_id = manifest.get(module_key)

        if module_id:
            print(f"\n[module exists] {m_title!r} ({module_id})")
        elif not dry_run and client:
            print(f"\n[create module] {m_title!r} (position {m_pos})...")
            module_id = client.create_module(course_id, m_title, m_pos)
            manifest.set(module_key, module_id)
        else:
            module_id = f"<dry-run-mod-{m_pos}>"
            print(f"\n[dry-run module] {m_title!r} (position {m_pos})")

        module_item_ids: list[str] = []
        for item_data in mod_data["items"]:
            kind = item_data["kind"]
            title = item_data["title"]
            item_key = f"item:{course_title}:M{m_pos}:{title}"
            item_id = manifest.get(item_key)

            if kind == "video":
                v_name = item_data["video_filename"]
                v_path = videos_dir / v_name
                if not v_path.exists():
                    print(f"  [ERROR] Video file not found: {v_path}")
                    continue

                if item_id:
                    print(f"  [skip video item] {title!r} already imported ({item_id})")
                    module_item_ids.append(item_id)
                    continue

                print(f"  [new video item] {title!r} -> uploading {v_name} ({v_path.stat().st_size / (1024*1024):.1f} MB)...")
                if not dry_run and client:
                    item_id = client.create_item(module_id, kind="video", title=title)
                    manifest.set(item_key, item_id)
                    client.upload_video(item_id, v_path)
                    print(f"    Uploaded and queued for transcoding: {item_id}")
                    module_item_ids.append(item_id)

            elif kind == "quiz":
                ref = item_data["quiz_ref"]
                questions = quiz_by_ref.get(ref, [])
                if item_id:
                    print(f"  [skip quiz item] {title!r} already imported ({item_id})")
                    module_item_ids.append(item_id)
                    continue

                print(f"  [new quiz item] {title!r} ({len(questions)} questions)...")
                if not dry_run and client:
                    content = {
                        "pass_threshold": 0,  # Practice quiz - pass on completion
                        "questions": questions,
                    }
                    item_id = client.create_item(module_id, kind="quiz", title=title, content=content)
                    manifest.set(item_key, item_id)
                    print(f"    Created quiz item: {item_id}")
                    module_item_ids.append(item_id)

        if not dry_run and client and len(module_item_ids) == len(mod_data["items"]):
            try:
                client.reorder_items(module_id, module_item_ids)
                print(f"  [reordered] items in {m_title!r}")
            except Exception as exc:
                print(f"  [WARN] Failed to reorder items in module {m_pos}: {exc}")

    print("\n========================================================")
    if dry_run:
        print("Dry run completed successfully! No changes were made.")
    else:
        print("Course onboarding completed successfully!")
        print(f"Course ID: {course_id}")
        print("Background video workers on the VPS are transcoding videos to R2.")
    print("========================================================\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--token",
        default=os.environ.get("LMS_DRIVE_TOKEN_PATH") or "fresh_token.json",
        help="Path to Google Drive OAuth authorized user token JSON (default: fresh_token.json)",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://localhost:8000",
        help="API Base URL (default: http://localhost:8000 on VPS)",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("LMS_IMPORT_EMAIL"),
        help="Admin/Staff login email for LMS API",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("LMS_IMPORT_PASSWORD"),
        help="Admin/Staff login password for LMS API",
    )
    parser.add_argument(
        "--staging-dir",
        default=os.environ.get("LMS_STAGING_DIR") or "kids_course_staging",
        help="Local staging directory for downloaded course media",
    )
    parser.add_argument(
        "--title",
        default="Satellite Engineering for Kids",
        help="Title of the new course",
    )
    parser.add_argument(
        "--description",
        default="An engaging introduction to satellite subsystems, orbits, and space missions designed for young learners.",
        help="Description of the course",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate Drive files, images, and Excel without writing to LMS API",
    )
    args = parser.parse_args()

    token_path = Path(args.token).resolve()
    # Also check Downloads folder if not found
    if not token_path.exists():
        fallback = Path.home() / "Downloads" / "fresh_token.json"
        if fallback.exists():
            token_path = fallback

    staging_dir = Path(args.staging_dir).resolve()

    try:
        run_onboarding(
            token_path=token_path,
            api_base_url=args.api_base_url,
            email=args.email,
            password=args.password,
            staging_dir=staging_dir,
            course_title=args.title,
            course_description=args.description,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"\n[ERROR] Onboarding failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
