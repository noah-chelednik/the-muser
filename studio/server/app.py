"""FastAPI app: REST + SSE API for the Studio, and static hosting of the built UI."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent_bridge, capabilities, engine
from .store import UPLOADS_DIR, jobs, resolve_file, tracks
from .upload_guard import UploadRejected, sanitize_title, save_upload

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("studio")

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

app = FastAPI(title="The Muser Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/status")
def status(refresh: bool = False) -> dict:
    caps = capabilities.detect(force=refresh)
    from src.orchestrator.tool_definitions import get_tool_names

    d = caps.to_dict()
    d["tool_count"] = len(get_tool_names())
    d["mode_detail"] = {
        "demo": "Demo mode: chat replies and audio come from the local demo synthesizer.",
        "hybrid": "LLM agent connected. Audio models missing - Generate uses the demo synthesizer.",
        "full": "Full pipeline: LLM agent + ACE-Step generation available.",
    }[caps.mode]
    return d


@app.get("/api/tools")
def tools() -> list[dict]:
    from src.orchestrator.tool_definitions import get_all_tools_openai

    return [
        {"name": t["function"]["name"], "description": t["function"].get("description", "")[:200]}
        for t in get_all_tools_openai()
    ]


# ---------------------------------------------------------------------------
# Chat (SSE)
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    model: str | None = None


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        agent_bridge.stream_chat(req.message, req.session_id, req.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Tracks / jobs
# ---------------------------------------------------------------------------


@app.get("/api/tracks")
def list_tracks() -> list[dict]:
    return [t.to_public() for t in tracks.list()]


@app.get("/api/tracks/{tid}")
def get_track(tid: str) -> dict:
    t = tracks.get(tid)
    if not t:
        raise HTTPException(404, "Track not found")
    return t.to_public()


@app.delete("/api/tracks/{tid}")
def delete_track(tid: str) -> dict:
    return {"deleted": tracks.delete(tid)}


def _job_response(job) -> dict:
    return {"job_id": job.id, "status": job.status}


@app.post("/api/generate")
def generate(req: engine.GenerateRequest) -> dict:
    return _job_response(jobs.submit("generate", lambda j: engine.generate(req, j)))


class SplitRequest(BaseModel):
    mode: str = Field("4stem", pattern="^(4stem|2stem)$")


@app.post("/api/tracks/{tid}/split")
def split(tid: str, req: SplitRequest) -> dict:
    if not tracks.get(tid):
        raise HTTPException(404, "Track not found")
    return _job_response(jobs.submit("split", lambda j: engine.split(tid, req.mode, j)))


@app.post("/api/mix")
def mix(req: engine.MixRequest) -> dict:
    return _job_response(jobs.submit("mix", lambda j: engine.mix(req, j)))


@app.post("/api/export")
def export(req: engine.ExportRequest) -> dict:
    return _job_response(jobs.submit("export", lambda j: engine.export(req, j)))


@app.get("/api/jobs/{jid}")
def job(jid: str) -> dict:
    j = jobs.get(jid)
    if not j:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": j.id,
        "kind": j.kind,
        "status": j.status,
        "message": j.message,
        "result": j.result,
        "error": j.error,
        "detail": getattr(j, "detail", ""),
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), title: str = Form("")) -> dict:
    # allowlist + MIME + magic bytes + streamed size cap + real decode; random stored name (upload_guard)
    try:
        stored, clean = save_upload(file.file, file.filename, file.content_type, UPLOADS_DIR)
    except UploadRejected as e:
        raise HTTPException(400, str(e)) from None
    t = engine.import_upload(stored, sanitize_title(title) if title else clean)
    return {"track": t.to_public()}


@app.get("/files/{root}/{rel:path}")
def files(root: str, rel: str) -> FileResponse:
    p = resolve_file(root, rel)
    if not p:
        raise HTTPException(404, "File not found")
    return FileResponse(p)


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

if (WEB_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


from .routes_v2 import router as _v2_router
from .routes_library import router as _library_router

app.include_router(_v2_router)
app.include_router(_library_router)


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    candidate = (WEB_DIST / path).resolve()
    if path and WEB_DIST in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(
        "<h2>The Muser Studio API is running.</h2><p>The web UI is not built yet. "
        "Run <code>npm install && npm run build</code> in <code>studio/web</code>, "
        "or use the dev server: <code>npm run dev</code> (http://localhost:5173).</p>",
        status_code=200,
    )
