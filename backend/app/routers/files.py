"""GET /files/{bucket}/{path} — serves blobs stored by the LOCAL storage
backend (GO_LIVE §3.A3).

Auth is the HMAC signature itself (no JWT): URLs are minted by
storage_local.get_signed_url() as
    /files/{bucket}/{path}?exp=<unix>&sig=<hex HMAC-SHA256(SECRET_KEY, bucket|path|exp)>
The route rejects bad/expired signatures with 403, then decrypts the Fernet
blob and streams it with a mimetypes-inferred content type.

This router always reads from local disk (it is the serving half of
storage_local), regardless of which backend is currently active — Supabase
URLs never point here.
"""

import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.services import storage_local

router = APIRouter(prefix="/files", tags=["files"])


PUBLIC_BUCKETS: set[str] = {"website-assets", "lms-quiz-images"}


@router.options("/{bucket}/{path:path}")
async def serve_file_options(bucket: str, path: str):
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400",
        },
    )


@router.get("/{bucket}/{path:path}")
async def serve_file(
    bucket: str,
    path: str,
    request: Request,
    exp: int | None = Query(None),
    sig: str | None = Query(None),
):
    if bucket not in PUBLIC_BUCKETS:
        if exp is None or sig is None or not storage_local.verify_signature(bucket, path, exp, sig):
            raise HTTPException(status_code=403, detail="Invalid or expired signature")

    try:
        data = await storage_local.download_file(bucket, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except (ValueError, OSError):
        # _safe_path rejected the bucket/path or tried reading a directory
        raise HTTPException(status_code=404, detail="File not found")

    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    filename = path.rsplit("/", 1)[-1]
    # HTTP header values must be Latin-1-encodable — a filename with a smart
    # quote, em-dash, or any other non-Latin-1 character (common in uploaded
    # originals) would otherwise crash Response's header encoding. RFC 6266:
    # an ASCII-sanitized `filename` fallback for old clients, alongside the
    # real name percent-encoded in `filename*` for everything modern.
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").replace('"', "").replace("\\", "") or "file"
    content_disposition = f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"

    total_len = len(data)
    headers = {
        "Content-Disposition": content_disposition,
        "Accept-Ranges": "bytes",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "Accept-Ranges, Content-Encoding, Content-Length, Content-Range, Content-Disposition",
    }

    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        try:
            byte_range = range_header.replace("bytes=", "").split("-")
            start = int(byte_range[0]) if byte_range[0] else 0
            end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else total_len - 1
            start = max(0, min(start, total_len - 1))
            end = max(start, min(end, total_len - 1))
            chunk = data[start : end + 1]
            headers["Content-Range"] = f"bytes {start}-{end}/{total_len}"
            headers["Content-Length"] = str(len(chunk))
            return Response(content=chunk, status_code=206, media_type=media_type, headers=headers)
        except Exception:
            pass

    headers["Content-Length"] = str(total_len)
    return Response(
        content=data,
        media_type=media_type,
        headers=headers,
    )

