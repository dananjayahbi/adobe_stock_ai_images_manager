"""Source-folder browse APIs - pick server-side files for batch import.

Thin HTTP shell over ``services.source_folder``: every path reaches the disk
through that module's containment helper, so ``403`` means the same thing in
every endpoint and the create-with-``files`` import shares the exact rule.

Endpoints:

* ``GET /api/fs/root``          - is a source folder configured, and does it exist
* ``GET /api/fs/list?path=``    - one directory level (dirs + image files)
* ``GET /api/fs/thumb?path=``   - a 512px JPEG preview of one image

Auth rides the global session-cookie middleware like every other ``/api/*``
router — nothing route-specific is needed.
"""

from __future__ import annotations

import io
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from PIL import Image

from services import source_folder

router = APIRouter(tags=["fs"])

#: Thumbnail contract: max edge, JPEG quality, and cache lifetime.
_THUMB_MAX_EDGE = 512
_THUMB_QUALITY = 75
_THUMB_CACHE_CONTROL = "private, max-age=3600"


@router.get("/api/fs/root")
async def fs_root() -> dict:
    """Whether a source folder is configured, and whether it currently exists."""
    raw = source_folder.configured_path()
    if not raw:
        return {"configured": False, "path": None, "exists": False}
    return {"configured": True, "path": raw, "exists": Path(raw).is_dir()}


@router.get("/api/fs/list")
async def fs_list(path: str = Query(default="")) -> dict:
    """One directory level of the source folder.

    ``path`` is relative to the folder root ("" = the root itself). Only image
    files are listed; directories come back as ``{"name"}``, files as
    ``{"name", "size", "mtime"}``, both sorted case-insensitively.
    """
    rel = path.strip("/")
    target = source_folder.resolve_dir(rel)
    parts = source_folder.relative_parts(rel)

    dirs: list[dict] = []
    files: list[dict] = []
    for entry in target.iterdir():
        try:
            if entry.is_dir():
                dirs.append({"name": entry.name})
            elif entry.is_file() and entry.suffix.lower() in source_folder.IMAGE_EXTENSIONS:
                stat = entry.stat()
                files.append(
                    {
                        "name": entry.name,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                )
        except OSError:
            # Raced with a delete/rename: skip the entry rather than failing
            # the whole listing.
            continue

    dirs.sort(key=lambda item: item["name"].lower())
    files.sort(key=lambda item: item["name"].lower())

    return {
        "path": rel,
        "segments": [
            {"name": part, "path": "/".join(parts[: index + 1])}
            for index, part in enumerate(parts)
        ],
        "parent": source_folder.parent_rel(parts),
        "dirs": dirs,
        "files": files,
    }


@router.get("/api/fs/thumb")
async def fs_thumb(path: str = Query(...)) -> Response:
    """A JPEG preview (max edge 512) of one image under the source folder.

    Never serves non-image extensions; 400 unconfigured/bad extension,
    403 escape, 404 missing.
    """
    target = source_folder.resolve_image_file(path)
    try:
        with Image.open(target) as img:
            img.thumbnail(
                (_THUMB_MAX_EDGE, _THUMB_MAX_EDGE), Image.Resampling.LANCZOS
            )
            if img.mode != "RGB":
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=_THUMB_QUALITY)
    except Exception as exc:  # noqa: BLE001 - unreadable/corrupt file
        raise HTTPException(
            status_code=400, detail=f"Cannot read image: {path}"
        ) from exc

    return Response(
        content=buffer.getvalue(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": _THUMB_CACHE_CONTROL,
            # Cheap freshness: the source file may change in place.
            "Last-Modified": time.strftime(
                "%a, %d %b %Y %H:%M:%S GMT", time.gmtime(target.stat().st_mtime)
            ),
        },
    )
