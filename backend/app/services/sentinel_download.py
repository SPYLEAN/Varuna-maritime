"""
VARUNA — Sentinel-1 Product Acquisition Service
Adapted from: m7mdehab/oil-spill-detection (src/oilspill/pipeline/ingest.py)
License: MIT (Copyright (c) 2024-2026 Mohammed Ehab)
Source Commit SHA: 6c18c292153b3c617dd1e015dbe00f86272f9437

POLICY NOTICE:
VARUNA's `sentinel_catalog.py` remains the canonical discovery service.
This service adapts the authentication token exchange, product resolution,
and resumable streaming download logic to fulfill:
ATTACHED OBSERVATION -> RESOLVE PRODUCT -> DOWNLOAD PRODUCT
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Union, runtime_checkable

import requests
from pydantic import BaseModel, ConfigDict, Field
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# CDSE Keycloak and OData endpoints
TOKEN_URL: str = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
TOKEN_CLIENT_ID: str = "cdse-public"
DOWNLOAD_URL_TEMPLATE: str = (
    "https://download.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
)
ODATA_PRODUCTS_URL: str = (
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
)

DEFAULT_CHUNK_SIZE: int = 1 << 20  # 1 MiB
DEFAULT_TIMEOUT: float = 120.0


@runtime_checkable
class HttpSession(Protocol):
    """Protocol for testable HTTP session injection."""
    def get(self, url: str, **kwargs: Any) -> Any: ...
    def post(self, url: str, **kwargs: Any) -> Any: ...
    def close(self) -> None: ...


class CdseError(Exception):
    """Base exception for CDSE ingest operations."""
    pass


class CdseCredentialsMissingError(CdseError):
    """Raised when CDSE username or password is not provided."""
    pass


class CdseAuthenticationError(CdseError):
    """Raised when token authentication fails."""
    pass


class CdseDownloadError(CdseError):
    """Raised when streaming download fails or size mismatches."""
    pass


class ProductDownloadTarget(BaseModel):
    """Metadata required to initiate a CDSE product download."""
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    download_url: str
    size: Optional[int] = None


class ProductAcquisitionResult(BaseModel):
    """Immutable record of satellite product acquisition provenance."""
    model_config = ConfigDict(frozen=True)

    case_id: str
    observation_id: str
    stac_item_id: str
    product_name: str
    product_id: str
    download_url: str
    archive_path: Optional[str] = None
    safe_dir_path: Optional[str] = None
    bytes_downloaded: int = 0
    sha256: str = ""
    started_at: str
    completed_at: str
    status: str
    error_message: Optional[str] = None


def compute_file_sha256(filepath: Union[str, Path], chunk_size: int = 65536) -> str:
    """Compute cryptographic SHA-256 hash of a local file."""
    p = Path(filepath)
    if not p.is_file():
        raise FileNotFoundError(f"Cannot compute hash: file does not exist: {filepath}")
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def make_session(retries: int = 3) -> requests.Session:
    """Create a session with exponential backoff for transient HTTP errors."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_access_token(
    user: Optional[str] = None,
    password: Optional[str] = None,
    *,
    session: Optional[HttpSession] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Obtain short-lived CDSE bearer token via Keycloak password grant.

    Reads CDSE_USER / CDSE_PASS (or COPERNICUS_USER / COPERNICUS_PASS) from environment
    if not explicitly passed.
    """
    u = user or os.environ.get("CDSE_USER") or os.environ.get("COPERNICUS_USER")
    p = password or os.environ.get("CDSE_PASS") or os.environ.get("COPERNICUS_PASS")

    if not u or not p:
        raise CdseCredentialsMissingError(
            "CDSE credentials missing: please configure CDSE_USER and CDSE_PASS in environment or .env"
        )

    owns_session = session is None
    sess = session or make_session()
    try:
        response = sess.post(
            TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": TOKEN_CLIENT_ID,
                "username": u,
                "password": p,
            },
            timeout=timeout,
        )
        if response.status_code == 401:
            raise CdseAuthenticationError("CDSE authentication failed: invalid credentials.")
        response.raise_for_status()
        payload: Dict[str, Any] = response.json()
    except (CdseCredentialsMissingError, CdseAuthenticationError):
        raise
    except Exception as exc:
        raise CdseAuthenticationError(f"Failed to authenticate with CDSE Keycloak: {exc}") from exc
    finally:
        if owns_session:
            sess.close()

    token = payload.get("access_token")
    if not token:
        raise CdseAuthenticationError("CDSE token response missing 'access_token' property.")
    return str(token)


def resolve_product_from_observation(
    observation_data: Dict[str, Any],
) -> ProductDownloadTarget:
    """Resolve CDSE OData product ID, name, and download URL from an attached observation.

    Works directly with VARUNA's normalized STAC observations or raw STAC items.
    """
    stac_id = observation_data.get("stac_item_id") or observation_data.get("id") or ""
    # Sentinel-1 COG STAC items typically strip the _COG suffix for the product archive name
    product_name = stac_id[:-4] if stac_id.endswith("_COG") else stac_id

    assets = observation_data.get("assets") or {}
    product_asset = assets.get("Product") or assets.get("download") or assets.get("safe_manifest") or {}
    href = product_asset.get("href") if isinstance(product_asset, dict) else str(product_asset)

    product_id = ""
    download_url = ""

    # Check for OData Product UUID in href e.g. Products(b686d9a2-...)/$value
    if href:
        uuid_match = re.search(r"Products\(([a-f0-9\-]+)\)", href, re.IGNORECASE)
        if uuid_match:
            product_id = uuid_match.group(1)
            download_url = DOWNLOAD_URL_TEMPLATE.format(product_id=product_id)
        elif "odata/v1/Products" in href and "$value" in href:
            download_url = href

    # If product_id not found in href, fallback to metadata_url
    if not product_id:
        meta_url = observation_data.get("metadata_url") or ""
        uuid_match = re.search(r"Products\(([a-f0-9\-]+)\)", meta_url, re.IGNORECASE)
        if uuid_match:
            product_id = uuid_match.group(1)
            download_url = DOWNLOAD_URL_TEMPLATE.format(product_id=product_id)

    if not product_id:
        # Check raw_properties
        raw_props = observation_data.get("raw_properties") or {}
        if "id" in raw_props and len(raw_props["id"]) == 36 and "-" in raw_props["id"]:
            product_id = raw_props["id"]
            download_url = DOWNLOAD_URL_TEMPLATE.format(product_id=product_id)

    # If still no UUID, use product_name with download URL template using name
    if not product_id:
        product_id = product_name
        download_url = DOWNLOAD_URL_TEMPLATE.format(product_id=product_id)

    return ProductDownloadTarget(
        id=product_id,
        name=product_name,
        download_url=download_url,
    )


def download_product(
    product: ProductDownloadTarget,
    dest_dir: Union[Path, str],
    token: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    session: Optional[HttpSession] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Path:
    """Stream a product ZIP archive to `dest_dir` with range-resume support.

    Adapted directly from `oilspill/pipeline/ingest.py`.
    """
    dest_path_dir = Path(dest_dir)
    dest_path_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_path_dir / f"{product.name}.zip"

    existing_bytes = dest_path.stat().st_size if dest_path.exists() else 0
    headers = {"Authorization": f"Bearer {token}"}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    owns_session = session is None
    sess = session or make_session()
    try:
        response = sess.get(
            product.download_url,
            headers=headers,
            stream=True,
            timeout=timeout,
            allow_redirects=True,
        )
        if response.status_code == 401:
            raise CdseAuthenticationError("CDSE token expired or invalid during download.")
        response.raise_for_status()

        # 206 Partial Content indicates range resume accepted
        resuming = existing_bytes > 0 and response.status_code == 206
        mode = "ab" if resuming else "wb"
        with dest_path.open(mode) as fh:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
    except Exception as exc:
        raise CdseDownloadError(f"Download failed for {product.name}: {exc}") from exc
    finally:
        resp_close = getattr(response, "close", None) if "response" in locals() else None
        if callable(resp_close):
            resp_close()
        if owns_session:
            sess.close()

    final_size = dest_path.stat().st_size
    if product.size is not None and final_size != product.size:
        raise CdseDownloadError(
            f"Downloaded size {final_size} does not match expected {product.size} for {product.name}"
        )

    return dest_path


def acquire_observation_product(
    case_id: str,
    observation_id: str,
    observation_data: Dict[str, Any],
    *,
    base_dir: Union[Path, str] = "data/cases",
    token: Optional[str] = None,
    extract_safe: bool = True,
    session: Optional[HttpSession] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ProductAcquisitionResult:
    """Execute complete VARUNA Sentinel product acquisition flow:

    Attached Observation -> Resolve Product -> Stream to disk -> Compute SHA-256 -> Unzip SAFE.
    Destination contract: data/cases/<case_id>/observations/<observation_id>/raw/
    """
    started_at = datetime.now(timezone.utc).isoformat()
    raw_dir = Path(base_dir) / case_id / "observations" / observation_id / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    stac_id = observation_data.get("stac_item_id") or observation_data.get("id") or ""
    product_target = resolve_product_from_observation(observation_data)

    # Obtain token if not provided
    try:
        active_token = token or get_access_token(session=session, timeout=timeout)
    except CdseCredentialsMissingError as cme:
        completed_at = datetime.now(timezone.utc).isoformat()
        return ProductAcquisitionResult(
            case_id=case_id,
            observation_id=observation_id,
            stac_item_id=stac_id,
            product_name=product_target.name,
            product_id=product_target.id,
            download_url=product_target.download_url,
            started_at=started_at,
            completed_at=completed_at,
            status="CREDENTIALS_MISSING",
            error_message=str(cme),
        )
    except Exception as ae:
        completed_at = datetime.now(timezone.utc).isoformat()
        return ProductAcquisitionResult(
            case_id=case_id,
            observation_id=observation_id,
            stac_item_id=stac_id,
            product_name=product_target.name,
            product_id=product_target.id,
            download_url=product_target.download_url,
            started_at=started_at,
            completed_at=completed_at,
            status="AUTHENTICATION_FAILED",
            error_message=str(ae),
        )

    # Perform download
    try:
        archive_path = download_product(
            product=product_target,
            dest_dir=raw_dir,
            token=active_token,
            session=session,
            timeout=timeout,
        )
        bytes_downloaded = archive_path.stat().st_size
        sha256_hash = compute_file_sha256(archive_path)

        safe_dir_path = None
        if extract_safe and zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(raw_dir)
            # Find extracted .SAFE directory
            safe_dirs = list(raw_dir.glob("*.SAFE"))
            if safe_dirs:
                safe_dir_path = str(safe_dirs[0])

        completed_at = datetime.now(timezone.utc).isoformat()
        return ProductAcquisitionResult(
            case_id=case_id,
            observation_id=observation_id,
            stac_item_id=stac_id,
            product_name=product_target.name,
            product_id=product_target.id,
            download_url=product_target.download_url,
            archive_path=str(archive_path),
            safe_dir_path=safe_dir_path,
            bytes_downloaded=bytes_downloaded,
            sha256=sha256_hash,
            started_at=started_at,
            completed_at=completed_at,
            status="SUCCESS",
        )
    except Exception as de:
        completed_at = datetime.now(timezone.utc).isoformat()
        logger.error(f"Failed to acquire satellite product: {de}", exc_info=True)
        return ProductAcquisitionResult(
            case_id=case_id,
            observation_id=observation_id,
            stac_item_id=stac_id,
            product_name=product_target.name,
            product_id=product_target.id,
            download_url=product_target.download_url,
            started_at=started_at,
            completed_at=completed_at,
            status="DOWNLOAD_FAILED",
            error_message=str(de),
        )
