import hashlib
from pathlib import Path
import numpy as np
import cv2
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.storage import storage
from ml.src.oiltrace_ml.train import train_model
from ml.src.oiltrace_ml.infer import run_inference


@pytest.fixture(autouse=True)
def temp_storage(tmp_path):
    original_dir = storage.storage_dir
    storage.storage_dir = tmp_path / "cases"
    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    storage.storage_dir = original_dir


client = TestClient(app)


def test_upload_valid_evidence_and_sha256(tmp_path):
    res_case = client.post("/cases", json={"name": "Evidence Test Case"})
    case_id = res_case.json()["case_id"]

    # Dummy file content
    content = b"DUMMY_SAR_IMAGE_DATA_BYTES_12345"
    expected_sha256 = hashlib.sha256(content).hexdigest()

    files = {"file": ("test_sar.png", content, "image/png")}
    data = {
        "evidence_type": "sar_image",
        "source": "Sentinel-1A",
        "acquisition_timestamp": "2026-08-27T12:00:00Z",
        "is_synthetic": True,
        "is_human_verified": False,
        "notes": "Test SAR pass image",
    }

    res_up = client.post(f"/cases/{case_id}/evidence", files=files, data=data)
    assert res_up.status_code == 201
    ev_data = res_up.json()

    assert ev_data["evidence_id"].startswith("ev_")
    assert ev_data["case_id"] == case_id
    assert ev_data["evidence_type"] == "sar_image"
    assert ev_data["original_filename"] == "test_sar.png"
    assert ev_data["file_size"] == len(content)
    assert ev_data["sha256"] == expected_sha256
    assert ev_data["source"] == "Sentinel-1A"
    assert ev_data["is_synthetic"] is True

    # Check that file exists on disk inside evidence directory
    stored_path = Path(ev_data["stored_path"])
    assert stored_path.exists()
    assert stored_path.read_bytes() == content


def test_sha256_exact_byte_and_hash_audit():
    res_case = client.post("/cases", json={"name": "SHA256 Audit Case"})
    case_id = res_case.json()["case_id"]

    known_bytes = b"SAMUDRANETRA_EXACT_SHA256_BYTE_AUDIT_DATA_BYTES_99999"
    expected_hash = hashlib.sha256(known_bytes).hexdigest()
    empty_file_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    files = {"file": ("audit_sample.dat", known_bytes, "application/octet-stream")}
    data = {"evidence_type": "other"}

    res_up = client.post(f"/cases/{case_id}/evidence", files=files, data=data)
    assert res_up.status_code == 201
    ev_data = res_up.json()

    assert ev_data["file_size"] == len(known_bytes)
    assert ev_data["sha256"] == expected_hash
    assert ev_data["sha256"] != empty_file_hash


def test_list_evidence(tmp_path):
    res_case = client.post("/cases", json={"name": "Listing Evidence Case"})
    case_id = res_case.json()["case_id"]

    client.post(
        f"/cases/{case_id}/evidence",
        files={"file": ("sar1.png", b"sar_content", "image/png")},
        data={"evidence_type": "sar_image"},
    )
    client.post(
        f"/cases/{case_id}/evidence",
        files={"file": ("mask1.png", b"mask_content", "image/png")},
        data={"evidence_type": "oil_mask"},
    )

    res_list = client.get(f"/cases/{case_id}/evidence")
    assert res_list.status_code == 200
    ev_list = res_list.json()
    assert len(ev_list) == 2

    # Filter by evidence type
    res_filtered = client.get(f"/cases/{case_id}/evidence?evidence_type=sar_image")
    assert res_filtered.status_code == 200
    filtered_list = res_filtered.json()
    assert len(filtered_list) == 1
    assert filtered_list[0]["evidence_type"] == "sar_image"


def test_unsafe_filename_rejection():
    res_case = client.post("/cases", json={"name": "Path Traversal Test Case"})
    case_id = res_case.json()["case_id"]

    # Upload with dangerous path in filename
    files = {"file": ("../../etc/passwd", b"malicious", "text/plain")}
    data = {"evidence_type": "other"}

    res_up = client.post(f"/cases/{case_id}/evidence", files=files, data=data)
    assert res_up.status_code == 201
    stored_path = Path(res_up.json()["stored_path"])
    assert stored_path.name == "passwd"
    assert stored_path.parent.name == "evidence"
    assert case_id in stored_path.parent.parent.name or case_id in str(stored_path)


def test_oil_detection_missing_sar_image_returns_insufficient_data():
    res_case = client.post("/cases", json={"name": "No SAR Case"})
    case_id = res_case.json()["case_id"]

    res_an = client.post(f"/cases/{case_id}/analysis/oil-detection", json={})
    assert res_an.status_code == 200
    an_data = res_an.json()

    assert an_data["status"] == "insufficient_data"
    assert an_data["confidence"] is None
    assert "No SAR image evidence" in an_data["warnings"][0]

    # Verify status in case manifest
    res_c = client.get(f"/cases/{case_id}")
    assert res_c.json()["analysis_status"]["oil_detection"] == "insufficient_data"


def test_oil_detection_missing_checkpoint_returns_insufficient_data():
    res_case = client.post("/cases", json={"name": "No Model Case"})
    case_id = res_case.json()["case_id"]

    client.post(
        f"/cases/{case_id}/evidence",
        files={"file": ("sar.png", b"dummy", "image/png")},
        data={"evidence_type": "sar_image"},
    )

    res_an = client.post(
        f"/cases/{case_id}/analysis/oil-detection",
        json={"checkpoint_path": "models/non_existent_model_checkpoint_123.pt"},
    )
    assert res_an.status_code == 200
    an_data = res_an.json()

    assert an_data["status"] == "insufficient_data"
    assert an_data["confidence"] is None
    assert "checkpoint missing" in an_data["warnings"][0].lower()


