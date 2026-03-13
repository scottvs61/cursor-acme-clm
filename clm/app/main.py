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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Serve frontend (frontend/ or frontend/dist)
_frontend_dist = _repo / "frontend" / "dist"
_frontend_src = _repo / "frontend"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
elif (_frontend_src / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_frontend_src), html=True), name="frontend")
