# NEXUS AI – Smart City Digital Twin

**Hackathon prototype:** Autonomous Multi-Agent Intelligence for Predictive Smart City Digital Twins.

## Current prototype scope
- FastAPI backend with health, dashboard and analysis endpoints.
- Browser dashboard with city indicators and trend visualization.
- Three transparent rule-based analysis modules: traffic, air quality and energy.
- Synthetic demonstration data is clearly labelled.

## Important limitations
This is an initial prototype, not a live city digital twin. The values are synthetic. The analysis is rule-based, not a trained predictive model. It does not connect to IoT devices or control real infrastructure. Recommendations require human review.

## Requirements
- Python 3.10+
- pip

## Setup

### Windows PowerShell
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

API documentation: http://127.0.0.1:8000/docs

## API endpoints
- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/analyze`

## Tests
```powershell
pytest -q
```

## GitHub setup
Create an empty GitHub repository named `NEXUS-AI-Smart-City`, then:
```powershell
git init
git add .
git commit -m "Initial NEXUS AI smart city prototype"
git branch -M main
git remote add origin https://github.com/deveshdeveloper-0/NEXUS-AI-Smart-City.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username. Never commit `.env` or API keys.
