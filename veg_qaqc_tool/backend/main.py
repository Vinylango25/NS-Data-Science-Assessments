"""
main.py
-------
Vegetation QA/QC API — FastAPI entry point.

Run locally:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Docs:
    http://localhost:8000/docs
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup/shutdown tasks."""
    log.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    log.info(f"  Data source : {settings.DATA_SOURCE}")
    log.info(f"  Database    : {settings.DATABASE_URL}")
    log.info(f"  Groq AI     : {'enabled' if settings.GROQ_API_KEY else 'disabled (rule-based fallback)'}")

    os.makedirs(settings.OUT_DIR, exist_ok=True)
    init_db()
    log.info("Database initialised.")
    yield
    log.info("Shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Vegetation QA/QC pipeline for Natural State Analytics. "
        "Runs the SOP-based scorecard against ODK herbaceous survey data "
        "and surfaces results through a REST API."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(api_router)


@app.get("/", tags=["Health"])
def root():
    return {
        "service":  settings.APP_NAME,
        "version":  settings.APP_VERSION,
        "status":   "running",
        "docs":     "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