def test_model_output_statistics_and_checkpoint_sha256_provenance(tmp_path):
    # 1. Create a dummy trained U-Net checkpoint
    dummy_img_dir = tmp_path / "train_img"
    dummy_mask_dir = tmp_path / "train_mask"
    dummy_img_dir.mkdir()
    dummy_mask_dir.mkdir()

    for i in range(3):
        img_arr = (np.random.rand(64, 64) * 255).astype(np.uint8)
        mask_arr = np.zeros((64, 64), dtype=np.uint8)
        if i == 0:
            mask_arr[10:30, 10:30] = 255
        cv2.imwrite(str(dummy_img_dir / f"sample_{i}.png"), img_arr)
        cv2.imwrite(str(dummy_mask_dir / f"sample_{i}.png"), mask_arr)

    ckpt_path = tmp_path / "provenance_test_model.pt"
    train_model(
        images_dir=dummy_img_dir,
        masks_dir=dummy_mask_dir,
        epochs=1,
        batch_size=2,
        image_size=64,
        out_path=ckpt_path,
        seed=42,
    )
    assert ckpt_path.exists()
    expected_ckpt_sha256 = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()

    # 2. Create case and upload SAR image evidence
    res_case = client.post("/cases", json={"name": "Provenance Audit Case"})
    case_id = res_case.json()["case_id"]

    sar_bytes = cv2.imencode(".png", (np.random.rand(64, 64) * 255).astype(np.uint8))[1].tobytes()
    expected_sar_sha256 = hashlib.sha256(sar_bytes).hexdigest()

    res_ev = client.post(
        f"/cases/{case_id}/evidence",
        files={"file": ("sar_scene.png", sar_bytes, "image/png")},
        data={"evidence_type": "sar_image", "source": "Sentinel-1A"},
    )
    sar_ev_id = res_ev.json()["evidence_id"]
    assert res_ev.json()["sha256"] == expected_sar_sha256

    # 3. Run oil detection analysis
    res_an = client.post(
        f"/cases/{case_id}/analysis/oil-detection",
        json={"checkpoint_path": str(ckpt_path), "threshold": 0.5, "sar_evidence_id": sar_ev_id},
    )
    assert res_an.status_code == 200
    an_data = res_an.json()

    # Provenance audit assertions
    assert an_data["status"] == "completed"
    assert an_data["confidence"] is None  # Must NOT contain invalid heuristic confidence
    assert an_data["configuration"]["checkpoint_sha256"] == expected_ckpt_sha256
    assert an_data["input_evidence_ids"] == [sar_ev_id]
    assert an_data["input_hashes"] == [expected_sar_sha256]

    res_dict = an_data["result"]
    assert "oil_fraction" in res_dict
    assert "mean_probability" in res_dict
    assert "max_probability" in res_dict
    assert "threshold" in res_dict
    assert res_dict["threshold"] == 0.5

    # Verify output binary and probability mask SHA256 hashes
    bin_mask_path = Path(res_dict["binary_mask_path"])
    prob_mask_path = Path(res_dict["probability_mask_path"])
    assert bin_mask_path.exists()
    assert prob_mask_path.exists()

    expected_bin_sha256 = hashlib.sha256(bin_mask_path.read_bytes()).hexdigest()
    expected_prob_sha256 = hashlib.sha256(prob_mask_path.read_bytes()).hexdigest()

    assert res_dict["binary_mask_sha256"] == expected_bin_sha256
    assert res_dict["probability_mask_sha256"] == expected_prob_sha256


def test_deterministic_inference_output_statistics(tmp_path):
    dummy_img_dir = tmp_path / "train_img"
    dummy_mask_dir = tmp_path / "train_mask"
    dummy_img_dir.mkdir()
    dummy_mask_dir.mkdir()

    for i in range(2):
        cv2.imwrite(str(dummy_img_dir / f"s_{i}.png"), np.zeros((32, 32), dtype=np.uint8))
        cv2.imwrite(str(dummy_mask_dir / f"s_{i}.png"), np.zeros((32, 32), dtype=np.uint8))

    ckpt_path = tmp_path / "stat_test_model.pt"
    train_model(
        images_dir=dummy_img_dir,
        masks_dir=dummy_mask_dir,
        epochs=1,
        batch_size=2,
        image_size=32,
        out_path=ckpt_path,
        seed=42,
    )

    test_img_path = tmp_path / "test_sar_input.png"
    cv2.imwrite(str(test_img_path), np.ones((64, 64), dtype=np.uint8) * 128)

    bin_out = tmp_path / "bin_out.png"
    prob_out = tmp_path / "prob_out.png"

    inf_res = run_inference(
        checkpoint_path=ckpt_path,
        image_path=test_img_path,
        binary_out_path=bin_out,
        prob_out_path=prob_out,
        threshold=0.5,
    )

    assert "oil_fraction" in inf_res
    assert "mean_probability" in inf_res
    assert "max_probability" in inf_res
    assert "threshold" in inf_res
    assert inf_res["threshold"] == 0.5
    assert 0.0 <= inf_res["oil_fraction"] <= 1.0
    assert 0.0 <= inf_res["mean_probability"] <= 1.0
    assert 0.0 <= inf_res["max_probability"] <= 1.0
    if inf_res["mean_oil_probability"] is not None:
        assert 0.0 <= inf_res["mean_oil_probability"] <= 1.0
