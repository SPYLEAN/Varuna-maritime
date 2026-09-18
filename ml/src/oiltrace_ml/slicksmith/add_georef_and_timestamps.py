"""
VARUNA — Slicksmith Preprocessing: Georeferencing & ML Indexing Timestamps
Adapted from: Halyjo/slicksmith-ttom (src/slicksmith_ttom/preprocessing/add_georef_and_timestamps.py)
License: MIT (Copyright (c) 2025 Harald Lykke Joakimsen)
Commit SHA: 9ccd35df53568c7e64121a2ae7c855f4545396ba

CRITICAL POLICY MANDATE:
The timestamps generated below (default year 2050) are ARTIFICIAL SYNTHETIC INDEXES
strictly for TorchGeo spatial indexing to prevent tile collisions.
NEVER use them as Sentinel acquisition timestamps, legal evidence timestamps,
or VARUNA case provenance.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Union

import rasterio


def make_timestamped_filename(index: int, base_time: datetime) -> str:
    """Make artificial synthetic timestamp for TorchGeo spatial indexing.

    Uses an artificial future time (e.g. 2050) so it is never confused with real
    Sentinel-1 acquisition timestamps.
    """
    dt = base_time + timedelta(seconds=index)
    return f"{index:05d}_{dt.strftime('%Y%m%dT%H%M%S')}.tif"


def georeference_and_timestamp_images_and_masks(
    root_dir: Union[str, Path],
    dst_dir: Union[str, Path],
    image_dir: str = "Oil",
    mask_dir: str = "Mask_oil",
    output_image_dir: str = "Oil_timestamped",
    output_mask_dir: str = "Mask_oil_georef_timestamped",
    base_time: datetime = datetime(2050, 1, 1, 0, 0, 0),
):
    """Add geospatial metadata to oil spill mask files by copying it from the
    corresponding Sentinel-1 image.

    Renames both image and mask files with artificial synthetic timestamps (in year 2050)
    solely for TorchGeo temporal indexing compatibility.
    """
    root_dir = Path(root_dir)
    dst_dir = Path(dst_dir)

    os.makedirs(dst_dir / output_image_dir, exist_ok=True)
    os.makedirs(dst_dir / output_mask_dir, exist_ok=True)

    image_filenames = sorted(
        f for f in os.listdir(root_dir / image_dir) if f.endswith(".tif")
    )

    for filename in image_filenames:
        image_path = root_dir / image_dir / filename
        mask_path = root_dir / mask_dir / filename
        index = int(Path(filename).stem.split("_")[0])
        new_filename = make_timestamped_filename(index, base_time)
        output_image_path = dst_dir / output_image_dir / new_filename
        output_mask_path = dst_dir / output_mask_dir / new_filename

        with rasterio.open(image_path) as img_src:
            image_data = img_src.read()
            crs = img_src.crs
            transform = img_src.transform
            img_dtype = img_src.dtypes[0]
            count = img_src.count
            height = img_src.height
            width = img_src.width

        with rasterio.open(
            output_image_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=count,
            dtype=img_dtype,
            crs=crs,
            transform=transform,
        ) as dst_img:
            dst_img.write(image_data)

        try:
            with rasterio.open(mask_path) as mask_src:
                mask_data = mask_src.read(1)
                mask_dtype = mask_src.dtypes[0]
        except Exception:
            with rasterio.open(
                str(mask_path).replace(".tif", "_segmentation.tif")
            ) as mask_src:
                mask_data = mask_src.read(1)
                mask_dtype = mask_src.dtypes[0]

        timestamp = base_time + timedelta(seconds=index)
        tags = {"TIFFTAG_DATETIME": timestamp.strftime("%Y:%m:%d %H:%M:%S")}

        with rasterio.open(
            output_mask_path,
            "w",
            driver="GTiff",
            height=mask_data.shape[0],
            width=mask_data.shape[1],
            count=1,
            dtype=mask_dtype,
            crs=crs,
            transform=transform,
        ) as dst_mask:
            dst_mask.write(mask_data, 1)
            dst_mask.update_tags(**tags)
