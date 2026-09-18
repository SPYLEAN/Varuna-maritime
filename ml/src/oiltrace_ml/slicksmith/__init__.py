"""
VARUNA — Slicksmith TTOM Integration
Source: Halyjo/slicksmith-ttom (MIT License, Copyright (c) 2025 Harald Lykke Joakimsen)
Commit SHA: 9ccd35df53568c7e64121a2ae7c855f4545396ba

CRITICAL POLICY NOTE:
Slicksmith pseudo-timestamps (e.g. year 2050 timestamps) are ML indexing metadata ONLY
to prevent spatial tile collisions in TorchGeo.
NEVER use them as Sentinel acquisition timestamps or VARUNA case provenance.
"""

from .balanced_geo_sampler import (
    build_integral_mask,
    build_integral_mask_from_raster_dataset,
)

__all__ = [
    "build_integral_mask",
    "build_integral_mask_from_raster_dataset",
]
