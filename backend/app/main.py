import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import analysis, cases, evidence, files, intelligence, investigation, satellite, workflow
from .routers.investigation import router as investigation_router, job_router, get_r001_dir

from backend.app.config import VARUNA_VERSION

# Backward compatibility alias
SAMUDRANETRA_VERSION = VARUNA_VERSION

app = FastAPI(
    title="VARUNA API",
    description="Maritime Pollution Intelligence System — Operational Investigation & Evidence Engine",
    version=VARUNA_VERSION,
)

# CORS Security Baseline
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# API v1 Product Namespace (/api/v1/cases, /api/v1/cases/{id}/evidence, etc.)
app.include_router(cases.router, prefix="/api/v1")
app.include_router(evidence.router, prefix="/api/v1")
app.include_router(satellite.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(workflow.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(intelligence.router, prefix="/api/v1")

# Storage & Component Analysis Routers (Mounted on root /cases for backward compatibility)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(satellite.router)
app.include_router(analysis.router)
app.include_router(workflow.router)
app.include_router(files.router)
app.include_router(intelligence.router)

# Unified Investigation Engine & Live Prototype Routers (Mounted on /api/cases & /api/investigations)
app.include_router(investigation_router, prefix="/api/cases")
app.include_router(investigation_router, prefix="/api/investigations")
app.include_router(job_router, prefix="/api")


@app.get("/health")
def health():
    r_dir = get_r001_dir()
    case_data_ready = (r_dir / "07_results").exists()
    return {
        "status": "healthy",
        "service": "varuna-backend",
        "version": VARUNA_VERSION,
        "api": True,
        "case_data": case_data_ready,
    }


@app.get("/ready")
def ready():
    r_dir = get_r001_dir()
    case_data_ready = (r_dir / "07_results").exists()
    return {
        "status": "READY" if case_data_ready else "DEGRADED",
        "service_running": True,
        "case_data_ready": case_data_ready,
        "version": VARUNA_VERSION,
    }


@app.get("/version")
def get_version():
    return {"version": VARUNA_VERSION, "release_stage": "PRODUCTION_CANDIDATE"}


# Mount static ops_console
ops_console_dir = Path(__file__).resolve().parents[2] / "ops_console"
if ops_console_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/console", StaticFiles(directory=str(ops_console_dir), html=True), name="console")

