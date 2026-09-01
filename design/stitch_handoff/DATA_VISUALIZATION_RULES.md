# SAMUDRANETRA — DATA VISUALIZATION & GIS MAP RULES

## 1. Map Canvas Dominance
- The GIS interactive map canvas MUST occupy **65% to 75%** of the main workstation viewport.
- Keyless basemap configuration MUST be preserved (`0` occurrences of "API KEY REQUIRED" overlays).

## 2. Layer Hierarchy & Styling

| Layer Type | Representation / Styling | Color / Code | Interactivity |
| :--- | :--- | :--- | :--- |
| **Sentinel-1 SAR Raster** | Calibrated VV / VH dB backscatter raster overlay | Grayscale / False-color | Pixel/coordinate probe on hover |
| **Dark Spot Candidates** | Polygon bounding boxes / contours | Cyan `#0EA5E9` (Selected `#2563EB`) | Click to select candidate |
| **Hindcast Particles** | Discrete particle points (500 particles) | Amber `#F59E0B` (Opacity `0.6`) | Filter by timestep ($T-24\text{h} \dots T-96\text{h}$) |
| **Source Envelope** | Bounding polygon convex hull | Amber Dash `#F59E0B` (Opacity `0.15`) | Hover for area statistics |
| **Forecast Particles** | Forward transport particles (250 particles) | Violet `#8B5CF6` (Opacity `0.7`) | Filter by horizon ($T+6\text{h} \dots T+48\text{h}$) |
| **Forecast Envelope** | Forward dispersion envelope | Violet Polygon `#8B5CF6` (Opacity `0.2`) | Hover for radius statistics |
| **AIS Vessel Tracks** | Polyline trajectories with directional arrows | Green `#10B981` / Red `#EF4444` | Click vessel to open lead card |

## 3. UI Badge Rules
- Cached benchmark data MUST display: `VALIDATED CACHED RESULT` (Green Badge).
- Live computed jobs MUST display: `LIVE COMPUTE` (Blue Badge).
- Synthetic AIS data MUST display: `SYNTHETIC DEMO AIS` (Amber Badge).
