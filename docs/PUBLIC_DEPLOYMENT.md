# SAMUDRANETRA — PUBLIC STAGING DEPLOYMENT MANUAL

## 1. Architecture Topology

```
                  PUBLIC USER BROWSER
                          │
                          ▼
              VERCEL FRONTEND HOSTING
          https://samudranetra.vercel.app
                          │
                          │ HTTPS / CORS REST API
                          ▼
             PRODUCTION FASTAPI BACKEND
            https://api.samudranetra.org
                          │
            ┌─────────────┼─────────────┐
            │             │             │
       SAR ENGINE   OPENDRIFT ENGINE   AIS ENGINE
            │             │             │
            └─────────────┼─────────────┘
                          ▼
            CANONICAL R001 ARTIFACT STORE
```

## 2. Environment Configurations

### Frontend (Vercel)
- `SAMUDRANETRA_API_BASE_URL`: `https://api.samudranetra.org` (or public FastAPI domain)
- Framework Preset: `Other` / Static HTML
- Root Directory: `ops_console`

### Backend (Production FastAPI Service)
- `DEBUG`: `False`
- `ALLOWED_ORIGINS`: `https://samudranetra.vercel.app,http://localhost:8080,http://localhost:8000`
- `PYTHONPATH`: `.`
- `PORT`: `8000`

## 3. Production Health Endpoints
- `GET /health`: System health status (`STATUS: OK`)
- `GET /ready`: Readiness check (`STATUS: READY`)
- `GET /version`: System version (`0.9.0-rc1`) and build commit tag (`SAMUDRANETRA-LIVE-CORE-1.0`)

## 4. Hackathon Local Backup Failsafe Procedure
If venue internet connectivity fails during demo, switch seamlessly to Local Failsafe Mode:
1. Run local dev server: `.\scripts\start-dev.ps1`
2. Open local workstation: `http://localhost:8080`
3. Backend responds on `http://localhost:8000/api` with zero cloud dependency.
