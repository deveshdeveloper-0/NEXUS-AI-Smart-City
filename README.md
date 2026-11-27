# NEXUS AI – Smart City Digital Twin

Hackathon prototype for transparent city monitoring and decision support. The multi-agent workflow is asynchronous and modular; its traffic, pollution, and energy findings use explicit rules over supplied indicators.

## Multi-Agent Architecture

`app/agents/` contains independent traffic, pollution, energy, prediction, and research agents plus a central coordinator. Pydantic schemas validate requests and structure each result. The coordinator runs the four independent agents concurrently, applies a per-agent timeout, records individual errors without discarding other results, and runs research synthesis after the other outputs arrive. It rejects a second simultaneous run with HTTP 409 and retains the latest report in process memory.

## Agent Responsibilities

- **Traffic Intelligence Agent:** classifies a supplied traffic index as low, moderate, or high congestion and gives explainable monitoring recommendations.
- **Pollution Intelligence Agent:** classifies an AQI value on the 0–500 scale and recommends monitoring appropriate to the category.
- **Energy Intelligence Agent:** classifies the energy-load percentage and suggests demand-management review.
- **Prediction Agent:** reports model metadata and predictions only when model artifacts and inference code are configured. This repository contains no Random Forest models or trained artifacts, so it currently returns `unavailable` and no prediction values or horizon.
- **Research Agent:** summarizes actual outputs from the other agents, notes indicator co-occurrence and conflicting measurements, and distinguishes observations from assumptions. It does not consult or fabricate external research or citations.
- **Central Coordinator Agent:** coordinates execution, tracks statuses and timestamps, isolates failures, and assembles the combined report.

The first three agents are transparent rule-based analyses, not machine-learning predictions. Recommendations are decision support only; the application does not operate city infrastructure.

## Execution Workflow

1. `POST /api/agents/run` validates optional indicator overrides. With no override, it reads the existing synthetic demo indicators from `app.services.city_engine`.
2. Traffic, pollution, energy, and prediction agents run independently and concurrently.
3. Research synthesizes their returned findings and observations; it does not infer causation from co-occurring measurements.
4. The coordinator returns a timestamped report with status, data source, input values, per-agent results, and limitations. `GET /api/agents/report` returns the latest successful run in the current process.

## Live Data Integrations

The Live City Data view is separate from the existing synthetic demo dashboard. Switching to live mode hides the demo measurements. Live values are shown only from validated provider responses; missing credentials, invalid responses, and unavailable feeds return `DATA_UNAVAILABLE`. Cached provider results may return as `STALE` with their original fetched timestamp and `is_live: false`.

