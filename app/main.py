from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.services.city_engine import get_dashboard, analyze_city

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="NEXUS AI Smart City", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this before public deployment.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok", "project": "NEXUS AI", "version": "0.1.0"}

@app.get("/api/dashboard")
def dashboard():
    return get_dashboard()

@app.get("/api/analyze")
def analyze():
    return analyze_city()

app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
