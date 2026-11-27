import asyncio

import pytest
from fastapi.testclient import TestClient

from app.agents.base_agent import BaseAgent
from app.agents.coordinator import ExecutionInProgressError, IntelligenceCoordinator
from app.agents.energy_agent import EnergyAgent
from app.agents.pollution_agent import PollutionAgent
from app.agents.prediction_agent import PredictionAgent
from app.agents.research_agent import ResearchAgent
from app.agents.schemas import AgentState, CityIndicators, Severity
from app.agents.traffic_agent import TrafficAgent
from app.main import app
import app.main as main_module

client = TestClient(app)
INDICATORS = CityIndicators(
    traffic_index=78,
    air_quality_index=142,
    energy_load_percent=71,
)


@pytest.mark.parametrize(
    ("agent_type", "expected_severity", "observation_key"),
    [
        (TrafficAgent, Severity.ALERT, "traffic_index"),
        (PollutionAgent, Severity.ALERT, "air_quality_index"),
        (EnergyAgent, Severity.WATCH, "energy_load_percent"),
    ],
)
def test_rule_agents_return_explainable_results(agent_type, expected_severity, observation_key):
    result = asyncio.run(agent_type().run(INDICATORS))

    assert result.status == AgentState.COMPLETED
    assert result.severity == expected_severity
    assert result.observed_data[observation_key] is not None
    assert result.findings
    assert result.recommendations
    assert result.metadata["method"] == "transparent rule-based analysis"


def test_traffic_threshold_boundaries():
    async def analyze(value):
        return await TrafficAgent().run(INDICATORS.model_copy(update={"traffic_index": value}))

    assert asyncio.run(analyze(39)).severity == Severity.NORMAL
    assert asyncio.run(analyze(40)).severity == Severity.WATCH
    assert asyncio.run(analyze(70)).severity == Severity.ALERT


def test_pollution_classifies_aqi_categories():
    async def analyze(value):
        return await PollutionAgent().run(INDICATORS.model_copy(update={"air_quality_index": value}))

    assert "good" in asyncio.run(analyze(50)).findings[0]
    assert "moderate" in asyncio.run(analyze(100)).findings[0]
    assert "unhealthy for sensitive groups" in asyncio.run(analyze(101)).findings[0]
    assert "hazardous" in asyncio.run(analyze(301)).findings[0]


def test_energy_load_threshold_boundaries():
    async def analyze(value):
        return await EnergyAgent().run(INDICATORS.model_copy(update={"energy_load_percent": value}))

    assert asyncio.run(analyze(49)).severity == Severity.NORMAL
    assert asyncio.run(analyze(70)).severity == Severity.WATCH
    assert asyncio.run(analyze(85)).severity == Severity.ALERT


def test_prediction_agent_does_not_fabricate_results():
    result = asyncio.run(PredictionAgent().run(INDICATORS))

    assert result.status == AgentState.UNAVAILABLE
    assert result.observed_data == {}
    assert result.metadata["prediction_horizon"] is None
    assert result.metadata["model_status"] == "unavailable"
    assert result.warnings


def test_research_agent_uses_agent_outputs_and_labels_inference():
    upstream = [
        asyncio.run(TrafficAgent().run(INDICATORS)),
        asyncio.run(PollutionAgent().run(INDICATORS)),
    ]
    result = asyncio.run(ResearchAgent().run(INDICATORS, prior_results=upstream))

    assert any("co-occur" in finding for finding in result.findings)
    assert result.metadata["source_agent_count"] == 2
    assert any("causal" in assumption for assumption in result.assumptions)
    assert result.metadata["conflict_count"] == 0


def test_coordinator_runs_all_agents_and_builds_combined_report():
    coordinator = IntelligenceCoordinator()
    report = asyncio.run(
        coordinator.run(
            INDICATORS,
            data_source="test input",
            data_mode="user_provided",
        )
    )

    assert report.status.value == "partial"
    assert {result.agent_id for result in report.results} == {
        "traffic",
        "pollution",
        "energy",
        "prediction",
        "research",
    }
    assert report.input_data == INDICATORS
    assert report.data_source == "test input"
    assert report.started_at <= report.completed_at
    assert report.duration_ms >= 0
    assert report.limitations
    assert report.results[-1].agent_id == "research"
    assert report.results[-1].metadata["source_agent_count"] == 4
    assert coordinator.latest_report() == report
    assert all(status.status != AgentState.RUNNING for status in coordinator.statuses())


class FailingTrafficAgent(BaseAgent):
    agent_id = "traffic"
    name = "Traffic Intelligence Agent"
    description = "Raises an exception for coordinator error-isolation testing."

    async def run(self, indicators, *, prior_results=None):
        raise RuntimeError("example internal failure")


def test_coordinator_keeps_partial_results_when_agent_fails(caplog):
    coordinator = IntelligenceCoordinator()
    coordinator.agents["traffic"] = FailingTrafficAgent()

    report = asyncio.run(
        coordinator.run(INDICATORS, data_source="test", data_mode="test")
    )

    failed = next(result for result in report.results if result.agent_id == "traffic")
    assert failed.status == AgentState.FAILED
    assert failed.error == "Agent execution failed; consult server logs."
    assert "example internal failure" not in failed.error
    assert any(result.status == AgentState.COMPLETED for result in report.results)
    assert report.status.value == "partial"
    assert "Agent traffic execution failed" in caplog.text


