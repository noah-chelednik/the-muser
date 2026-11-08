"""Sample and soundfont library API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import library

router = APIRouter(prefix="/api/library", tags=["library"])


class ScanRequest(BaseModel):
    paths: list[str]


@router.post("/scan")
def scan(req: ScanRequest) -> dict:
    if not req.paths:
        raise HTTPException(400, "Provide at least one path to scan")
    return library.scan_paths(req.paths)


@router.get("/search")
def search(q: str = "", kind: str | None = None, limit: int = 200) -> list[dict]:
    return library.search(q, kind, limit)


@router.get("/stats")
def stats() -> dict:
    return library.get_stats()


@router.get("/file")
def file(path: str) -> FileResponse:
    """Stream a file that is already in the scanned library index."""
    try:
        resolved = library.resolve_indexed(path)
    except FileNotFoundError:
        raise HTTPException(404, "File not found") from None
    except PermissionError:
        raise HTTPException(403, "File is not in the scanned library") from None
    return FileResponse(resolved, filename=resolved.name)
