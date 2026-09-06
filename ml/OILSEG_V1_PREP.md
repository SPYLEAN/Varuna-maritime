# OilSeg V1 preparation: Sentinel-1 VV/VH

This document describes the prepared pipeline only. It does not claim that an
OilSeg V1 model has been trained or validated on official Sentinel-1 data.
`models/oil_detection/samudranetra_oilseg_v0.pt` remains the frozen V0 artifact.

## Current architecture audit

Before V1 preparation, `SmallUNet` already exposed an `in_channels` constructor
argument, but every production path still assumed one channel:

- `OilSpillDataset` used OpenCV grayscale conversion and per-image min/max scaling.
- Training always instantiated `SmallUNet()` and saved a minimal checkpoint.
- Evaluation and inference always instantiated a one-channel `SmallUNet()`.
- Checkpoint loading did not identify architecture, channel count/order, or preprocessing.
- Evaluation averaged batch metrics and had no scene-category false-positive analysis.
- GeoTIFF georeferencing was used only later by polygon export, not preserved by the dataset.

The legacy path remains available and unchanged by default. The V1 path adds a
manifest-driven dual-polarization dataset, SAR-specific preprocessing, metadata-aware
checkpoint loading, and category-aware evaluation.

## V1 dataset contract

Use one single-band GeoTIFF for each polarization and one aligned, single-band
binary mask GeoTIFF. A CSV, JSON, JSONL, or NDJSON manifest binds the files and
category metadata explicitly. Relative paths resolve from the manifest directory.

```json
[
  {
    "scene_id": "S1A_IW_20260828T010203_TILE_001",
    "vv_path": "images/S1A_IW_20260828T010203_TILE_001_VV.tif",
    "vh_path": "images/S1A_IW_20260828T010203_TILE_001_VH.tif",
    "mask_path": "masks/S1A_IW_20260828T010203_TILE_001_mask.tif",
    "scene_category": "lookalike",
    "acquisition_timestamp": "2026-08-28T01:02:03Z"
  }
]
```

Required fields are `scene_id`, `vv_path`, `vh_path`, `mask_path`, and
`scene_category`. Categories are exactly `oil`, `lookalike`, or `no_oil`.
`acquisition_timestamp` is optional; when absent, common GeoTIFF acquisition tags
are retained when available.

The adapter returns:

- image tensor `[2, H, W]` in the explicit configured order, normally `[VV, VH]`;
- binary target tensor `[1, H, W]`;
- metadata containing scene ID/category, channel order, CRS, six affine coefficients,
  spatial bounds, acquisition timestamp, original shape, preprocessing bounds, and
  whether the original mask is empty.

VV and VH are named separately in every manifest record. The adapter accepts only
an explicit permutation of `VV` and `VH`, requires preprocessing to use that exact
same order, and records the order in every V1 checkpoint. It never discovers or
sorts polarization filenames heuristically.

## Integrity rules

The V1 adapter rejects:

- missing polarization or mask files;
- non-GeoTIFF inputs, malformed rasters, or rasters with other than one band;
- VV/VH/mask dimension, CRS, or affine-transform disagreement;
- non-finite and declared nodata SAR values under the default strict policy;
- non-finite mask pixels or mask values outside `0/1/255`;
- duplicate scene IDs and unknown scene categories;
- a mismatch between image channels, configured channel order, and normalization bounds.

An empty mask is valid for `lookalike` and `no_oil`; these categories remain negative
examples and are never converted to positive oil labels. An empty `oil` mask is
reported by validation and should be reviewed before training.

## SAR preprocessing

Input values must already be radiometrically calibrated Sigma0 in dB. The pipeline
does not treat the raster as RGB and does not perform implicit conversion from DN or
linear power.

The reproducible default method is `fixed_db`:

1. Validate every value is finite and not declared nodata.
2. Clip VV to `[-30, 0] dB` and VH to `[-35, -5] dB`.
3. For each channel, compute `(x - lower) / (upper - lower)`.
4. Clip the normalized result to `[0, 1]`.
5. Resize each channel with bilinear interpolation; resize the mask with nearest-neighbor.

These are visible starter bounds, not immutable scientific constants. Profile only
the training split, choose/version final bounds, and use the identical serialized
configuration for validation, test, and inference.

The optional `robust_percentile` method uses configurable per-scene percentiles
(default 1st and 99th), records each realized dB interval, clips to that interval,
and maps to `[0,1]`. It can help with unusual dynamic ranges but may remove useful
absolute backscatter differences between scenes, so it is not the default.

Invalid pixels fail by default. An explicit `invalid_value_policy="fill"` plus an
explicit `invalid_fill_db` is available for a documented nodata strategy; filling is
never silent.

## Evaluation contract

The report contains pixel-aggregated global Dice, IoU, precision, and recall, plus:

- oil scenes: pixel-aggregated Dice, IoU, precision, recall, and sample count;
- lookalike/no-oil scenes: sample count, false-positive scene rate, mean predicted
  oil fraction, maximum predicted oil fraction, and percentage with predicted oil
  fraction greater than a configurable threshold.

