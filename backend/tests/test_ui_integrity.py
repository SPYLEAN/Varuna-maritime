"""
Unit Test Suite for SAMUDRANETRA TASK017.1 — Final UI Remaster Integrity Audit.

Verifies keyless basemap configuration, 5-domain navigation model, default NORMAL_CASE initialization,
scientific value alignment, and prohibition of unscientific wording.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.routers.investigation import get_r001_dir
from backend.app.services.investigation_engine import build_unified_investigation_case

client = TestClient(app)
CASE_ID = "R001_WAKASHIO"
R001_DIR = get_r001_dir()
OPS_CONSOLE_DIR = Path(__file__).resolve().parents[2] / "ops_console"


def test_keyless_basemap_configuration():
    """1. Verify app.js uses keyless ESRI Dark Gray basemap URL."""
    app_js_path = OPS_CONSOLE_DIR / "app.js"
    assert app_js_path.exists()
    content = app_js_path.read_text(encoding="utf-8")

    assert "arcgisonline.com" in content
    assert "cartocdn.com/dark_all" not in content  # Watermarked tile URL removed


def test_five_domain_navigation_structure():
    """2. Verify index.html implements the 5-domain navigation model."""
    index_html_path = OPS_CONSOLE_DIR / "index.html"
    assert index_html_path.exists()
    content = index_html_path.read_text(encoding="utf-8")

    domains = ["01", "OBSERVE", "02", "ANALYZE", "03", "RECONSTRUCT", "04", "VESSEL INTELLIGENCE", "05", "REVIEW"]
    for d in domains:
        assert d in content


def test_default_case_state_is_normal():
    """3. Verify default state is NORMAL_CASE without simulated failure banners."""
    app_js_path = OPS_CONSOLE_DIR / "app.js"
    content = app_js_path.read_text(encoding="utf-8")

    assert 'activeEdgeState: "NORMAL_CASE"' in content


def test_scientific_values_canonical_alignment():
    """4. Audit canonical values for C4053 candidate evidence."""
    c = build_unified_investigation_case(R001_DIR)
    assert c["case_id"] == "R001_WAKASHIO"
    assert c["sar"]["candidate_count"] == 8
    assert c["historical_validation"]["best_candidate"] == "C4053"
    assert c["historical_validation"]["best_distance_km"] == 24.64


def test_no_unscientific_wording_audit():
    """5. Audit outputs for forbidden unscientific terminology."""
    resp = client.get(f"/api/cases/{CASE_ID}")
    assert resp.status_code == 200
    text = resp.text.lower()

    forbidden_terms = ["culprit", "guilty", "proven source", "ai confidence", "probability of guilt", "100% accurate"]
    for term in forbidden_terms:
        assert term not in text, f"Forbidden term '{term}' found in case API response."
