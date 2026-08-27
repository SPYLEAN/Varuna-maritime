from __future__ import annotations
import argparse, json
from pathlib import Path
import cv2
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, mapping


def mask_to_features(mask_path: str, reference_raster: str, min_pixels: int = 20):
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None: raise ValueError(f"Could not read {mask_path}")
    binary = (mask > 127).astype(np.uint8)
    with rasterio.open(reference_raster) as src:
        if (src.height, src.width) != binary.shape:
            raise ValueError(f"Mask shape {binary.shape} != raster shape {(src.height, src.width)}")
        feats = []
        for geom, value in shapes(binary, mask=binary.astype(bool), transform=src.transform):
            if value != 1: continue
            poly = shape(geom)
            if poly.area <= 0: continue
            feats.append({"type":"Feature","properties":{},"geometry":mapping(poly)})
        return {"type":"FeatureCollection","name":"oil_spill_prediction","crs":str(src.crs),"features":feats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mask", required=True)
    ap.add_argument("--reference", required=True, help="Original georeferenced GeoTIFF")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    fc = mask_to_features(args.mask, args.reference)
    Path(args.out).write_text(json.dumps(fc, indent=2))
    print(f"wrote {args.out}; polygons={len(fc['features'])}")


if __name__ == "__main__":
    main()
