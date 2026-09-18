"""
VARUNA — Slicksmith TTOM Datasets & DataModule
Adapted from: Halyjo/slicksmith-ttom (src/slicksmith_ttom/deep_learning/torchgeo_datasets.py)
License: MIT (Copyright (c) 2025 Harald Lykke Joakimsen)
Commit SHA: 9ccd35df53568c7e64121a2ae7c855f4545396ba

CRITICAL POLICY NOTE:
Slicksmith pseudo timestamps are ML indexing metadata ONLY.
NEVER use them as Sentinel acquisition timestamps or VARUNA provenance.
"""

from __future__ import annotations
import os
from pathlib import Path

try:
    import torch
    from torch.utils.data import DataLoader
    from torchgeo.datamodules import GeoDataModule
    from torchgeo.datasets import (
        IntersectionDataset,
        RasterDataset,
        concat_samples,
        random_bbox_assignment,
        stack_samples,
    )
    from torchgeo.samplers import GridGeoSampler
    HAS_TORCHGEO = True
except ImportError:
    HAS_TORCHGEO = False
    RasterDataset = object  # type: ignore
    GeoDataModule = object  # type: ignore

from .balanced_geo_sampler import (
    BalancedRandomGeoSampler,
    build_integral_mask_from_raster_dataset,
)


class TtomLabelDataset(RasterDataset):
    """Slicksmith TTOM 1-band binary label raster dataset."""
    filename_glob = "*.tif"
    filename_regex = r"(?P<index>\d+)_(?P<date>\d{8}T\d{6}).tif"
    date_format = "%Y%m%dT%H%M%S"
    is_image = False


class TtomImageDataset(RasterDataset):
    """Slicksmith TTOM SAR input imagery dataset."""
    filename_glob = "*.tif"
    filename_regex = r"(?P<index>\d+)_(?P<date>\d{8}T\d{6}).tif"
    date_format = "%Y%m%dT%H%M%S"
    is_image = True


class TtomDataModule(GeoDataModule):
    """Ttom remote-sensing segmentation datamodule for PyTorch Lightning."""

    def __init__(
        self,
        train_img_path: os.PathLike,
        train_lbl_path: os.PathLike,
        val_img_path: os.PathLike,
        val_lbl_path: os.PathLike,
        test_img_path: os.PathLike,
        test_lbl_path: os.PathLike,
        num_train_patches: int | None = 1000,
        num_val_patches: int | None = 100,
        num_test_patches: int | None = 1000,
        num_examples: int = 10,
        batch_size: int = 4,
        patch_size: tuple[int, int] = (480, 480),
        split_only_train: bool = False,
        num_workers: int | None = None,
        pos_ratio: float = 0.5,
    ):
        if not HAS_TORCHGEO:
            raise ImportError("torchgeo must be installed to use TtomDataModule")

        super().__init__(
            dataset_class=IntersectionDataset,
            batch_size=batch_size,
            patch_size=patch_size,
            num_workers=num_workers,
        )
        self.train_img_path = train_img_path
        self.train_lbl_path = train_lbl_path
        self.val_img_path = val_img_path
        self.val_lbl_path = val_lbl_path
        self.test_img_path = test_img_path
        self.test_lbl_path = test_lbl_path
        self.num_train_patches = num_train_patches
        self.num_val_patches = num_val_patches
        self.num_test_patches = num_test_patches
        self.num_examples = num_examples
        self.split_only_train = split_only_train
        self.pos_ratio = pos_ratio

    def setup(self, stage: str = "fit"):
        train_dataset = self._load_ttom_dataset(
            self.train_img_path, self.train_lbl_path
        )

        if self.split_only_train:
            generator = torch.Generator().manual_seed(0)
            (
                self.train_dataset,
                self.val_dataset,
                self.test_dataset,
            ) = random_bbox_assignment(train_dataset, [0.7, 0.1, 0.2], generator)
        else:
            self.train_dataset = train_dataset
            self.val_dataset = self._load_ttom_dataset(
                self.val_img_path, self.val_lbl_path
            )
            self.test_dataset = self._load_ttom_dataset(
                self.test_img_path, self.test_lbl_path
            )

        self._setup_samplers()

    def example_dataloader(self):
        return DataLoader(
            dataset=self.val_dataset,
            sampler=self.example_sampler,
            batch_size=self.num_examples,
            collate_fn=stack_samples,
        )

    def _setup_samplers(self):
        train_integral_mask, train_integral_transform = (
            build_integral_mask_from_raster_dataset(self.train_dataset.datasets[1])
        )
        self.train_sampler = BalancedRandomGeoSampler(
            self.train_dataset,
            self.patch_size,
            length=self.num_train_patches,
            pos_ratio=self.pos_ratio,
            integral_mask=train_integral_mask,
            integral_transform=train_integral_transform,
        )

        if self.num_val_patches is not None:
            val_integral_mask, val_integral_transform = (
                build_integral_mask_from_raster_dataset(self.val_dataset.datasets[1])
            )
            self.val_sampler = BalancedRandomGeoSampler(
                self.val_dataset,
                self.patch_size,
                length=self.num_val_patches,
                pos_ratio=self.pos_ratio,
                integral_mask=val_integral_mask,
                integral_transform=val_integral_transform,
            )
        else:
            self.val_sampler = GridGeoSampler(
                self.val_dataset, self.patch_size, self.patch_size
            )

        if self.num_test_patches:
            test_integral_mask, test_integral_transform = (
                build_integral_mask_from_raster_dataset(self.test_dataset.datasets[1])
            )
            self.test_sampler = BalancedRandomGeoSampler(
                self.test_dataset,
                self.patch_size,
                length=self.num_test_patches,
                pos_ratio=self.pos_ratio,
                integral_mask=test_integral_mask,
                integral_transform=test_integral_transform,
            )
        else:
            self.test_sampler = GridGeoSampler(
                self.test_dataset, self.patch_size, self.patch_size
            )

        self.example_sampler = BalancedRandomGeoSampler(
            self.val_dataset,
            self.patch_size,
            length=self.num_examples,
            pos_ratio=self.pos_ratio,
        )

    @staticmethod
    def _load_ttom_dataset(img_path, lbl_path):
        return IntersectionDataset(
            dataset1=TtomImageDataset(
                img_path,
                transforms=lambda x: x,
            ),
            dataset2=TtomLabelDataset(
                lbl_path,
                transforms=lambda x: x,
            ),
            collate_fn=concat_samples,
        )
