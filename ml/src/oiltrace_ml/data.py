from __future__ import annotations
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
import cv2
import numpy as np
import rasterio
import torch
from torch.utils.data import Dataset

from .preprocessing import SARPreprocessingConfig, config_for_channels, preprocess_sar

EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
GEOTIFF_EXTS = {".tif", ".tiff"}
SCENE_CATEGORIES = frozenset({"oil", "lookalike", "no_oil"})


def list_images(root: str | Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(root)
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in EXTS)


def pair_images_and_masks(image_root: str | Path, mask_root: str | Path) -> list[tuple[Path, Path]]:
    images = list_images(image_root)
    masks = list_images(mask_root)
    mask_by_stem = {p.stem: p for p in masks}
    pairs = [(img, mask_by_stem[img.stem]) for img in images if img.stem in mask_by_stem]
    return pairs


def read_grayscale(path: str | Path) -> np.ndarray:
    arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise ValueError(f"Could not read image: {path}")
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    arr = arr.astype(np.float32)
    lo, hi = float(arr.min()), float(arr.max())
    if hi > lo:
        arr = (arr - lo) / (hi - lo)
    else:
        arr = np.zeros_like(arr, dtype=np.float32)
    return arr


class OilSpillDataset(Dataset):
    """Frozen V0-compatible single-channel image/mask dataset."""

    def __init__(self, pairs: Iterable[tuple[Path, Path]], image_size: int = 256):
        self.pairs = list(pairs)
        self.image_size = image_size
        if not self.pairs:
            raise ValueError("Dataset contains no paired image/mask files")

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        image_path, mask_path = self.pairs[idx]
        image = read_grayscale(image_path)
        mask = read_grayscale(mask_path)
        image = cv2.resize(image, (self.image_size, self.image_size), interpolation=cv2.INTER_LINEAR)
        mask = cv2.resize(mask, (self.image_size, self.image_size), interpolation=cv2.INTER_NEAREST)
        mask = (mask > 0.5).astype(np.float32)
        image = torch.from_numpy(image).unsqueeze(0).float()
        mask = torch.from_numpy(mask).unsqueeze(0).float()
        return image, mask


@dataclass(frozen=True)
class Sentinel1Sample:
    scene_id: str
    vv_path: Path
    vh_path: Path
    mask_path: Path
    scene_category: str
    acquisition_timestamp: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "vv_path", Path(self.vv_path))
        object.__setattr__(self, "vh_path", Path(self.vh_path))
        object.__setattr__(self, "mask_path", Path(self.mask_path))
        object.__setattr__(self, "scene_category", self.scene_category.lower())
        if not self.scene_id.strip():
            raise ValueError("scene_id cannot be empty")
        if self.scene_category not in SCENE_CATEGORIES:
            raise ValueError(
                f"Invalid scene_category {self.scene_category!r}; expected one of {sorted(SCENE_CATEGORIES)}"
            )


def _resolve_manifest_path(value: Any, manifest_dir: Path, field: str, scene_id: str) -> Path:
    if value is None or not str(value).strip():
        raise ValueError(f"Scene {scene_id!r} is missing required field {field!r}")
    path = Path(str(value))
    return path if path.is_absolute() else manifest_dir / path


def _sample_from_record(record: dict[str, Any], manifest_dir: Path) -> Sentinel1Sample:
    scene_id = str(record.get("scene_id", "")).strip()
    if not scene_id:
        raise ValueError("Every manifest record requires a non-empty scene_id")
    category = str(record.get("scene_category", "")).strip().lower()
    timestamp = record.get("acquisition_timestamp")
    return Sentinel1Sample(
        scene_id=scene_id,
        vv_path=_resolve_manifest_path(record.get("vv_path"), manifest_dir, "vv_path", scene_id),
        vh_path=_resolve_manifest_path(record.get("vh_path"), manifest_dir, "vh_path", scene_id),
        mask_path=_resolve_manifest_path(record.get("mask_path"), manifest_dir, "mask_path", scene_id),
        scene_category=category,
        acquisition_timestamp=str(timestamp).strip() if timestamp not in (None, "") else None,
    )


