"""CLM API: certificates, events, optional ServiceNow. Run from repo root with PYTHONPATH=. """

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Repo root on path
_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from lib.config import load_config

from clm.app.admin_router import router as admin_router
from clm.app.auth_router import router as auth_router
from clm.app.db import init_db
from clm.app.routes import router

load_config(_repo / "config" / "config.yaml")

app = FastAPI(title="Certificate Lifecycle Manager", description="CLM API and ingestion for ACME/certs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup
@app.on_event("startup")
def startup():
    init_db()

app.include_router(router, prefix="/api", tags=["api"])
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Serve frontend: use built React app (frontend/dist) if it exists; else show build instructions
_frontend_dist = _repo / "frontend" / "dist"
_frontend_src = _repo / "frontend"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
else:
    @app.get("/")
    def _frontend_placeholder():
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            status_code=200,
            content="""<!DOCTYPE html><html><head><meta charset="utf-8"><title>CLM</title></head><body style="font-family:sans-serif;max-width:600px;margin:2rem auto;padding:1rem;">
            <h1>Certificate Lifecycle Manager</h1>
            <p>The GUI is not built yet. From the repo root run:</p>
            <pre style="background:#f0f0f0;padding:1rem;overflow:auto;">cd frontend && npm install && npm run build && cd ..</pre>
            <p>Then restart the CLM server. API is available at <a href="/health">/health</a> and <a href="/api/certificates">/api/certificates</a>.</p>
            </body></html>""",
        )
