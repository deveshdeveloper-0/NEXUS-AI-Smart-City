from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import PROJECT_ROOT
from app.agents.coordinator import ExecutionInProgressError, IntelligenceCoordinator
from app.agents.schemas import (
    AgentRunRequest,
    AgentDefinition,
    AgentStatusResponse,
    CityIndicators,
    IntelligenceReport,
)
from app.services.city_engine import get_dashboard, analyze_city
from app.services.live_data import LiveDataService
from app.services.live_data.schemas import (
    LiveCity,
    LiveMetricResponse,
    LiveOverview,
    LiveStatusResponse,
    RouteRequest,
    RouteTrafficResponse,
    WeatherResponse,
)

ROOT = PROJECT_ROOT
app = FastAPI(title="NEXUS AI Smart City", version="0.1.0")
coordinator = IntelligenceCoordinator()
live_data = LiveDataService()

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


@app.get("/api/agents", response_model=list[AgentDefinition])
def list_agents():
    return coordinator.definitions()


@app.get("/api/agents/status", response_model=AgentStatusResponse)
def agent_status():
    return AgentStatusResponse(
        execution_active=coordinator.execution_active,
        agents=coordinator.statuses(),
    )


@app.post("/api/agents/run", response_model=IntelligenceReport)
async def run_agents(request: AgentRunRequest | None = None):
    if request and request.indicators:
        indicators = request.indicators
        data_source = "POST /api/agents/run request (user-provided indicators)"
        data_mode = "user_provided"
    else:
        dashboard_data = get_dashboard()
        indicators = CityIndicators(
            traffic_index=dashboard_data["traffic_index"],
            air_quality_index=dashboard_data["air_quality_index"],
            energy_load_percent=dashboard_data["energy_load_percent"],
        )
        data_source = "app.services.city_engine.DEMO_CITY"
        data_mode = dashboard_data["data_mode"]
    try:
        return await coordinator.run(
            indicators,
            data_source=data_source,
            data_mode=data_mode,
        )
    except ExecutionInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@app.get("/api/agents/report", response_model=IntelligenceReport)
def agent_report():
    report = coordinator.latest_report()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No agent report is available. Run POST /api/agents/run first.",
        )
    return report


@app.get("/api/live/cities", response_model=list[LiveCity])
def live_cities():
    return live_data.cities()


@app.get("/api/live/status", response_model=LiveStatusResponse)
def live_status():
    return live_data.status()


@app.get("/api/live/{city_slug}/overview", response_model=LiveOverview)
async def live_city_overview(city_slug: str):
    city = live_data.resolve_city(city_slug)
    if city is None:
        raise HTTPException(status_code=404, detail="Unsupported city slug.")
    return await live_data.get_overview(city)


@app.get("/api/live/{city_slug}/aqi", response_model=LiveMetricResponse)
async def live_city_aqi(city_slug: str):
    city = live_data.resolve_city(city_slug)
    if city is None:
        raise HTTPException(status_code=404, detail="Unsupported city slug.")
    return await live_data.get_aqi(city)


@app.get("/api/live/{city_slug}/weather", response_model=WeatherResponse)
async def live_city_weather(city_slug: str):
    city = live_data.resolve_city(city_slug)
    if city is None:
        raise HTTPException(status_code=404, detail="Unsupported city slug.")
    return await live_data.get_weather(city)


@app.post("/api/live/traffic/route", response_model=RouteTrafficResponse)
async def live_traffic_route(request: RouteRequest):
    return await live_data.get_traffic_route(request)


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
