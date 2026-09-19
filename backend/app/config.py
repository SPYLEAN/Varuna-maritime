"""
VARUNA — Central Runtime Configuration & Environment Loader.

Loads .env once centrally at import time, ensuring process environment
variables override file values, and protecting sensitive credentials.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Locate repository root and load .env if present
_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"

if _ENV_FILE.is_file():
    load_dotenv(dotenv_path=_ENV_FILE, override=False)
else:
    load_dotenv(override=False)

# Core Runtime Configuration
VARUNA_VERSION: str = "2.0.0-rc1"
API_HOST: str = os.environ.get("API_HOST", "127.0.0.1").strip()
API_PORT: int = int(os.environ.get("API_PORT", "8000"))
NEXT_PUBLIC_API_BASE_URL: str = os.environ.get(
    "NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000/api/v1"
).strip()

# Storage Roots
VARUNA_DATA_ROOT: str = os.environ.get("VARUNA_DATA_ROOT", "./data").strip()
VARUNA_RESEARCH_ROOT: str = os.environ.get("VARUNA_RESEARCH_ROOT", "./data/research").strip()

# Copernicus Data Space Ecosystem (CDSE)
DEFAULT_CDSE_STAC_URL: str = "https://stac.dataspace.copernicus.eu/v1/"
VARUNA_CDSE_STAC_URL: str = os.environ.get(
    "VARUNA_CDSE_STAC_URL", DEFAULT_CDSE_STAC_URL
).strip()

CDSE_USER: str = (
    os.environ.get("CDSE_USER")
    or os.environ.get("COPERNICUS_USER")
    or ""
).strip()

CDSE_PASS: str = (
    os.environ.get("CDSE_PASS")
    or os.environ.get("COPERNICUS_PASS")
    or ""
).strip()

VARUNA_CDSE_CACHE_DIR: str = os.environ.get(
    "VARUNA_CDSE_CACHE_DIR", "./data/cache/cdse"
).strip()


def mask_secret(value: Optional[str]) -> str:
    """Safely mask sensitive strings for logs without revealing content."""
    if not value:
        return "<not set>"
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}...{value[-2:]} ({len(value)} chars)"


def get_sanitized_config() -> dict[str, str | int]:
    """Return a dictionary of configuration with sensitive credentials masked."""
    return {
        "VARUNA_VERSION": VARUNA_VERSION,
        "API_HOST": API_HOST,
        "API_PORT": API_PORT,
        "NEXT_PUBLIC_API_BASE_URL": NEXT_PUBLIC_API_BASE_URL,
        "VARUNA_DATA_ROOT": VARUNA_DATA_ROOT,
        "VARUNA_RESEARCH_ROOT": VARUNA_RESEARCH_ROOT,
        "VARUNA_CDSE_STAC_URL": VARUNA_CDSE_STAC_URL,
        "VARUNA_CDSE_CACHE_DIR": VARUNA_CDSE_CACHE_DIR,
        "CDSE_USER": mask_secret(CDSE_USER),
        "CDSE_PASS": mask_secret(CDSE_PASS),
    }
