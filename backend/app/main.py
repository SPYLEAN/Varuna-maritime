from fastapi import FastAPI
app = FastAPI(title="OilTrace AI", version="0.1.0")

@app.get("/health")
def health():
    return {"status":"ok", "service":"oiltrace-backend"}
