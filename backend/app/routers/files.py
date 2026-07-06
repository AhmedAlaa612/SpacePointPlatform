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

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.services import storage_local

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{bucket}/{path:path}")
async def serve_file(bucket: str, path: str, exp: int = Query(...), sig: str = Query(...)):
    if not storage_local.verify_signature(bucket, path, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid or expired signature")

    try:
        data = await storage_local.download_file(bucket, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except ValueError:
        # _safe_path rejected the bucket/path (traversal attempt)
        raise HTTPException(status_code=403, detail="Invalid path")

    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    filename = path.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