`false_positive_scene_rate` is the fraction of negative scenes with at least one
predicted positive pixel. The separately reported exceedance percentage uses
strictly `predicted_oil_fraction > oil_fraction_threshold`. No generic accuracy is
reported.

## Checkpoint contract and V0 compatibility

New checkpoints retain legacy top-level `model`, `image_size`, `epoch`, and
`val_metrics` entries and add versioned metadata:

- model architecture and model version;
- input channel count and ordered channel names;
- full preprocessing configuration;
- training dataset/version;
- epoch and validation metrics;
- UTC creation timestamp.

The loader also accepts the old wrapped V0 checkpoint format and raw SmallUNet state
dictionaries. For a metadata-free V0 checkpoint it infers one input channel and
network width from tensor shapes, then applies the legacy grayscale preprocessing.

## Architecture assessment

`SmallUNet` should remain the mandatory V1 smoke-test baseline. It is easy to debug,
stable on a T4, fast at inference, and now supports two channels. It is probably not
the best final detector for diverse official Sentinel-1 scenes because its shallow,
unpretrained encoder has limited multi-scale context for diffuse slick boundaries
and broad low-wind lookalikes.

Recommended next candidate: a moderately sized U-Net with a ResNet-34-class encoder,
with its first convolution explicitly adapted to two SAR channels. It offers the best
hackathon balance of implementation maturity, training stability, T4 memory use,
inference speed, and likely accuracy. Keep preprocessing and splits identical so its
gain over `SmallUNet` is measurable.

Other options:

- Attention U-Net: modest complexity and potentially better boundary focus, but less
  certain benefit than a stronger encoder.
- DeepLabV3+: strong multi-scale context and mature implementations, but usually
  heavier and somewhat slower for the same experiment budget.
- SegFormer: strong global context and accuracy potential, but more integration and
  tuning risk; pretrained RGB weights also need a deliberate two-channel strategy.

Do not change architecture before `SmallUNet` establishes a reproducible VV/VH
baseline and false-positive profile.

## Work required before GPU training

1. Acquire a manageable, licensed official Sentinel-1 subset; do not start with the
   full 40+ GB collection.
2. Confirm the rasters are calibrated Sigma0 dB rather than DN, amplitude, or linear
   Sigma0. Record the upstream calibration/terrain-correction workflow.
3. Create versioned train, validation, and test manifests split by source scene/event,
   not random tiles. Prevent neighboring tiles or repeat acquisitions from leaking
   across splits.
4. Review mask provenance, label convention, coastline/land handling, nodata policy,
   and empty oil-scene masks.
5. Profile only the training split and approve VV/VH dB clipping bounds.
6. Check category balance and include sufficient hard lookalikes and clean no-oil scenes.
7. Run manifest validation and visually inspect aligned VV, VH, and masks.
8. Run a CPU/Colab data-loader forward smoke test, then a 1-3 epoch T4 smoke run.
9. Select the pixel threshold and negative-scene oil-fraction threshold on validation;
   keep the test set untouched.
10. Train/evaluate `SmallUNet`, then compare one stronger encoder under the same split,
    preprocessing, loss, seeds, and reporting contract.

## Suggested Colab workflow

```bash
!git clone <YOUR_REPOSITORY_URL> /content/samudranetra
%cd /content/samudranetra
!git switch oilseg-v1-prep
!pip install -q -r requirements.txt

# Mount or copy a small versioned subset and its explicit manifests first.
!python -m ml.src.oiltrace_ml.validate \
  --manifest /content/oilseg_v1/manifests/train.json \
  --channel-order VV VH \
  --preprocessing-method fixed_db \
  --db-min -30 -35 \
  --db-max 0 -5

# Only after validation: T4 smoke train. This creates a new V1 artifact.
!python -m ml.src.oiltrace_ml.train \
  --manifest /content/oilseg_v1/manifests/train.json \
  --val-manifest /content/oilseg_v1/manifests/validation.json \
  --dataset-version sentinel1-official-subset-v1 \
  --model-version oilseg-v1-smallunet-smoke \
  --input-channels 2 \
  --channel-order VV VH \
  --preprocessing-method fixed_db \
  --db-min -30 -35 \
  --db-max 0 -5 \
  --epochs 3 \
  --batch-size 8 \
  --image-size 256 \
  --out /content/checkpoints/samudranetra_oilseg_v1_smoke.pt

!python -m ml.src.oiltrace_ml.evaluate \
  --checkpoint /content/checkpoints/samudranetra_oilseg_v1_smoke.pt \
  --manifest /content/oilseg_v1/manifests/validation.json \
  --threshold 0.5 \
  --oil-fraction-threshold 0.01 \
  --out-json /content/checkpoints/oilseg_v1_validation.json

!python -m ml.src.oiltrace_ml.infer \
  --checkpoint /content/checkpoints/samudranetra_oilseg_v1_smoke.pt \
  --image /content/oilseg_v1/example_VV.tif \
  --vh-image /content/oilseg_v1/example_VH.tif \
  --out /content/predicted_oil_mask.png \
  --prob-out /content/predicted_oil_probability.png
```
