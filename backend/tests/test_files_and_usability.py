import hashlib
from pathlib import Path
import numpy as np
import cv2
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.storage import storage
from ml.src.oiltrace_ml.train import train_model


@pytest.fixture(autouse=True)
def temp_storage(tmp_path):
    original_dir = storage.storage_dir
    storage.storage_dir = tmp_path / "cases"
    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    storage.storage_dir = original_dir


client = TestClient(app)


def test_case_creation_nullable_fields_and_timestamp_distinction():
    res = client.post("/cases", json={"name": "Nullable Fields Benchmark Case"})
    assert res.status_code == 201
    case_data = res.json()

    # 1. case_id auto-generated
    assert case_data["case_id"].startswith("case_")
    assert case_data["name"] == "Nullable Fields Benchmark Case"

    # 2. Coordinates nullable and NOT replaced with 0,0
    assert case_data["latitude"] is None
    assert case_data["longitude"] is None

    # 3. Observation timestamp distinct from creation timestamp
    assert case_data["observation_timestamp"] is None
    assert case_data["created_at"] is not None


def test_get_evidence_file_secure_serving():
    res_case = client.post("/cases", json={"name": "File Endpoint Case"})
    case_id = res_case.json()["case_id"]

    content = b"SECURE_EVIDENCE_FILE_BYTES_5555"
    res_ev = client.post(
        f"/cases/{case_id}/evidence",
        files={"file": ("test_doc.png", content, "image/png")},
        data={"evidence_type": "sar_image"},
    )
    assert res_ev.status_code == 201
    ev_id = res_ev.json()["evidence_id"]

    # Retrieve file via GET endpoint
    res_file = client.get(f"/cases/{case_id}/evidence/{ev_id}/file")
    assert res_file.status_code == 200
    assert res_file.content == content


def test_get_output_file_secure_serving(tmp_path):
    # 1. Create dummy trained model
    dummy_img_dir = tmp_path / "t_img"
    dummy_mask_dir = tmp_path / "t_mask"
    dummy_img_dir.mkdir()
    dummy_mask_dir.mkdir()

    for i in range(2):
        cv2.imwrite(str(dummy_img_dir / f"s_{i}.png"), np.zeros((32, 32), dtype=np.uint8))
        cv2.imwrite(str(dummy_mask_dir / f"s_{i}.png"), np.zeros((32, 32), dtype=np.uint8))

    ckpt_path = tmp_path / "test_model.pt"
    train_model(images_dir=dummy_img_dir, masks_dir=dummy_mask_dir, epochs=1, batch_size=2, image_size=32, out_path=ckpt_path, seed=42)

    # 2. Create case and upload SAR image
    res_case = client.post("/cases", json={"name": "Output Retrieval Case"})
    case_id = res_case.json()["case_id"]

    sar_bytes = cv2.imencode(".png", np.zeros((32, 32), dtype=np.uint8))[1].tobytes()
    res_ev = client.post(f"/cases/{case_id}/evidence", files={"file": ("sar.png", sar_bytes, "image/png")}, data={"evidence_type": "sar_image"})
    sar_ev_id = res_ev.json()["evidence_id"]

    # 3. Run oil detection
    res_an = client.post(f"/cases/{case_id}/analysis/oil-detection", json={"checkpoint_path": str(ckpt_path), "sar_evidence_id": sar_ev_id})
    assert res_an.status_code == 200
    bin_path = res_an.json()["result"]["binary_mask_path"]
    filename = Path(bin_path).name

    # 4. Fetch output mask via GET /cases/{case_id}/outputs/{filename}
    res_out = client.get(f"/cases/{case_id}/outputs/{filename}")
    assert res_out.status_code == 200
    assert len(res_out.content) > 0


def test_output_file_path_traversal_rejection():
    res_case = client.post("/cases", json={"name": "Traversal Protection Case"})
    case_id = res_case.json()["case_id"]

    res_out = client.get(f"/cases/{case_id}/outputs/../../etc/passwd")
    # Sanitized filename passwd does not exist in outputs directory, so returns 404
    assert res_out.status_code == 404