- **CPCB / data.gov.in:** The official [Real-time AQI resource](https://data.gov.in/resource/real-time-air-quality-index-various-locations) was inspected. Its metadata identifies resource `3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69` and pollutant fields (`state`, `city`, `station`, `latitude`, `longitude`, `pollutant_id`, `pollutant_min`, `pollutant_max`, `pollutant_avg`). `DATA_GOV_API_KEY` is required; `DATA_GOV_RESOURCE_ID` can override the verified resource ID. Records are filtered by state and normalized city names. `pollutant_avg` is never treated as AQI. Station readings are kept separate and are not averaged into a city-wide value.
- **Weather:** The documented IMD reference lists current-weather and seven-day city forecast APIs, but this runtime could not verify an authorized IMD response or the exact city/station mapping for these cities. The app therefore does not invent an IMD endpoint credential or station ID. It uses Open-Meteo geocoding and forecast APIs as a fallback and marks these results `FORECAST_DATA` / model-based, not direct IMD station observations. The API response is validated before it is marked `LIVE`.
- **Google Maps Routes:** Route-level `TRAFFIC_AWARE` ETA is requested only when `GOOGLE_MAPS_API_KEY` is configured. The route response includes provider-returned distance, traffic-aware `duration`, and `staticDuration` when available. The dashboard labels `duration` as the estimated traffic-aware travel time and `staticDuration` as the non-traffic baseline. Missing credentials, invalid locations, permission/billing problems, quota limits, and network failures return an unavailable status with a sanitized explanation. A route is never represented as city-wide traffic.
- **Energy:** No authorized utility or smart-meter provider is configured, so live energy always returns `DATA_UNAVAILABLE`; no demo percentage is substituted.
- **ML:** No Random Forest model artifacts or ML engine are present in this repository. The live-data APIs do not invoke the demo agent workflow or feed synthetic measurements into an ML model.

All provider credentials are backend-only environment variables. `app.config` loads the project-root `.env` on startup without overriding variables already set by the process. `.env.example` contains blank placeholders; `.env` is ignored by Git and must never be committed.

### Live API Endpoints

- `GET /api/live/cities` — supported city slugs and names.
- `GET /api/live/status` — backend status and provider configuration/readiness. `READY` or `CONFIGURED` is not a claim that the provider returned live data.
- `GET /api/live/{city_slug}/overview` — combined AQI, weather, energy, and city-wide traffic availability.
- `GET /api/live/{city_slug}/aqi` — station-level CPCB observations when configured and valid.
- `GET /api/live/{city_slug}/weather` — current model-based weather plus up to seven forecast days.
- `POST /api/live/traffic/route` — route-level traffic-aware ETA:

  ```json
  {
    "city_slug": "varanasi",
    "origin": "Varanasi Junction",
    "destination": "Lal Bahadur Shastri International Airport"
  }
  ```

  The `city_slug` is optional. Do not send sensitive addresses unless appropriate; route inputs are not logged by the application.

Every live response includes a status, source attribution where data exists, fetched timestamp, live flag, and data classification (`OBSERVED_DATA` or `FORECAST_DATA`). The API never marks model weather as observed station data.

## Installation and Startup

Requirements: Python 3.10+ and pip.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Fill provider variables in .env only when authorized.
python -m uvicorn app.main:app --reload --env-file .env
```

The application also loads `.env` automatically when imported; `--env-file .env` is optional.

Open <http://127.0.0.1:8000>. Interactive API documentation is at <http://127.0.0.1:8000/docs>.

## API Endpoints

- `GET /api/health` — health check.
- `GET /api/dashboard` — existing city indicators and trend data.
- `GET /api/analyze` — existing rule-based analysis endpoint (preserved).
- `GET /api/agents` — agent definitions and methods.
- `GET /api/agents/status` — current execution status for each agent.
- `POST /api/agents/run` — execute all agents; optional validated input:

  ```json
  {
    "indicators": {
      "traffic_index": 78,
      "air_quality_index": 142,
      "energy_load_percent": 71
    }
  }
  ```

- `GET /api/agents/report` — latest report; returns 404 before the first run.
- Live-data API routes are listed above.

Example report shape (timestamps and report ID vary):

```json
{
  "status": "partial",
  "data_source": "app.services.city_engine.DEMO_CITY",
  "data_mode": "synthetic_demo",
  "summary": "Rule-based agents reported 2 alert-level and 1 watch-level finding(s). One or more agents returned incomplete or unavailable results.",
  "results": [
    {
      "agent_id": "prediction",
      "status": "unavailable",
      "findings": ["No trained prediction models or model artifacts are present in this project."],
      "metadata": {
        "model_status": "unavailable",
        "model_names": null,
        "prediction_horizon": null
      }
    }
  ],
  "limitations": ["Default indicators are synthetic demonstration values, not live city telemetry."]
}
```

The `results` array contains all five agent outputs; the abbreviated example above highlights the unavailable prediction status.

## Testing

```powershell
python -m pytest -q
```

## Known Limitations

- Default city measurements are synthetic demo data; no city, IoT, or live AQI feeds are connected.
- CPCB AQI requests require a configured data.gov.in API key; no live CPCB station records were verified in this environment.
- Open-Meteo weather is model-based forecast data, not an IMD observation. IMD city/station mapping and authorized API access remain unverified.
- Google Routes requires a configured key and enabled billing/API access; no live route response was verified.
- No live energy provider is configured.
- Traffic, pollution, and energy analysis is rule-based.
- No trained Random Forest models or prediction artifacts currently exist in this repository; predictions and horizons are therefore unavailable, not fabricated.
- Research synthesis only uses run-time agent outputs; it does not access external literature or provide citations.
- The latest report and statuses are held in process memory and reset on restart.
- The prototype is not a live digital twin and must not be used to control infrastructure. Recommendations require human review.
