"""GET /files/{bucket}/{path} — regression test for serving a locally-stored
blob whose original filename contains a non-Latin-1 character (a smart
quote, in this case), which used to crash Content-Disposition header
encoding with a raw UnicodeEncodeError (2026-08-31).
"""

import uuid

import pytest

from app.services import storage_local


@pytest.mark.asyncio
async def test_serve_file_with_unicode_filename_in_path(client):
    bucket = f"test-bucket-{uuid.uuid4().hex[:8]}"
    # U+2019 RIGHT SINGLE QUOTATION MARK — not Latin-1-encodable, exactly the
    # character that broke the old single-parameter Content-Disposition header.
    filename = "Ru’ya Space Race - Implementation Plan.pdf"
    path = f"{uuid.uuid4()}/{filename}"
    await storage_local.upload_to_path(bucket, path, b"%PDF-1.4 fake pdf bytes", "application/pdf")

    url = await storage_local.get_signed_url(bucket, path)
    # get_signed_url returns an absolute URL (BASE_URL + /files/...) — strip
    # the base so the test client's ASGI transport hits the right path.
    relative = url.split("/files/", 1)[1]

    resp = await client.get(f"/files/{relative}")
    assert resp.status_code == 200, resp.text
    assert resp.content == b"%PDF-1.4 fake pdf bytes"

    disposition = resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "Ru" in disposition and "ya Space Race" in disposition


@pytest.mark.asyncio
async def test_serve_file_public_bucket_without_signatures(client):
    bucket = "lms-quiz-images"
    filename = "Q03.png"
    await storage_local.upload_to_path(bucket, filename, b"\x89PNG\r\n\x1a\nfake png bytes", "image/png")

    # Public buckets do not require exp and sig
    resp = await client.get(f"/files/{bucket}/{filename}")
    assert resp.status_code == 200, resp.text
    assert resp.content == b"\x89PNG\r\n\x1a\nfake png bytes"
    assert resp.headers["content-type"] == "image/png"

