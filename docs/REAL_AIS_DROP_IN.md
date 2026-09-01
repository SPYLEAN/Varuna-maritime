# SAMUDRANETRA — Real Historical AIS Drop-In Ingestion Guide

**Version**: `0.9.0-rc1`

This document specifies the drop-in interface for replacing synthetic demonstration data with real historical AIS vessel traffic.

---

## Required CSV Input Schema

Place real AIS CSV files in `07_results/ais/raw_historical_ais.csv` conforming to:

| Column Name | Type | Format / Unit | Description |
|---|---|---|---|
| `mmsi` | Integer | 9-digit ID | Maritime Mobile Service Identity |
| `vessel_name` | String | UTF-8 Text | Registered vessel name |
| `timestamp` | String | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`) | AIS broadcast timestamp |
| `latitude` | Float | Decimal degrees (-90 to +90) | Vessel latitude |
| `longitude` | Float | Decimal degrees (-180 to +180) | Vessel longitude |
| `sog_knots` | Float | Knots (0–50) | Speed over ground |
| `cog_degrees` | Float | Degrees (0–360) | Course over ground |
| `imo_number` | Optional Int | 7-digit ID | IMO ship identification number |
| `ship_type` | String | Cargo / Tanker / Fishing / Passenger | Vessel category |

---

## Ingestion Command

Execute the clean-room AIS ingestion pipeline:

```powershell
$env:PYTHONPATH="."
python backend/app/services/ais_ingestion.py --input "07_results/ais/raw_historical_ais.csv" --data-mode REAL_HISTORICAL
```

---

## Data Provenance Guard Verification

Upon ingestion of real AIS data:
1. `data_mode` transitions automatically from `SYNTHETIC_DEMO` to `REAL_HISTORICAL`.
2. `historical_attribution_valid` updates from `False` to `True`.
3. Badges on the Ops Console automatically update to reflect verified historical vessel traffic.
