"""
VARUNA — Slicksmith Balanced Random Geo Sampler & Integral Mask
Adapted from: Halyjo/slicksmith-ttom (src/slicksmith_ttom/deep_learning/BalancedRandomGeoSampler.py)
License: MIT (Copyright (c) 2025 Harald Lykke Joakimsen)
Commit SHA: 9ccd35df53568c7e64121a2ae7c855f4545396ba
"""

from __future__ import annotations

import contextlib
import random
from pathlib import Path
from typing import Iterator, Optional, Tuple
from warnings import warn

import rasterio
import torch
from affine import Affine
from rasterio.enums import Resampling
from rasterio.merge import merge as rio_merge
from rasterio.vrt import WarpedVRT

try:
    from torchgeo.datasets.utils import BoundingBox
    from torchgeo.samplers import RandomGeoSampler, get_random_bounding_box
    HAS_TORCHGEO = True
except ImportError:
    HAS_TORCHGEO = False
    RandomGeoSampler = object  # type: ignore
    BoundingBox = object  # type: ignore

__all__ = [
    "BalancedRandomGeoSampler",
    "build_integral_mask",
    "build_integral_mask_from_raster_dataset",
]


def build_integral_mask(mask: torch.Tensor) -> torch.Tensor:
    """Convert a binary 2-D mask to its integral image with (1, 1) padding.

    Calculates 2D prefix sums for fast O(1) rectangular query of oil presence.
    """
    mask = mask.to(torch.int32)
    integral = torch.cumsum(torch.cumsum(mask, dim=0), dim=1)
    return torch.nn.functional.pad(integral, (1, 0, 1, 0))


def _raster_files(ds):
    """Return a list of file paths for a TorchGeo RasterDataset."""
    try:
        return ds.files
    except AttributeError as e:
        files = sorted(Path(ds.root).glob(ds.filename_glob))
        if not files:
            raise FileNotFoundError("No raster tiles found in dataset root") from e
        return files


def compute_res_for_shape(srcs, target_shape: Tuple[int, int]):
    """Compute target resolution given bounding box of all sources and desired shape."""
    minx = min(s.bounds.left for s in srcs)
    maxx = max(s.bounds.right for s in srcs)
    miny = min(s.bounds.bottom for s in srcs)
    maxy = max(s.bounds.top for s in srcs)
    res_x = (maxx - minx) / target_shape[1]
    res_y = (maxy - miny) / target_shape[0]
    return (res_x, res_y), (minx, miny, maxx, maxy)


def build_integral_mask_from_raster_dataset(
    label_ds,
    *,
    reference_ds: Optional[object] = None,
    band: int = 1,
    resampling: Resampling = Resampling.nearest,
    to_device: Optional[torch.device | str] = "cpu",
) -> Tuple[torch.Tensor, Affine]:
    """Mosaic label rasters into a single integral image for rapid patch sampling."""
    files = _raster_files(label_ds)
    if not files:
        raise ValueError("Label dataset contains no raster files")

    if reference_ds is not None:
        try:
            target_crs = reference_ds.crs
        except AttributeError:
            ref_path = _raster_files(reference_ds)[0]
            with rasterio.open(str(ref_path)) as ref_src:
                target_crs = ref_src.crs
    else:
        with rasterio.open(str(files[0])) as src0:
            target_crs = src0.crs

    srcs = []
    for fp in files:
        src = rasterio.open(str(fp))
        if src.crs != target_crs:
            src = WarpedVRT(src, crs=target_crs, resampling=resampling)
        srcs.append(src)

    target_mosaic_shape = (512, 512)
    res, bounds = compute_res_for_shape(srcs, target_mosaic_shape)
    mosaic, out_transform = rio_merge(srcs, bounds=bounds, res=res, nodata=0, target_aligned_pixels=True)

    for s in srcs:
        with contextlib.suppress(Exception):
            s.close()

    mask = (mosaic[band - 1] != 0).astype("int32")
    mask_t = torch.from_numpy(mask)
    if to_device is not None:
        mask_t = mask_t.to(to_device)

    return build_integral_mask(mask_t), out_transform


class BalancedRandomGeoSampler(RandomGeoSampler):
    """RandomGeoSampler yielding a user-specified ratio of positive to negative patches."""

    def __init__(
        self,
        dataset,
        size,
        pos_ratio: float = 0.5,
        integral_mask: Optional[torch.Tensor] = None,
        integral_transform: Optional[Affine] = None,
        length: Optional[int] = None,
        **kwargs,
    ) -> None:
        if not HAS_TORCHGEO:
            raise ImportError("torchgeo must be installed to use BalancedRandomGeoSampler")

        super().__init__(
            dataset=dataset,
            size=size,
            length=length,
            **kwargs,
        )

        if not 0.0 <= pos_ratio <= 1.0:
            raise ValueError("pos_ratio must lie strictly between 0 and 1")

        self.pos_ratio = float(pos_ratio)
        self.neg_ratio = 1.0 - self.pos_ratio
        self.integral_mask = integral_mask
        self.integral_transform = integral_transform

        if (integral_mask is not None) ^ (integral_transform is not None):
            raise ValueError(
                "integral_mask and integral_transform must be provided together"
            )

        if integral_transform is not None:
            a, _, c, _, e, f = integral_transform[:6]
            self._px_size_x = a
            self._px_size_y = -e
            self._origin_x = c
            self._origin_y = f

        if integral_mask is None:
            self.dataset = dataset

    def __iter__(self) -> Iterator[BoundingBox]:
        want_positive = random.random
        draw_bbox = self._draw_bbox
        N = len(self)
        i = 0
        while i < N:
            yield draw_bbox(want_positive() < self.pos_ratio)
            i += 1

    def _draw_bbox(self, want_pos: bool, max_iter: int = 1000) -> BoundingBox:
        is_pos = self._is_positive
        areas = self.areas
        hits = self.hits
        size = self.size
        res = self.res

        for _ in range(max_iter):
            idx = torch.multinomial(areas, 1)
            hit = hits[idx]
            bbox = get_random_bounding_box(BoundingBox(*hit.bounds), size, res)
            if is_pos(bbox) == want_pos:
                return bbox
        warn(
            f"Tried {max_iter} random boxes without finding "
            "a positive patch so returned a negative one.",
            stacklevel=2,
        )
        return bbox

    def _is_positive(self, bbox: BoundingBox) -> bool:
        if self.integral_mask is None:
            sample = self.dataset.datasets[1][bbox]
            return sample["mask"].sum().item() > 0

        col0 = int((bbox.minx - self._origin_x) / self._px_size_x) + 1
        col1 = int((bbox.maxx - self._origin_x) / self._px_size_x) + 1
        row0 = int((self._origin_y - bbox.maxy) / self._px_size_y) + 1
        row1 = int((self._origin_y - bbox.miny) / self._px_size_y) + 1

        I = self.integral_mask
        col0 = max(1, min(col0, I.shape[1] - 1))
        col1 = max(1, min(col1, I.shape[1] - 1))
        row0 = max(1, min(row0, I.shape[0] - 1))
        row1 = max(1, min(row1, I.shape[0] - 1))

        s = (
            I[row1, col1]
            - I[row0 - 1, col1]
            - I[row1, col0 - 1]
            + I[row0 - 1, col0 - 1]
        )
        return s.item() > 0
