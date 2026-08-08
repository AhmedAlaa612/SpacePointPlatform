"""lms_drive_oauth_download — folder-ID extraction, same pinning rationale
as test_lms_download_drive_dump.py (get this wrong, the operator downloads
the wrong folder). No network/OAuth here — that needs real credentials and
isn't this codebase's to fake convincingly.
"""

import pytest

from scripts.lms_drive_oauth_download import _extract_folder_id, _name_is_wanted


def test_extracts_id_from_a_full_share_link():
    url = "https://drive.google.com/drive/folders/1a2B3c4D5e6F7g8H9i0JklMnoPQRstuVW?usp=sharing"
    assert _extract_folder_id(url) == "1a2B3c4D5e6F7g8H9i0JklMnoPQRstuVW"


def test_accepts_a_bare_folder_id():
    bare = "1a2B3c4D5e6F7g8H9i0JklMnoPQRstuVW"
    assert _extract_folder_id(bare) == bare


def test_rejects_garbage_input():
    with pytest.raises(ValueError, match="Couldn't find a Drive folder ID"):
        _extract_folder_id("not-a-drive-link")


def test_no_filter_wants_everything():
    assert _name_is_wanted("9- Challenges and Future.mp4", None) is True


def test_only_files_filter_is_case_insensitive_and_exact():
    only = {"1- intro-1.mp4", "intro - content and questions"}
    assert _name_is_wanted("1- Intro-1.mp4", only) is True
    assert _name_is_wanted("Intro - Content and Questions", only) is True
    assert _name_is_wanted("2- What is a satellite-2.mp4", only) is False
