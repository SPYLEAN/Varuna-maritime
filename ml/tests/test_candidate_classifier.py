import json
from pathlib import Path
import numpy as np
import pytest
import torch

from ml.src.oiltrace_ml.candidate_classifier import (
    SingleChannelCandidateClassifier,
    fixed_r001_vv_adapter,
    generate_synthetic_public_dataset,
    train_candidate_classifier,
    PublicSARDataset,
    run_r001_candidate_classifier_inference,
)
from torch.utils.data import DataLoader


def test_single_channel_input_enforcement():
    model = SingleChannelCandidateClassifier(num_classes=2)
    # Test valid single-channel input [B, 1, 224, 224]
    x_valid = torch.randn(2, 1, 224, 224)
    logits = model(x_valid)
    assert logits.shape == (2, 2)

    probs = model.predict_probs(x_valid)
    assert probs.shape == (2, 2)
    assert torch.allclose(probs.sum(dim=1), torch.ones(2), atol=1e-5)

    # 3-channel input should fail or mismatch single-channel conv1
    with pytest.raises(Exception):
        x_invalid = torch.randn(2, 3, 224, 224)
        model(x_invalid)


def test_fixed_r001_vv_adapter():
    # Test fixed clipping range [-30, 0] dB
    vv_raw = np.array([[-35.0, -15.0], [0.0, 5.0]], dtype=np.float32)
    tensor_out = fixed_r001_vv_adapter(vv_raw)

    assert tensor_out.shape == (1, 1, 224, 224)
    assert np.min(tensor_out) >= 0.0 and np.max(tensor_out) <= 1.0
    assert np.all(np.isfinite(tensor_out))


def test_r001_training_lock_safeguard(tmp_path):
    # Manifest row with invalid training_allowed = True on R001 sample must raise RuntimeError
    manifest_p = tmp_path / "manifest.csv"
    manifest_content = (
        "candidate_id,group_id,chip_folder,vv_raw_path,vh_raw_path,mask_path,npy_path,metadata_path,quality_flag,label_status,training_allowed\n"
        "C001,GRP001,chips/C001,chips/C001/vv_raw.tif,chips/C001/vh_raw.tif,chips/C001/candidate_mask.tif,chips/C001/input_2ch.npy,chips/C001/metadata.json,VALID,UNLABELLED_REAL_CASE,True\n"
    )
    with open(manifest_p, "w", encoding="utf-8") as f:
        f.write(manifest_content)

    out_d = tmp_path / "out"
    with pytest.raises(RuntimeError, match="safety violation"):
        run_r001_candidate_classifier_inference(tmp_path, out_d)


def test_model_training_and_metrics_calculation():
    images, labels, scene_ids = generate_synthetic_public_dataset(num_samples=8, seed=42)
    train_ds = PublicSARDataset(images[:4], labels[:4])
    val_ds = PublicSARDataset(images[4:], labels[4:])

    train_ld = DataLoader(train_ds, batch_size=2, shuffle=True)
    val_ld = DataLoader(val_ds, batch_size=2, shuffle=False)

    model, metrics = train_candidate_classifier(train_ld, val_ld, num_epochs=1)

    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1" in metrics
    assert "false_positive_rate_non_oil" in metrics
    assert 0.0 <= metrics["f1"] <= 1.0


def test_model_save_and_load(tmp_path):
    model = SingleChannelCandidateClassifier(num_classes=2)
    model.eval()

    save_path = tmp_path / "model.pt"
    torch.save(model.state_dict(), save_path)

    loaded_model = SingleChannelCandidateClassifier(num_classes=2)
    loaded_model.load_state_dict(torch.load(save_path))
    loaded_model.eval()

    x = torch.randn(1, 1, 224, 224)
    with torch.no_grad():
        out1 = model.predict_probs(x)
        out2 = loaded_model.predict_probs(x)

    assert torch.allclose(out1, out2, atol=1e-6)