def test_coordinator_marks_report_failed_when_no_independent_agent_succeeds():
    class FailingAgent(BaseAgent):
        def __init__(self, agent_id, name):
            self.agent_id = agent_id
            self.name = name
            self.description = "Fails to test the all-agent failure report state."

        async def run(self, indicators, *, prior_results=None):
            raise RuntimeError("agent failure")

    coordinator = IntelligenceCoordinator()
    for agent_id in ("traffic", "pollution", "energy"):
        coordinator.agents[agent_id] = FailingAgent(
            agent_id,
            coordinator.agents[agent_id].name,
        )

    report = asyncio.run(
        coordinator.run(INDICATORS, data_source="test", data_mode="test")
    )

    assert report.status.value == "failed"


class SlowTrafficAgent(BaseAgent):
    agent_id = "traffic"
    name = "Traffic Intelligence Agent"
    description = "Delays to verify execution timeouts and duplicate-run rejection."

    def __init__(self, delay=0.1):
        self.delay = delay
        self.started = None

    async def run(self, indicators, *, prior_results=None):
        self.started.set()
        await asyncio.sleep(self.delay)
        return await TrafficAgent().run(indicators)


def test_coordinator_times_out_slow_agent():
    async def scenario():
        coordinator = IntelligenceCoordinator(timeout_seconds=0.01)
        slow = SlowTrafficAgent()
        slow.started = asyncio.Event()
        coordinator.agents["traffic"] = slow
        report = await coordinator.run(INDICATORS, data_source="test", data_mode="test")
        return next(result for result in report.results if result.agent_id == "traffic")

    result = asyncio.run(scenario())
    assert result.status == AgentState.FAILED
    assert "timed out" in result.error


def test_coordinator_rejects_duplicate_concurrent_run():
    async def scenario():
        coordinator = IntelligenceCoordinator()
        slow = SlowTrafficAgent(delay=0.05)
        slow.started = asyncio.Event()
        coordinator.agents["traffic"] = slow
        first_run = asyncio.create_task(
            coordinator.run(INDICATORS, data_source="test", data_mode="test")
        )
        await slow.started.wait()
        with pytest.raises(ExecutionInProgressError):
            await coordinator.run(INDICATORS, data_source="test", data_mode="test")
        await first_run

    asyncio.run(scenario())


def test_agent_api_endpoints_and_combined_report():
    definitions = client.get("/api/agents")
    assert definitions.status_code == 200
    assert {agent["agent_id"] for agent in definitions.json()} == {
        "traffic",
        "pollution",
        "energy",
        "prediction",
        "research",
    }

    status_response = client.get("/api/agents/status")
    assert status_response.status_code == 200
    assert len(status_response.json()["agents"]) == 5

    run_response = client.post("/api/agents/run", json={"indicators": INDICATORS.model_dump()})
    assert run_response.status_code == 200
    report = run_response.json()
    assert report["data_mode"] == "user_provided"
    assert len(report["results"]) == 5

    latest = client.get("/api/agents/report")
    assert latest.status_code == 200
    assert latest.json()["report_id"] == report["report_id"]


def test_agent_report_is_not_found_before_first_run(monkeypatch):
    monkeypatch.setattr(main_module, "coordinator", IntelligenceCoordinator())

    response = client.get("/api/agents/report")

    assert response.status_code == 404
    assert "Run POST /api/agents/run first" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"indicators": {"traffic_index": 101, "air_quality_index": 50, "energy_load_percent": 20}},
        {"indicators": {"traffic_index": 10, "air_quality_index": 50}},
        {"indicators": {"traffic_index": 10, "air_quality_index": 50, "energy_load_percent": 20, "extra": 1}},
        {"unexpected": True},
    ],
)
def test_agent_run_rejects_invalid_requests(payload):
    assert client.post("/api/agents/run", json=payload).status_code == 422


def test_default_run_uses_real_dashboard_data_and_prediction_is_unavailable():
    report = client.post("/api/agents/run").json()

    assert report["data_source"] == "app.services.city_engine.DEMO_CITY"
    assert report["data_mode"] == "synthetic_demo"
    prediction = next(result for result in report["results"] if result["agent_id"] == "prediction")
    assert prediction["status"] == "unavailable"
    assert prediction["metadata"]["model_names"] is None


def test_existing_api_compatibility_and_frontend_integration():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/dashboard").json()["data_mode"] == "synthetic_demo"
    assert client.get("/api/analyze").json()["agents"]
    html = client.get("/").text
    javascript = client.get("/app.js").text
    assert 'id="run-agents"' in html
    assert 'id="agent-status"' in html
    assert 'id="combined-report"' in html
    assert '"/api/agents/run"' in javascript
    assert '"/api/agents/status"' in javascript
    assert '"/api/agents/report"' in javascript
