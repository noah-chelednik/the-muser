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
    """Serve one indexed sample (only paths the scanner indexed; nothing else on disk)."""
    p = library.indexed_file(path)
    if not p:
        raise HTTPException(404, "Not in the sample library")
    return FileResponse(p)
