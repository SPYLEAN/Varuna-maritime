from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import torch

from .model import SmallUNet


CHECKPOINT_SCHEMA_VERSION = 1
SMALL_UNET_ARCHITECTURE = "small_unet"
FROZEN_V0_CHECKPOINT_NAME = "samudranetra_oilseg_v0.pt"


def create_checkpoint_metadata(
    *,
    model_architecture: str,
    model_version: str,
    input_channels: int,
    channel_order: Sequence[str],
    preprocessing: Mapping[str, Any],
    training_dataset_version: str,
    epoch: int,
    validation_metrics: Mapping[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    order = [str(value).upper() for value in channel_order]
    if input_channels < 1:
        raise ValueError("input_channels must be positive")
    if len(order) != input_channels:
        raise ValueError("channel_order length must equal input_channels")
    if len(set(order)) != len(order):
        raise ValueError("channel_order cannot contain duplicates")
    if not model_architecture or not model_version or not training_dataset_version:
        raise ValueError("Architecture, model version, and dataset version are required")

    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "model_architecture": model_architecture,
        "model_version": model_version,
        "input_channels": int(input_channels),
        "channel_order": order,
        "preprocessing": dict(preprocessing),
        "training_dataset_version": training_dataset_version,
        "epoch": int(epoch),
        "validation_metrics": dict(validation_metrics),
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }


def build_checkpoint(
    model: torch.nn.Module,
    *,
    image_size: int,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a V1 checkpoint while retaining legacy top-level fields."""

    required = {
        "model_architecture",
        "model_version",
        "input_channels",
        "channel_order",
        "preprocessing",
        "training_dataset_version",
        "epoch",
        "validation_metrics",
        "created_at",
    }
    missing = sorted(required - set(metadata))
    if missing:
        raise ValueError(f"Checkpoint metadata is missing fields: {missing}")

    return {
        "model": model.state_dict(),
        "image_size": int(image_size),
        "epoch": int(metadata["epoch"]),
        "val_metrics": dict(metadata["validation_metrics"]),
        "metadata": dict(metadata),
    }


def _looks_like_state_dict(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        isinstance(key, str) and isinstance(tensor, torch.Tensor)
        for key, tensor in value.items()
    )


def unpack_checkpoint(checkpoint: Any) -> tuple[Mapping[str, torch.Tensor], dict[str, Any], int]:
    """Return state, normalized metadata, and image size for V0 or V1 files."""

    if isinstance(checkpoint, Mapping) and "model" in checkpoint:
        state_dict = checkpoint["model"]
        if not _looks_like_state_dict(state_dict):
            raise ValueError("Checkpoint 'model' entry is not a valid state dict")
        image_size = int(checkpoint.get("image_size", 256))
        metadata = dict(checkpoint.get("metadata", {}))
        if "epoch" not in metadata and "epoch" in checkpoint:
            metadata["epoch"] = int(checkpoint["epoch"])
        if "validation_metrics" not in metadata and "val_metrics" in checkpoint:
            metadata["validation_metrics"] = dict(checkpoint["val_metrics"])
    elif _looks_like_state_dict(checkpoint):
        state_dict = checkpoint
        image_size = 256
        metadata = {}
    else:
        raise ValueError("Unsupported checkpoint format")

    inferred = infer_small_unet_config(state_dict)
    if "input_channels" in metadata and int(metadata["input_channels"]) != inferred["input_channels"]:
        raise ValueError("Checkpoint metadata input_channels does not match model weights")
    metadata.setdefault("model_architecture", SMALL_UNET_ARCHITECTURE)
    metadata.setdefault("model_version", "v0-legacy")
    metadata.setdefault("input_channels", inferred["input_channels"])
    metadata.setdefault(
        "channel_order",
        ["GRAYSCALE"] if inferred["input_channels"] == 1 else [f"CHANNEL_{i}" for i in range(inferred["input_channels"])],
    )
    metadata.setdefault("preprocessing", {"method": "legacy_per_image_minmax"})
    metadata.setdefault("training_dataset_version", "unknown-legacy")
    metadata.setdefault("epoch", None)
    metadata.setdefault("validation_metrics", {})
    metadata.setdefault("created_at", None)
    metadata.setdefault("schema_version", 0)
    if len(metadata["channel_order"]) != inferred["input_channels"]:
        raise ValueError("Checkpoint metadata channel_order does not match model input channels")
    metadata["base_channels"] = inferred["base_channels"]
    metadata["output_channels"] = inferred["output_channels"]
    return state_dict, metadata, image_size


def infer_small_unet_config(state_dict: Mapping[str, torch.Tensor]) -> dict[str, int]:
    first = state_dict.get("enc1.block.0.weight")
    head = state_dict.get("head.weight")
    if first is None or not isinstance(first, torch.Tensor) or first.ndim != 4:
        raise ValueError("Checkpoint does not contain the expected SmallUNet first convolution")
    if head is None or not isinstance(head, torch.Tensor) or head.ndim != 4:
        raise ValueError("Checkpoint does not contain the expected SmallUNet output head")
    return {
        "input_channels": int(first.shape[1]),
        "base_channels": int(first.shape[0]),
        "output_channels": int(head.shape[0]),
    }


def load_model_from_checkpoint(
    checkpoint_path: str | Path,
    *,
    device: torch.device | str = "cpu",
) -> tuple[SmallUNet, dict[str, Any], int]:
    path = Path(checkpoint_path)
    if not path.exists():
        raise FileNotFoundError(f"Checkpoint file not found: {path}")

    checkpoint = torch.load(path, map_location=device, weights_only=False)
    state_dict, metadata, image_size = unpack_checkpoint(checkpoint)
    if metadata["model_architecture"] != SMALL_UNET_ARCHITECTURE:
        raise ValueError(f"Unsupported model architecture: {metadata['model_architecture']}")

    model = SmallUNet(
        in_channels=int(metadata["input_channels"]),
        out_channels=int(metadata["output_channels"]),
        base=int(metadata["base_channels"]),
    ).to(device)
    model.load_state_dict(state_dict)
    return model, metadata, image_size
