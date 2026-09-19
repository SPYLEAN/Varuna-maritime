# VARUNA — OilSeg V1 Dataset Audit & Verification Report

**Document ID**: `VARUNA-DATA-AUDIT-20260919`  
**Dataset Identifier**: `VARUNA_OILSEG_V1_SYNTHETIC_BENCHMARK`  
**Target Architecture**: Sentinel-1-like Dual-Polarization (`VV`, `VH`) SmallUNet  
**Data Mode**: `SYNTHETIC`  
**Sensor Simulation**: `SENTINEL1_LIKE_DUAL_POL`  
**Auditor**: Antigravity Autonomous Systems  
**Date**: 2026-09-19  
**Status**: `SYNTHETIC_BENCHMARK_VERIFIED` | `REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED`

---

## 1. Executive Summary & Truthful Provenance Mandate

In strict compliance with **Scientific Truthfulness and Dataset Audit Standards**:
- **Synthetic Benchmark Provenance**: The 68-scene dataset is **synthetically generated** by physical backscatter simulation (`generate_sar_scene()`). These are **not genuine satellite acquisitions** from ESA or Copernicus, and they are not real historical discharge events.
- **Data Mode & Simulation Tagging**: Every record in the dataset is explicitly tagged:
  ```json
  "data_mode": "SYNTHETIC",
  "sensor_simulation": "SENTINEL1_LIKE_DUAL_POL",
  "source_dataset": "VARUNA_OILSEG_V1_SYNTHETIC_BENCHMARK",
  "license": "MIT (Synthetic Benchmark Generator, SPYLEAN/Varuna-maritime)",
  "real_world_validation": "REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED"
  ```
- **License Integrity**: Misleading Copernicus licensing attribution has been removed from all synthetic arrays. The code and generated arrays carry the repository MIT license.
- **Allowed Categories**: `oil`, `lookalike`, `no_oil`.
- **R001 Historical Benchmark Quarantine**: R001 Wakashio chips are tagged `training_allowed=False` and excluded completely from training/val/test splits to eliminate out-of-sample data leakage.
- **Synthetic Benchmark Purpose**: Demonstrates dual-channel architectural convergence, gradient dynamics, spatial tiling, and metric evaluation under controlled physical damping signatures.
- **Operational Reality**: **`REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED`**. High synthetic IoU scores do not imply real-world operational readiness without in-situ satellite validation.

---

## 2. Dataset Demographics & Synthetic Partitions

The dataset comprises **68 total synthetic scenes** across three non-overlapping geographic bounding boxes and simulated observation dates:

| Split | Geography | Bounding Box | Simulated Date Range | Oil Scenes | Lookalike Scenes | No-Oil Scenes | Total Scenes |
|---|---|---|---|:---:|:---:|:---:|:---:|
| **Train** | North Sea (Simulated) | `[1.5°E, 53.0°N, 3.5°E, 55.0°N]` | 2024-04-10 to 2024-04-12 | 20 | 10 | 10 | **40** |
| **Val** | Gulf of Guinea (Simulated) | `[2.0°E, 3.5°N, 4.5°E, 5.5°N]` | 2024-05-20 to 2024-05-21 | 6 | 4 | 4 | **14** |
| **Test** | Malacca Strait (Simulated) | `[102.0°E, 1.2°N, 104.5°E, 2.5°N]` | 2024-06-15 to 2024-06-16 | 6 | 4 | 4 | **14** |
| **Total** | | | | **32** | **18** | **18** | **68** |

---

## 3. Simulated Physics & Dual-Polarization Parameters

| Attribute | Synthetic Specification | Simulation Logic |
|---|---|---|
| **Sensor Simulation** | `SENTINEL1_LIKE_DUAL_POL` | C-band SAR geometry with dual-polarization channels |
| **Channels** | Channel 1: `VV`, Channel 2: `VH` | Explicit channel order `("VV", "VH")` enforced by dataset reader |
| **Radiometric Units** | Simulated $\sigma^0$ in decibels ($\text{dB}$) | Bounds: $[-30, 0]$ dB (VV) and $[-35, -5]$ dB (VH) |
| **Simulated Damping** | Oil: $\Delta \sigma^0 \approx 9\text{ to }13\text{ dB}$ (VV), $\Delta \sigma^0 \approx 7\text{ to }10\text{ dB}$ (VH) | Simulates Bragg wave damping physics on short gravity-capillary waves |
| **Negative Controls** | Lookalikes: Low-wind/biogenic damping ($\Delta \sigma^0 \approx 3\text{ to }5\text{ dB}$) with diffuse borders. No-oil: Clean background. | Masks strictly empty ($0$ positive pixels) |
| **Coordinate Reference System** | `EPSG:4326` (WGS 84 geographic) | Standard GeoTIFF geotransform header |
| **Raster Dimensions** | $256 \times 256$ pixels, $0.0001^\circ$ resolution (~10 m) | Exact dimensional match between VV, VH, and Mask |

---

## 4. Leakage Audit (`audit_split_leakage`)

The canonical leakage auditor verified mutual exclusivity across `scene_id` and simulated `event_id`:

```json
{
  "passed": true,
  "scene_id_leakage": {
    "train_val": [],
    "train_test": [],
    "val_test": []
  },
  "event_leakage": {
    "train_val": [],
    "train_test": [],
    "val_test": []
  }
}
```

- **Scene ID Overlap**: $0$ overlapping scenes.
- **Event / Temporal Overlap**: $0$ shared dates across splits.
- **Geographic Overlap**: Disjoint bounding boxes.

---

## 5. Artifact Manifest Registry

All generated manifests conform to `load_sentinel1_manifest`:
1. `07_results/final_build/oilseg_manifest.json` (Full 68-scene synthetic dataset)
2. `07_results/final_build/oilseg_train_manifest.json` (40-scene synthetic training set)
3. `07_results/final_build/oilseg_val_manifest.json` (14-scene synthetic validation set)
4. `07_results/final_build/oilseg_test_manifest.json` (14-scene synthetic held-out test set)
5. `07_results/final_build/oilseg_split_report.json` (Machine-readable audit record)

---

## 6. Audit Conclusion

The dataset provenance is formally classified as **`VARUNA_OILSEG_V1_SYNTHETIC_BENCHMARK`**. All records truthfully declare `data_mode="SYNTHETIC"` and `real_world_validation="REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED"`. Zero data leakage across splits.
