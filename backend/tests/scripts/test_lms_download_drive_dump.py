"""LM1-9 — the Drive folder ID extraction is the one piece of this script
that's worth pinning: get it wrong and the operator downloads the wrong
folder (or gets a confusing 404 from Drive) instead of a clear local error.
No network test here — gdown itself is a thin wrapper over Drive's own
folder-listing endpoint, not ours to re-test.
"""

import pytest

from scripts.lms_download_drive_dump import _extract_folder_id


def test_extracts_id_from_a_full_share_link():
    url = "https://drive.google.com/drive/folders/1a2B3c4D5e6F7g8H9i0JklMnoPQRstuVW?usp=sharing"
    assert _extract_folder_id(url) == "1a2B3c4D5e6F7g8H9i0JklMnoPQRstuVW"


def test_accepts_a_bare_folder_id():
    bare = "1a2B3c4D5e6F7g8H9i0JklMnoPQRstuVW"
    assert _extract_folder_id(bare) == bare


def test_rejects_garbage_input():
    with pytest.raises(ValueError, match="Couldn't find a Drive folder ID"):
        _extract_folder_id("not-a-drive-link")
