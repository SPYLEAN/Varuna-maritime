from __future__ import annotations
from pathlib import Path
from typing import Iterable
import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


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
