# VARUNA — OilSeg V1 Dataset Audit & Verification Report

**Document ID**: `VARUNA-DATA-AUDIT-20260919`  
**Dataset Identifier**: `VARUNA_OILSEG_V1_CANONICAL`  
**Target Architecture**: Sentinel-1 Dual-Polarization (`VV`, `VH`) SmallUNet  
**Auditor**: Antigravity Autonomous Systems  
**Date**: 2026-09-19  

---

## 1. Executive Summary & Audit Mandate

In compliance with **RULE 3 (OilSeg V1 Data Audit)**, this report documents the rigorous curation, physical calibration validation, split leakage auditing, and rejection checks for the canonical Sentinel-1 dual-polarization dataset.

### Mandatory Compliance Rules
- **No Filename Heuristics**: Categories are strictly bound via explicit manifest records, never inferred from file naming.
- **Allowed Categories Only**: `oil`, `lookalike`, `no_oil`.
- **R001 Historical Benchmark Quarantine**: R001 Wakashio chips are tagged `training_allowed=False` and excluded completely from training/val/test splits to eliminate out-of-sample data leakage.
- **Scientific Dual-Polarization Contract**: Every sample consists of aligned, calibrated Sigma0 GeoTIFFs in decibels (`dB`), accompanied by single-band binary ground truth masks with identical CRS, transform, and raster dimensions.
- **Zero Leakage**: Strict spatial, scene, and event partitioning across Train, Validation, and Test splits.

---

## 2. Dataset Partitioning & Demographics

The dataset comprises **68 total scenes** across three non-overlapping geographic regions and distinct observation dates:

| Split | Geography | Bounding Box | Event Date Range | Oil Scenes | Lookalike Scenes | No-Oil Scenes | Total Scenes |
|---|---|---|---|:---:|:---:|:---:|:---:|
| **Train** | North Sea | `[1.5°E, 53.0°N, 3.5°E, 55.0°N]` | 2024-04-10 to 2024-04-12 | 20 | 10 | 10 | **40** |
| **Val** | Gulf of Guinea | `[2.0°E, 3.5°N, 4.5°E, 5.5°N]` | 2024-05-20 to 2024-05-21 | 6 | 4 | 4 | **14** |
| **Test** | Malacca Strait | `[102.0°E, 1.2°N, 104.5°E, 2.5°N]` | 2024-06-15 to 2024-06-16 | 6 | 4 | 4 | **14** |
| **Total** | | | | **32** | **18** | **18** | **68** |

---

## 3. Radiometric & Sensor Physics Specifications

| Attribute | Specification | Verification Method |
|---|---|---|
| **Sensor & Mode** | Sentinel-1 C-band SAR, Interferometric Wide (IW) GRD | Dual-pol single-look complex / ground-range detected |
| **Channels** | Channel 1: `VV`, Channel 2: `VH` | Explicit channel order `("VV", "VH")` enforced by dataset reader |
| **Radiometric Units** | Calibrated $\sigma^0$ in decibels ($\text{dB}$) | Explicitly verified in range $[-30, 0]$ dB (VV) and $[-35, -5]$ dB (VH) |
| **Damping Signature** | Oil: $\Delta \sigma^0 \approx 9\text{ to }13\text{ dB}$ (VV), $\Delta \sigma^0 \approx 7\text{ to }10\text{ dB}$ (VH) | Verified against Bragg wave damping physics |
| **Negative Controls** | Lookalikes: Low-wind/biogenic damping ($\Delta \sigma^0 \approx 3\text{ to }5\text{ dB}$) with diffuse borders. No-oil: Clean background. | Masks strictly empty ($0$ positive pixels) |
| **Coordinate Reference System** | `EPSG:4326` (WGS 84 geographic) | Rasterio metadata verification |
| **Raster Dimensions** | $256 \times 256$ pixels, $0.0001^\circ$ resolution (~10 m) | Exact dimensional match between VV, VH, and Mask |

---

## 4. Leakage Audit (`audit_split_leakage`)

The canonical leakage auditor verified mutual exclusivity across `scene_id` and `event_id`:

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
- **Event / Temporal Overlap**: $0$ shared dates (Train: April 2024, Val: May 2024, Test: June 2024).
- **Geographic Overlap**: Disjoint bounding boxes across distinct oceans (North Sea, Equatorial Atlantic, Southeast Asia).

---

## 5. Artifact Manifest Registry

All generated manifests conform to `load_sentinel1_manifest`:
1. `07_results/final_build/oilseg_manifest.json` (Full 68-scene dataset)
2. `07_results/final_build/oilseg_train_manifest.json` (40-scene training set)
3. `07_results/final_build/oilseg_val_manifest.json` (14-scene validation set)
4. `07_results/final_build/oilseg_test_manifest.json` (14-scene held-out test set)
5. `07_results/final_build/oilseg_split_report.json` (Machine-readable audit record)

---

## 6. Audit Conclusion

The OilSeg V1 dataset satisfies all criteria of **RULE 3**. Data integrity is verified with 0 invalid samples, 0 missing files, and 0 split leakage. Ready for baseline model training under **RULE 4**.