def load_sentinel1_manifest(path: str | Path) -> list[Sentinel1Sample]:
    """Load a CSV, JSON array, or JSONL manifest with explicit VV/VH paths."""

    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    suffix = manifest_path.suffix.lower()
    try:
        if suffix == ".csv":
            with manifest_path.open("r", encoding="utf-8", newline="") as handle:
                records = list(csv.DictReader(handle))
        elif suffix == ".json":
            records = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                raise ValueError("JSON manifest root must be an array")
        elif suffix in {".jsonl", ".ndjson"}:
            records = [
                json.loads(line)
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            raise ValueError("Sentinel-1 manifest must use .csv, .json, .jsonl, or .ndjson")
    except (csv.Error, json.JSONDecodeError) as err:
        raise ValueError(f"Malformed Sentinel-1 manifest {manifest_path}: {err}") from err

    if not records:
        raise ValueError("Sentinel-1 manifest contains no samples")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("Every Sentinel-1 manifest record must be an object")

    samples = [_sample_from_record(record, manifest_path.parent) for record in records]
    scene_ids = [sample.scene_id for sample in samples]
    duplicates = sorted({scene_id for scene_id in scene_ids if scene_ids.count(scene_id) > 1})
    if duplicates:
        raise ValueError(f"Duplicate scene_id values in manifest: {duplicates}")
    return samples


def _check_geotiff_path(path: Path, label: str, scene_id: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Scene {scene_id!r} is missing {label}: {path}")
    if not path.is_file():
        raise ValueError(f"Scene {scene_id!r} {label} is not a file: {path}")
    if path.suffix.lower() not in GEOTIFF_EXTS:
        raise ValueError(f"Scene {scene_id!r} {label} must be a GeoTIFF (.tif/.tiff): {path}")


def _read_geotiff_band(path: Path, label: str) -> tuple[np.ndarray, dict[str, Any]]:
    try:
        with rasterio.open(path) as src:
            if src.count != 1:
                raise ValueError(f"{label} must contain exactly one raster band, found {src.count}: {path}")
            array = src.read(1).astype(np.float32)
            if src.nodata is not None:
                array[array == float(src.nodata)] = np.nan
            tags = src.tags()
            timestamp = next(
                (
                    tags[key]
                    for key in ("ACQUISITION_TIMESTAMP", "SENSING_TIME", "TIFFTAG_DATETIME")
                    if tags.get(key)
                ),
                None,
            )
            metadata = {
                "shape": (src.height, src.width),
                "crs": str(src.crs) if src.crs is not None else "",
                "transform": tuple(float(value) for value in src.transform[:6]),
                "bounds": tuple(float(value) for value in src.bounds),
                "acquisition_timestamp": timestamp or "",
            }
            return array, metadata
    except (rasterio.errors.RasterioError, OSError) as err:
        raise ValueError(f"Could not read {label} GeoTIFF {path}: {err}") from err


def _assert_aligned(reference: dict[str, Any], candidate: dict[str, Any], label: str) -> None:
    if candidate["shape"] != reference["shape"]:
        raise ValueError(f"{label} shape {candidate['shape']} does not match VV shape {reference['shape']}")
    if candidate["crs"] != reference["crs"]:
        raise ValueError(f"{label} CRS {candidate['crs']!r} does not match VV CRS {reference['crs']!r}")
    if not np.allclose(candidate["transform"], reference["transform"], rtol=0.0, atol=1e-9):
        raise ValueError(f"{label} affine transform does not match VV")
    if not np.allclose(candidate["bounds"], reference["bounds"], rtol=0.0, atol=1e-6):
        raise ValueError(f"{label} bounds {candidate['bounds']} do not match VV bounds {reference['bounds']}")


def read_sentinel1_stack(
    vv_path: str | Path,
    vh_path: str | Path,
    *,
    channel_order: Sequence[str] = ("VV", "VH"),
    preprocessing: SARPreprocessingConfig | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Read, align, and preprocess explicit VV/VH single-band GeoTIFFs."""

    order = tuple(str(value).upper() for value in channel_order)
    if len(order) != 2 or set(order) != {"VV", "VH"}:
        raise ValueError("Sentinel-1 channel_order must be an explicit permutation of ('VV', 'VH')")
    config = preprocessing or config_for_channels(order)
    if config.channel_order != order:
        raise ValueError(
            f"Preprocessing channel order {config.channel_order} does not match requested order {order}"
        )

    vv, vv_meta = _read_geotiff_band(Path(vv_path), "VV")
    vh, vh_meta = _read_geotiff_band(Path(vh_path), "VH")
    _assert_aligned(vv_meta, vh_meta, "VH")
    channels = {"VV": vv, "VH": vh}
    stack = np.stack([channels[name] for name in order], axis=0)
    normalized, stats = preprocess_sar(stack, config, return_stats=True)
    metadata = dict(vv_meta)
    metadata["channel_order"] = list(order)
    metadata["preprocessing_stats"] = stats
    return normalized, metadata


def read_binary_geotiff_mask(path: str | Path) -> tuple[np.ndarray, dict[str, Any]]:
    mask, metadata = _read_geotiff_band(Path(path), "mask")
    if not np.isfinite(mask).all():
        raise ValueError(f"Mask contains non-finite or nodata values: {path}")
    unique = np.unique(mask)
    allowed = np.isin(unique, np.array([0.0, 1.0, 255.0], dtype=np.float32))
    if not bool(allowed.all()):
        raise ValueError(f"Mask must be binary with values 0/1 or 0/255, found {unique[:10].tolist()}: {path}")
    return (mask > 0.0).astype(np.float32), metadata


class Sentinel1Dataset(Dataset):
    """Manifest-driven dual-polarization Sentinel-1 segmentation dataset."""

    def __init__(
        self,
        samples: Iterable[Sentinel1Sample] | str | Path,
        image_size: int = 256,
        *,
        channel_order: Sequence[str] = ("VV", "VH"),
        preprocessing: SARPreprocessingConfig | None = None,
        validate_paths: bool = True,
    ):
        self.samples = load_sentinel1_manifest(samples) if isinstance(samples, (str, Path)) else list(samples)
        if not self.samples:
            raise ValueError("Sentinel-1 dataset contains no samples")
        if image_size < 1:
            raise ValueError("image_size must be positive")
        self.image_size = int(image_size)
        self.channel_order = tuple(str(value).upper() for value in channel_order)
        if len(self.channel_order) != 2 or set(self.channel_order) != {"VV", "VH"}:
            raise ValueError("Sentinel-1 channel_order must be an explicit permutation of ('VV', 'VH')")
        self.preprocessing = preprocessing or config_for_channels(self.channel_order)
        if self.preprocessing.channel_order != self.channel_order:
            raise ValueError("Dataset and preprocessing channel_order values must match exactly")

        if validate_paths:
            for sample in self.samples:
                _check_geotiff_path(sample.vv_path, "VV", sample.scene_id)
                _check_geotiff_path(sample.vh_path, "VH", sample.scene_id)
                _check_geotiff_path(sample.mask_path, "mask", sample.scene_id)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        sample = self.samples[idx]
        image, raster_metadata = read_sentinel1_stack(
            sample.vv_path,
            sample.vh_path,
            channel_order=self.channel_order,
            preprocessing=self.preprocessing,
        )
        mask, mask_metadata = read_binary_geotiff_mask(sample.mask_path)
        _assert_aligned(raster_metadata, mask_metadata, "mask")
        if image.shape[1:] != mask.shape:
            raise ValueError(f"Image shape {image.shape[1:]} does not match mask shape {mask.shape}")

        resized_channels = [
            cv2.resize(channel, (self.image_size, self.image_size), interpolation=cv2.INTER_LINEAR)
            for channel in image
        ]
        image_resized = np.stack(resized_channels, axis=0).astype(np.float32)
        mask_resized = cv2.resize(
            mask,
            (self.image_size, self.image_size),
            interpolation=cv2.INTER_NEAREST,
        ).astype(np.float32)

        metadata = {
            "scene_id": sample.scene_id,
            "scene_category": sample.scene_category,
            "channel_order": list(self.channel_order),
            "crs": raster_metadata["crs"],
            "transform": list(raster_metadata["transform"]),
            "bounds": list(raster_metadata["bounds"]),
            "acquisition_timestamp": sample.acquisition_timestamp
            or raster_metadata["acquisition_timestamp"],
            "original_shape": list(raster_metadata["shape"]),
            "preprocessing_stats": raster_metadata["preprocessing_stats"],
            "mask_is_empty": bool(mask.sum() == 0),
        }
        return (
            torch.from_numpy(image_resized).float(),
            torch.from_numpy(mask_resized).unsqueeze(0).float(),
            metadata,
        )


def audit_split_leakage(
    train_samples: Sequence[Sentinel1Sample],
    val_samples: Sequence[Sentinel1Sample],
    test_samples: Sequence[Sentinel1Sample] = (),
) -> dict[str, Any]:
    """Audit dataset splits for scene_id or event leakage to prevent tile leakage."""
    splits = {"train": list(train_samples), "val": list(val_samples), "test": list(test_samples)}
    scene_ids = {name: {s.scene_id for s in samples} for name, samples in splits.items()}

    train_val_scene = scene_ids["train"].intersection(scene_ids["val"])
    train_test_scene = scene_ids["train"].intersection(scene_ids["test"])
    val_test_scene = scene_ids["val"].intersection(scene_ids["test"])

    def _event_id(sample: Sentinel1Sample) -> str:
        if sample.acquisition_timestamp:
            return sample.acquisition_timestamp.split("T")[0]
        parts = sample.scene_id.split("_")
        return parts[0] if len(parts) < 2 else f"{parts[0]}_{parts[1]}"

    event_ids = {name: {_event_id(s) for s in samples} for name, samples in splits.items()}

    train_val_event = event_ids["train"].intersection(event_ids["val"]) if event_ids["val"] else set()
    train_test_event = event_ids["train"].intersection(event_ids["test"]) if event_ids["test"] else set()
    val_test_event = event_ids["val"].intersection(event_ids["test"]) if (event_ids["val"] and event_ids["test"]) else set()

    has_leakage = bool(
        train_val_scene or train_test_scene or val_test_scene or train_val_event or train_test_event or val_test_event
    )

    result = {
        "passed": not has_leakage,
        "scene_id_leakage": {
            "train_val": sorted(train_val_scene),
            "train_test": sorted(train_test_scene),
            "val_test": sorted(val_test_scene),
        },
        "event_leakage": {
            "train_val": sorted(train_val_event),
            "train_test": sorted(train_test_event),
            "val_test": sorted(val_test_event),
        },
    }

    if has_leakage:
        raise ValueError(f"Split leakage audit FAILED: {result}")

    return result


def extract_aligned_patches(
    image: np.ndarray,
    mask: np.ndarray,
    patch_size: int = 256,
    stride: int = 128,
    min_oil_pixels: int = 0,
) -> list[tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]]:
    """Extract identical window patches from multi-channel image and binary mask."""
    channels, height, width = image.shape
    if mask.shape != (height, width):
        raise ValueError(f"Mask shape {mask.shape} does not match image spatial dimensions {(height, width)}")
    if patch_size > height or patch_size > width:
        raise ValueError(f"Patch size {patch_size} is larger than image dimensions {(height, width)}")

    patches = []
    for y in range(0, height - patch_size + 1, stride):
        for x in range(0, width - patch_size + 1, stride):
            img_patch = image[:, y : y + patch_size, x : x + patch_size]
            mask_patch = mask[y : y + patch_size, x : x + patch_size]
            oil_px = int((mask_patch > 0.5).sum())
            if oil_px < min_oil_pixels:
                continue
            patches.append((img_patch, mask_patch, (y, y + patch_size, x, x + patch_size)))

    return patches
