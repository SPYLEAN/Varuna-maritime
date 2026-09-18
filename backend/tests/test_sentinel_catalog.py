"""
Test Suite for VARUNA Phase 2 — Live Sentinel-1 Discovery + Observation Attachment.

Verifies:
1. Satellite search requires valid case (404)
2. Satellite search requires case AOI (400)
3. Satellite search validates ISO-8601 UTC date ranges (400)
4. CDSE STAC item normalization and schema mapping
5. Search endpoint response schema contract
6. Shapely AOI coverage calculation (100%, 50%, 0%)
7. Observation attachment with cryptographic and provider provenance
8. Attached observation persistence across storage reload
9. Zero-leakage contract: Generic Case #2 contains NO R001 / Wakashio / C4053 / Mauritius
10. Truthful error handling: Provider failure returns 503 with 0 fabricated fallback items
11. Live integration test with real CDSE STAC endpoint (@pytest.mark.integration)
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas import SatelliteObservation, SatelliteSearchResponse
from backend.app.services.sentinel_catalog import (
    CopernicusUnavailableError,
    calculate_aoi_coverage,
    normalize_stac_item,
    search_sentinel1_grd,
)
from backend.app.storage import JSONCaseStorage, storage

client = TestClient(app)

MOCK_AOI = {
    "type": "Polygon",
    "coordinates": [
        [
            [70.0, 19.0],
            [71.0, 19.0],
            [71.0, 20.0],
            [70.0, 20.0],
            [70.0, 19.0],
        ]
    ],
}

MOCK_STAC_ITEM = {
    "id": "S1A_IW_GRDH_1SDV_20240914T011048_20240914T011113_055654_06CB9B_7619_COG",
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [69.5, 18.5],
                [71.5, 18.5],
                [71.5, 20.5],
                [69.5, 20.5],
                [69.5, 18.5],
            ]
        ],
    },
    "bbox": [69.5, 18.5, 71.5, 20.5],
    "properties": {
        "datetime": "2024-09-14T01:10:48.872266Z",
        "start_datetime": "2024-09-14T01:10:48.872266Z",
        "end_datetime": "2024-09-14T01:11:13.870442Z",
        "platform": "sentinel-1a",
        "constellation": "sentinel-1",
        "sar:instrument_mode": "IW",
        "sar:polarizations": ["VV", "VH"],
        "sat:orbit_state": "descending",
        "sat:relative_orbit": 107,
        "sat:absolute_orbit": 55654,
        "product:type": "IW_GRDH_1S",
    },
    "assets": {
        "thumbnail": {
            "href": "https://datahub.creodias.eu/odata/v1/Assets(0d16b7b6)/$value",
            "title": "Thumbnail image",
        },
        "Product": {
            "href": "https://download.dataspace.copernicus.eu/odata/v1/Products(76f26297)/$value",
            "title": "Product package",
        },
        "safe_manifest": {
            "href": "s3://eodata/Sentinel-1/manifest.safe",
            "title": "SAFE manifest",
        },
    },
}


@pytest.fixture(autouse=True)
def temp_storage(tmp_path):
    """Isolate case storage in temporary directory during test execution."""
    original_dir = storage.storage_dir
    storage.storage_dir = tmp_path / "cases"
    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    storage.storage_dir = original_dir


def _create_test_case(name="Arabian Sea Case", aoi=MOCK_AOI):
    res = client.post(
        "/api/v1/cases",
        json={
            "name": name,
            "description": "Satellite test case",
            "region": "Arabian Sea",
            "latitude": 19.5,
            "longitude": 70.5,
            "aoi_geojson": aoi,
        },
    )
    assert res.status_code == 201
    return res.json()["case_id"]


def test_satellite_search_requires_case():
    """1. Verify search returns 404 for non-existent case."""
    res = client.post(
        "/api/v1/cases/case_non_existent/satellite/search",
        json={
            "start_datetime": "2024-09-10T00:00:00Z",
            "end_datetime": "2024-09-18T00:00:00Z",
        },
    )
    assert res.status_code == 404
    assert "CASE_NOT_FOUND" in res.json()["detail"]


def test_satellite_search_requires_aoi():
    """2. Verify search returns 400 when case has no AOI defined."""
    case_id = _create_test_case(name="No AOI Case", aoi=None)
    res = client.post(
        f"/api/v1/cases/{case_id}/satellite/search",
        json={
            "start_datetime": "2024-09-10T00:00:00Z",
            "end_datetime": "2024-09-18T00:00:00Z",
        },
    )
    assert res.status_code == 400
    assert "CASE_HAS_NO_AOI" in res.json()["detail"]


def test_satellite_search_validates_dates():
    """3. Verify search returns 400 for invalid dates or start > end."""
    case_id = _create_test_case()

    # Invalid string
    res = client.post(
        f"/api/v1/cases/{case_id}/satellite/search",
        json={
            "start_datetime": "not-a-date",
            "end_datetime": "2024-09-18T00:00:00Z",
        },
    )
    assert res.status_code == 400
    assert "INVALID_TIME_RANGE" in res.json()["detail"]

    # start > end
    res2 = client.post(
        f"/api/v1/cases/{case_id}/satellite/search",
        json={
            "start_datetime": "2024-09-20T00:00:00Z",
            "end_datetime": "2024-09-10T00:00:00Z",
        },
    )
    assert res2.status_code == 400
    assert "INVALID_TIME_RANGE" in res2.json()["detail"]


def test_cdse_stac_normalization():
    """4. Verify raw CDSE STAC item dict normalizes to SatelliteObservation without inventing fake values."""
    normalized = normalize_stac_item(MOCK_STAC_ITEM, aoi_geojson=MOCK_AOI)

    assert normalized["stac_item_id"] == MOCK_STAC_ITEM["id"]
    assert normalized["platform"] == "Sentinel-1A"
    assert normalized["constellation"] == "sentinel-1"
    assert normalized["instrument_mode"] == "IW"
    assert normalized["polarizations"] == ["VV", "VH"]
    assert normalized["orbit_state"] == "descending"
    assert normalized["relative_orbit"] == 107
    assert normalized["absolute_orbit"] == 55654
    assert normalized["product_type"] == "IW_GRDH_1S"
    assert normalized["thumbnail_url"] == "https://datahub.creodias.eu/odata/v1/Assets(0d16b7b6)/$value"
    assert normalized["coverage_fraction"] == 1.0
    assert normalized["coverage_percent"] == 100.0
    assert normalized["attached_at"] is None

    # Verify no fake values for non-existent properties
    sparse_item = {
        "id": "S1A_SPARSE_ITEM_COG",
        "geometry": None,
        "properties": {"datetime": "2024-09-14T00:00:00Z"},
        "assets": {},
    }
    sparse_norm = normalize_stac_item(sparse_item)
    assert sparse_norm["platform"] is None
    assert sparse_norm["instrument_mode"] is None
    assert sparse_norm["polarizations"] == []
    assert sparse_norm["thumbnail_url"] is None
    assert sparse_norm["coverage_percent"] == 0.0


def test_sentinel1_search_returns_real_schema():
    """5. Verify search endpoint returns properly typed SatelliteSearchResponse."""
    case_id = _create_test_case()
    normalized_item = normalize_stac_item(MOCK_STAC_ITEM, aoi_geojson=MOCK_AOI)

    with patch("backend.app.routers.satellite.search_sentinel1_grd", return_value=[normalized_item]):
        res = client.post(
            f"/api/v1/cases/{case_id}/satellite/search",
            json={
                "start_datetime": "2024-09-10T00:00:00Z",
                "end_datetime": "2024-09-18T00:00:00Z",
                "instrument_mode": "IW",
            },
        )
        assert res.status_code == 200
        data = res.json()
        validated = SatelliteSearchResponse(**data)
        assert validated.case_id == case_id
        assert validated.count == 1
        assert validated.results[0].stac_item_id == MOCK_STAC_ITEM["id"]
        assert validated.results[0].platform == "Sentinel-1A"


def test_coverage_calculation():
    """6. Verify shapely polygon coverage calculation (100%, 50%, 0%)."""
    # 1x1 AOI: [0..1, 0..1], area = 1.0
    aoi = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}

    # 100% overlap: footprint completely covers AOI
    fp_full = {"type": "Polygon", "coordinates": [[[-1, -1], [2, -1], [2, 2], [-1, 2], [-1, -1]]]}
    frac, pct = calculate_aoi_coverage(aoi, fp_full)
    assert frac == 1.0
    assert pct == 100.0

    # 50% overlap: footprint covers right half [0.5..1.5, 0..1]
    fp_half = {"type": "Polygon", "coordinates": [[[0.5, 0], [1.5, 0], [1.5, 1], [0.5, 1], [0.5, 0]]]}
    frac50, pct50 = calculate_aoi_coverage(aoi, fp_half)
    assert frac50 == 0.5
    assert pct50 == 50.0

    # 0% overlap: completely disjoint footprint [2..3, 2..3]
    fp_disjoint = {"type": "Polygon", "coordinates": [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]]}
    frac0, pct0 = calculate_aoi_coverage(aoi, fp_disjoint)
    assert frac0 == 0.0
    assert pct0 == 0.0


def test_attach_observation():
    """7. Verify attaching an observation persists verified STAC metadata and provenance."""
    case_id = _create_test_case()
    normalized_item = normalize_stac_item(MOCK_STAC_ITEM, aoi_geojson=MOCK_AOI)

    with patch("backend.app.routers.satellite.get_sentinel1_item_by_id", return_value=normalized_item):
        res = client.post(
            f"/api/v1/cases/{case_id}/satellite/attach",
            json={"stac_item_id": MOCK_STAC_ITEM["id"]},
        )
        assert res.status_code == 201
        attached = res.json()
        assert attached["stac_item_id"] == MOCK_STAC_ITEM["id"]
        assert attached["attached_at"] is not None
        assert attached["provenance"]["provider"] == "Copernicus Data Space Ecosystem"
        assert attached["provenance"]["catalogue"] == "CDSE STAC"
        assert attached["provenance"]["collection"] == "sentinel-1-grd"

        # Check GET endpoint
        get_res = client.get(f"/api/v1/cases/{case_id}/satellite")
        assert get_res.status_code == 200
        obs_list = get_res.json()
        assert len(obs_list) == 1
        assert obs_list[0]["stac_item_id"] == MOCK_STAC_ITEM["id"]


def test_attached_observation_persists():
    """8. Verify attached observation persists across cold storage reloads."""
    case_id = _create_test_case()
    normalized_item = normalize_stac_item(MOCK_STAC_ITEM, aoi_geojson=MOCK_AOI)

    with patch("backend.app.routers.satellite.get_sentinel1_item_by_id", return_value=normalized_item):
        attach_res = client.post(
            f"/api/v1/cases/{case_id}/satellite/attach",
            json={"stac_item_id": MOCK_STAC_ITEM["id"]},
        )
        assert attach_res.status_code == 201

    # Reload storage from disk directly
    fresh_storage = JSONCaseStorage(storage.storage_dir)
    persisted_case = fresh_storage.get_case(case_id)
    assert persisted_case is not None

    sat_obs = persisted_case.get("data_manifest", {}).get("satellite_observations", [])
    assert len(sat_obs) == 1
    assert sat_obs[0]["stac_item_id"] == MOCK_STAC_ITEM["id"]
    assert sat_obs[0]["provenance"]["collection"] == "sentinel-1-grd"


def test_case2_satellite_has_no_r001_leakage():
    """9. Zero-leakage contract: Attached satellite metadata contains 0 R001 / Wakashio / C4053 / Mauritius."""
    case_id = _create_test_case(name="Arabian Sea Zero Leakage Test")
    normalized_item = normalize_stac_item(MOCK_STAC_ITEM, aoi_geojson=MOCK_AOI)

    with patch("backend.app.routers.satellite.get_sentinel1_item_by_id", return_value=normalized_item):
        client.post(
            f"/api/v1/cases/{case_id}/satellite/attach",
            json={"stac_item_id": MOCK_STAC_ITEM["id"]},
        )

    case_res = client.get(f"/api/v1/cases/{case_id}")
    case_str = json.dumps(case_res.json()).lower()

    forbidden_tokens = ["r001", "wakashio", "c4053", "mauritius", "vessel_beta"]
    for token in forbidden_tokens:
        assert token not in case_str, f"Leakage detected: '{token}' found in generic case!"


def test_provider_failure_does_not_return_fake_results():
    """10. Verify provider failure truthfully returns 503 without fake fallback results."""
    case_id = _create_test_case()

    with patch(
        "backend.app.routers.satellite.search_sentinel1_grd",
        side_effect=CopernicusUnavailableError("CDSE 503 Service Unavailable"),
    ):
        res = client.post(
            f"/api/v1/cases/{case_id}/satellite/search",
            json={
                "start_datetime": "2024-09-10T00:00:00Z",
                "end_datetime": "2024-09-18T00:00:00Z",
            },
        )
        assert res.status_code == 503
        assert "COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE" in res.json()["detail"]


@pytest.mark.integration
def test_live_cdse_stac_integration():
    """
    11. Optional Live Integration Test: Calls actual Copernicus CDSE STAC endpoint.
    Tests genuine search and observation schema against real Sentinel-1 acquisitions.
    """
    # Arabian Sea test AOI offshore Mumbai/Gujarat: [69.5, 19.5, 70.5, 20.5]
    arabian_sea_aoi = {
        "type": "Polygon",
        "coordinates": [
            [
                [69.5, 19.5],
                [70.5, 19.5],
                [70.5, 20.5],
                [69.5, 20.5],
                [69.5, 19.5],
            ]
        ],
    }
    start = "2024-09-10T00:00:00Z"
    end = "2024-09-18T23:59:59Z"

    results = search_sentinel1_grd(
        aoi_geojson=arabian_sea_aoi,
        start_datetime=start,
        end_datetime=end,
        limit=5,
        instrument_mode="IW",
    )

    assert len(results) > 0, "Expected at least 1 Sentinel-1 acquisition in Arabian Sea window"
    top_item = results[0]
    assert top_item["provider"] == "Copernicus Data Space Ecosystem"
    assert top_item["collection"] == "sentinel-1-grd"
    assert "sentinel-1" in (top_item["constellation"] or "").lower()
    assert top_item["instrument_mode"] == "IW"
    assert top_item["coverage_percent"] > 0.0
    assert top_item["stac_item_id"].endswith("_COG")
