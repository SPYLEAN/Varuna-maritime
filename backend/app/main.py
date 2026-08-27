from fastapi import FastAPI
from .routers import analysis, cases, evidence, files

app = FastAPI(
    title="SAMUDRANETRA API",
    description="Maritime Pollution Intelligence System — Case Intake, Evidence & Analysis",
    version="0.1.0",
)

app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(analysis.router)
app.include_router(files.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "samudranetra-backend"}
