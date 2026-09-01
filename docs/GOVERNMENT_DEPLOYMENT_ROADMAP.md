# SAMUDRANETRA — Government Operational Deployment Roadmap

**Version**: `0.9.0-rc1`

---

## Current Status vs Production Roadmap

```
┌────────────────────────────────────────────────────────┐
│                   IMPLEMENTED NOW                      │
├────────────────────────────────────────────────────────┤
│ • Sentinel-1 SAR dark-spot extraction & ML scoring     │
│ • OpenDrift backward ocean transport (ERA5/HYCOM/CMEMS)│
│ • Forward physical closure validation (Task009C)       │
│ • Post-freeze historical validation (Task009D)         │
│ • Explainable AIS evidence ranking engine & abstention │
│ • FastAPI Unified Investigation API                    │
│ • Desktop Ops Console Workstation (FUNCTIONAL_UI_V1)   │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                  PRODUCTION ROADMAP                    │
├────────────────────────────────────────────────────────┤
│ Phase 1: Real AIS Feed & Coast Guard API Integration   │
│ Phase 2: Multi-Satellite Ingestion (Sentinel-2, RADARSAT)│
│ Phase 3: Role-Based Access Control (RBAC) & Audit Logs │
│ Phase 4: Automated Incident Escalation & Legal Export  │
└────────────────────────────────────────────────────────┘
```

---

## Target Agency Integration

1. **Maritime Safety & Coast Guard Agencies**: Live SAR polling, automatic candidate alerting, vessel priority dispatch.
2. **Environmental Protection Authorities**: Pollution containment trajectory forecasting, coastal impact threat maps.
3. **Naval Command Centers**: Geospatial intelligence workstation integration, multi-vessel tracking, sovereign EEZ monitoring.
