# VARUNA — Satellite Catalogue Discovery & Observation Attachment

## Overview

VARUNA Phase 2 introduces genuine live satellite catalogue discovery, connecting generic investigation cases to the official **Copernicus Data Space Ecosystem (CDSE)** SpatioTemporal Asset Catalog (STAC) API.

```
CASE (persisted AOI + time window)
  │
  ▼
CDSE STAC API (v1 / sentinel-1-grd)
  │
  ▼
SENTINEL-1 GRD DISCOVERY & FOOTPRINT INTERSECTION
  │
  ▼
ANALYST SELECTION & ATTACHMENT
  │
  ▼
ATTACHED OBSERVATION RECORD + PROVENANCE (Data Manifest)
```

---

## 1. Provider & Service Specification

- **Provider**: European Space Agency (ESA) / Copernicus Data Space Ecosystem (CDSE)
- **STAC Endpoint**: `https://stac.dataspace.copernicus.eu/v1/` (configurable via `VARUNA_CDSE_STAC_URL`)
- **Collection**: `sentinel-1-grd` (Sentinel-1 Ground Range Detected Level-1 products)
- **Deprecated Endpoints**: `https://catalogue.dataspace.copernicus.eu/stac` is deprecated and **must not be used**.
- **STAC Client**: `pystac-client` (v0.9.0+)

---

## 2. Catalogue Discovery vs. Product Download

A critical scientific distinction is maintained between **Catalogue Metadata Discovery** and **Product SAFE Download**:

| Dimension | Phase 2: Catalogue Discovery | Phase 3: Product Download & SNAP |
| :--- | :--- | :--- |
| **Action** | Metadata query & footprint intersection | Multi-GB `.SAFE` download & unzipping |
| **Data Transferred** | Kilobytes of GeoJSON / STAC metadata | ~1.5 GB per product archive |
| **Processing** | Polygon intersection coverage calculation | ESA SNAP GPT calibration, speckle filter, terrain correction |
| **Scientific State** | SATELLITE CATALOGUE OBSERVATION ATTACHED | CALIBRATED SAR RASTER READY FOR INFERENCE |
| **Provenance** | CDSE STAC item ID, source URL, timestamps | Product SHA-256, GPT graph execution log |

> [!IMPORTANT]
> **Scientific Integrity Rule**: At this stage, VARUNA knows only that an acquisition exists and intersects the case AOI. Catalogue discovery must never be labeled "oil detection", "live SAR analysis", or "real-time satellite feed".

---

## 3. AOI Search & Coverage Calculation

### Geospatial Intersection
- The case's persisted `aoi_geojson` (Polygon / MultiPolygon) is passed to CDSE STAC via `intersects=<GeoJSON>`.
- The temporal query window is formatted as ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ/YYYY-MM-DDTHH:MM:SSZ`).
- For maritime oil spill analysis, the default instrument mode filter is `IW` (Interferometric Wide Swath).

### Coverage Metric
- `coverage_fraction` ($0.0 \dots 1.0$) and `coverage_percent` ($0 \dots 100\%$) are computed using `shapely.geometry.shape`.
- **Methodology Note**: Planar 2D polygon intersection area ratio in WGS84 coordinates is utilized for catalogue-ranking and product selection. This is a catalogue footprint coverage approximation, not a physical curved-Earth geodetic area measurement.

---

## 4. Normalized Observation Schema (`SatelliteObservation`)

```json
{
  "observation_id": "obs-76f26297b67a",
  "provider": "Copernicus Data Space Ecosystem",
  "collection": "sentinel-1-grd",
  "stac_item_id": "S1A_IW_GRDH_1SDV_20240914T011048_20240914T011113_055654_06CB9B_7619_COG",
  "platform": "Sentinel-1A",
  "constellation": "sentinel-1",
  "datetime": "2024-09-14T01:10:48.872266Z",
  "start_datetime": "2024-09-14T01:10:48.872266Z",
  "end_datetime": "2024-09-14T01:11:13.870442Z",
  "instrument_mode": "IW",
  "polarizations": ["VV", "VH"],
  "orbit_state": "descending",
  "relative_orbit": 107,
  "absolute_orbit": 55654,
  "product_type": "IW_GRDH_1S",
  "geometry": { "type": "Polygon", "coordinates": [...] },
  "bbox": [68.12, 18.24, 71.85, 21.05],
  "thumbnail_url": "https://datahub.creodias.eu/odata/v1/Assets(...)/$value",
  "metadata_url": "https://download.dataspace.copernicus.eu/odata/v1/Products(...)/$value",
  "coverage_fraction": 0.8523,
  "coverage_percent": 85.2,
  "attached_at": "2026-09-18T17:00:00Z",
  "provenance": {
    "provider": "Copernicus Data Space Ecosystem",
    "catalogue": "CDSE STAC",
    "collection": "sentinel-1-grd",
    "retrieved_at": "2026-09-18T17:00:00Z",
    "query_aoi": { ... },
    "stac_item_id": "...",
    "source_url": "https://stac.dataspace.copernicus.eu/v1/collections/sentinel-1-grd/items/..."
  }
}
```

---

## 5. API Endpoints

- `POST /api/v1/cases/{case_id}/satellite/search`: Searches CDSE STAC using persisted case AOI and parameters.
- `POST /api/v1/cases/{case_id}/satellite/attach`: Verifies item with CDSE and attaches it to case manifest with provenance.
- `GET /api/v1/cases/{case_id}/satellite`: Returns all attached satellite observations for the case.

---

## 6. Truthful Error Handling

If Copernicus CDSE is unreachable, times out, or returns zero acquisitions, VARUNA truthfully presents:
- `COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE`
- `NO ACQUISITIONS FOUND`

Under no circumstances does VARUNA fabricate synthetic acquisitions or fall back to R001 observation metadata.
