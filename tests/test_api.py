from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_dashboard_marks_demo_data():
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json()["data_mode"] == "synthetic_demo"
    assert response.json()["data_type"] == "DEMO_DATA"

def test_analysis_has_agents_and_limitations():
    response = client.get("/api/analyze")
    assert response.status_code == 200
    body = response.json()
    assert len(body["agents"]) >= 2
    assert body["limitations"]
