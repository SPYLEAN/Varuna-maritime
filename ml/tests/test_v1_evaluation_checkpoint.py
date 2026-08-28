import hashlib
from pathlib import Path

import numpy as np
import pytest
import rasterio
import torch
from rasterio.transform import from_origin
from torch.utils.data import DataLoader, Dataset

from ml.src.oiltrace_ml.checkpoint import (
    SMALL_UNET_ARCHITECTURE,
    build_checkpoint,
    create_checkpoint_metadata,
    load_model_from_checkpoint,
)
from ml.src.oiltrace_ml.evaluate import evaluate_model
from ml.src.oiltrace_ml.infer import run_inference
from ml.src.oiltrace_ml.model import SmallUNet
from ml.src.oiltrace_ml.preprocessing import SARPreprocessingConfig
from ml.src.oiltrace_ml.train import train_model


class CategoryDataset(Dataset):
    def __init__(self):
        self.samples = [
            (
                torch.tensor([[[20.0, -20.0], [-20.0, -20.0]]]),
                torch.tensor([[[1.0, 0.0], [0.0, 0.0]]]),
                {"scene_category": "oil", "scene_id": "oil-1"},
            ),
            (
                torch.tensor([[[20.0, -20.0], [-20.0, -20.0]]]),
                torch.zeros((1, 2, 2)),
                {"scene_category": "lookalike", "scene_id": "lookalike-1"},
            ),
            (
                torch.full((1, 2, 2), -20.0),
                torch.zeros((1, 2, 2)),
                {"scene_category": "no_oil", "scene_id": "no-oil-1"},
            ),
        ]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        return self.samples[index]


class IdentityLogitModel(torch.nn.Module):
    def forward(self, inputs):
        return inputs


def test_evaluation_reports_global_and_category_false_positives():
    report = evaluate_model(
        IdentityLogitModel(),
        DataLoader(CategoryDataset(), batch_size=3, shuffle=False),
        threshold=0.5,
        oil_fraction_threshold=0.10,
    )

    assert set(report["global_segmentation"]) == {"dice", "iou", "precision", "recall"}
    assert report["categories"]["oil"]["dice"] > 0.999
    assert report["categories"]["lookalike"]["false_positive_scene_rate"] == 1.0
    assert report["categories"]["lookalike"]["mean_predicted_oil_fraction"] == 0.25
    assert report["categories"]["lookalike"]["maximum_predicted_oil_fraction"] == 0.25
    assert report["categories"]["lookalike"]["percentage_above_oil_fraction_threshold"] == 100.0
    assert report["categories"]["no_oil"]["false_positive_scene_rate"] == 0.0
    assert report["categories"]["no_oil"]["mean_predicted_oil_fraction"] == 0.0
    assert report["categories"]["no_oil"]["percentage_above_oil_fraction_threshold"] == 0.0


def test_v1_checkpoint_metadata_and_two_channel_loading(tmp_path):
    model = SmallUNet(in_channels=2, base=8)
    preprocessing = SARPreprocessingConfig().to_dict()
    metadata = create_checkpoint_metadata(
        model_architecture=SMALL_UNET_ARCHITECTURE,
        model_version="oilseg-v1-test",
        input_channels=2,
        channel_order=("VV", "VH"),
        preprocessing=preprocessing,
        training_dataset_version="synthetic-s1-v1",
        epoch=3,
        validation_metrics={"dice": 0.75, "iou": 0.6},
        created_at="2026-08-28T00:00:00+00:00",
    )
    checkpoint_path = tmp_path / "v1.pt"
    torch.save(build_checkpoint(model, image_size=128, metadata=metadata), checkpoint_path)

    loaded_model, loaded_metadata, image_size = load_model_from_checkpoint(checkpoint_path)

    assert loaded_model.in_channels == 2
    assert loaded_model(torch.randn(1, 2, 32, 32)).shape == (1, 1, 32, 32)
    assert image_size == 128
    assert loaded_metadata["model_architecture"] == "small_unet"
    assert loaded_metadata["model_version"] == "oilseg-v1-test"
    assert loaded_metadata["input_channels"] == 2
    assert loaded_metadata["channel_order"] == ["VV", "VH"]
    assert loaded_metadata["preprocessing"] == preprocessing
    assert loaded_metadata["training_dataset_version"] == "synthetic-s1-v1"
    assert loaded_metadata["epoch"] == 3
    assert loaded_metadata["validation_metrics"]["dice"] == 0.75
    assert loaded_metadata["created_at"] == "2026-08-28T00:00:00+00:00"


def test_legacy_v0_style_checkpoint_remains_loadable(tmp_path):
    model = SmallUNet(in_channels=1, base=8)
    checkpoint_path = tmp_path / "legacy-v0.pt"
    torch.save(
        {
            "model": model.state_dict(),
            "image_size": 64,
            "val_metrics": {"dice": 0.8254},
            "epoch": 5,
        },
        checkpoint_path,
    )

    loaded_model, metadata, image_size = load_model_from_checkpoint(checkpoint_path)

    assert loaded_model.in_channels == 1
    assert image_size == 64
    assert metadata["model_version"] == "v0-legacy"
    assert metadata["input_channels"] == 1
    assert metadata["channel_order"] == ["GRAYSCALE"]
    assert metadata["preprocessing"]["method"] == "legacy_per_image_minmax"
    assert metadata["validation_metrics"]["dice"] == 0.8254


def test_two_channel_inference_uses_checkpoint_preprocessing(tmp_path):
    model = SmallUNet(in_channels=2, base=8)
    preprocessing = SARPreprocessingConfig().to_dict()
    metadata = create_checkpoint_metadata(
        model_architecture=SMALL_UNET_ARCHITECTURE,
        model_version="oilseg-v1-inference-test",
        input_channels=2,
        channel_order=("VV", "VH"),
        preprocessing=preprocessing,
        training_dataset_version="synthetic-s1-v1",
        epoch=1,
        validation_metrics={"dice": 0.5},
    )
    checkpoint_path = tmp_path / "v1-inference.pt"
    torch.save(build_checkpoint(model, image_size=32, metadata=metadata), checkpoint_path)

    transform = from_origin(72.0, 19.0, 0.001, 0.001)
    vv_path = tmp_path / "vv.tif"
    vh_path = tmp_path / "vh.tif"
    for path, value in ((vv_path, -15.0), (vh_path, -20.0)):
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=6,
            width=7,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(np.full((6, 7), value, dtype=np.float32), 1)

    output_path = tmp_path / "prediction.png"
    result = run_inference(
        checkpoint_path,
        vv_path,
        output_path,
        vh_image_path=vh_path,
    )

    assert output_path.exists()
    assert result["input_channels"] == 2
    assert result["channel_order"] == ["VV", "VH"]
    assert result["original_shape"] == (6, 7)


def test_frozen_workspace_v0_checkpoint_loads_without_mutation():
    checkpoint_path = Path("models/oil_detection/samudranetra_oilseg_v0.pt")
    if not checkpoint_path.exists():
        return
    digest_before = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()

    model, metadata, _ = load_model_from_checkpoint(checkpoint_path)

    digest_after = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    assert model.in_channels == 1
    assert metadata["input_channels"] == 1
    assert digest_after == digest_before


def test_training_refuses_frozen_v0_checkpoint_name(tmp_path):
    with pytest.raises(ValueError, match="Refusing to overwrite frozen V0"):
        train_model(out_path=tmp_path / "samudranetra_oilseg_v0.pt")
