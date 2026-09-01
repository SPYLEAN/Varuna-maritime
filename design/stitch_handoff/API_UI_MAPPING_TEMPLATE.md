# SAMUDRANETRA — STITCH COMPONENT TO API BINDING TEMPLATE

| UI Component / Field | Target API Endpoint | Backend API JSON Field | Canonical Scientific Artifact | Fallback / Error State |
| :--- | :--- | :--- | :--- | :--- |
| **ML Oil-Like Score** | `GET /api/cases/{id}/sar` | `primary_ml_score` | `R001_CANDIDATE_CLASSIFIER_RESULTS.csv` | `0.5818` |
| **SAR Acquisition TS** | `GET /api/cases/{id}` | `observation_timestamp_utc` | `R001_S1B_VV_SIGMA0_DB.tif` | `2020-08-10T01:38:07.500Z` |
| **SAR Product ID** | `GET /api/cases/{id}` | `satellite_product_id` | Sentinel-1B Manifest | `S1B_IW_GRDH_1SDV_20200810...` |
| **Selected Candidate ID** | `GET /api/cases/{id}/sar` | `selected_candidate_id` | `R001_CANDIDATE_TRIAGE.json` | `C4053` |
| **Candidate Count** | `GET /api/cases/{id}/sar` | `candidate_count` | `R001_CANDIDATE_TRIAGE.json` | `8` |
| **Candidate Hierarchy** | `GET /api/cases/{id}/sar` | `candidate_count_description` | `R001_CANDIDATE_TRIAGE.json` | `8 physics-eligible source candidate hypotheses (from 45 triaged candidate groups)` |
| **Hindcast Particles** | `GET /api/cases/{id}/reconstruct` | `hindcast_particles` | `R001_HINDCAST_OPENDRIFT.json` | `500 particles` |
| **Source Region Envelope** | `GET /api/cases/{id}/reconstruct` | `source_envelope_geojson` | `R001_SOURCE_REGION.json` | Polygon Feature |
| **Forecast Horizon** | `GET /api/cases/{id}/forecast` | `horizon_metadata` | Extended NetCDF Forcing | `T0 → T+48h` |
| **Forcing Support** | `GET /api/cases/{id}/forecast` | `forcing_support.coverage_status` | Extended NetCDF Forcing | `FULL FORCING SUPPORT` |
| **Forcing End TS** | `GET /api/cases/{id}/forecast` | `forcing_support.datasets_metadata.era5_wind.coverage_end` | Extended NetCDF Forcing | `2020-08-12T03:00Z` |
| **Ranked Vessel Leads** | `GET /api/cases/{id}/vessels` | `vessel_leads` | `R001_AIS_CORRELATION.json` | List of 3 Ranked Vessels |
| **AIS Data Mode** | `GET /api/cases/{id}/vessels` | `ais_data_mode` | `R001_AIS_INPUT.csv` | `SYNTHETIC DEMONSTRATION` |
| **Review Briefing** | `GET /api/cases/{id}/review` | `briefing_matrix` | Integrated Case Engine | 11-Stage JSON Matrix |
| **Clean-Room Provenance** | `GET /api/cases/{id}/provenance` | `provenance_manifest` | `R001_PROVENANCE.json` | SHA256 Manifest |
