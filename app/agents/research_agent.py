from datetime import datetime, timezone

from app.agents.base_agent import BaseAgent
from app.agents.schemas import AgentResult, AgentState, CityIndicators, Severity


class ResearchAgent(BaseAgent):
    agent_id = "research"
    name = "Research Agent"
    description = "Summarizes other agent results, observed patterns, and disagreements."
    method = "evidence synthesis from agent outputs; no external research or citations"

    async def run(
        self,
        indicators: CityIndicators,
        *,
        prior_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        del indicators
        results = prior_results or []
        traffic = next((r for r in results if r.agent_id == "traffic"), None)
        pollution = next((r for r in results if r.agent_id == "pollution"), None)
        findings: list[str] = []
        assumptions = [
            "This summary uses only the supplied indicators and completed agent outputs.",
            "Co-occurring indicators do not establish a causal relationship.",
            "No external research, citations, or live sources were consulted.",
        ]
        observed_data: dict[str, int | float | str | None] = {
            "analyzed_agent_count": len(results),
        }

        for result in results:
            observed_data[f"{result.agent_id}_status"] = result.status.value
            for key, value in result.observed_data.items():
                observed_data[key] = value

        traffic_value = (traffic.observed_data.get("traffic_index") if traffic else None)
        aqi_value = (pollution.observed_data.get("air_quality_index") if pollution else None)
        if isinstance(traffic_value, (int, float)) and isinstance(aqi_value, (int, float)):
            if traffic_value >= 70 and aqi_value > 100:
                findings.append(
                    "High traffic index and elevated AQI co-occur in the supplied indicators; this is descriptive, not causal."
                )
            else:
                findings.append(
                    "Traffic and AQI outputs show no high-traffic/elevated-AQI co-occurrence under the configured thresholds."
                )
        else:
            findings.append("A traffic/AQI cross-domain comparison was unavailable because one or both agents returned no observation.")

        conflicts: list[str] = []
        observed_by_key: dict[str, tuple[int | float | str | None, str]] = {}
        for result in results:
            for key, value in result.observed_data.items():
                if key in observed_by_key and observed_by_key[key][0] != value:
                    prior_value, prior_agent = observed_by_key[key]
                    conflicts.append(
                        f"{key} differs between {prior_agent} ({prior_value}) and {result.agent_id} ({value})."
                    )
                else:
                    observed_by_key[key] = (value, result.agent_id)
        findings.extend(conflicts or ["No conflicting observations of the same indicator were reported."])

        incomplete = [
            result.agent_id
            for result in results
            if result.status in {AgentState.FAILED, AgentState.UNAVAILABLE, AgentState.WARNING}
        ]
        warnings = []
        if incomplete:
            warnings.append(f"Some upstream outputs were incomplete: {', '.join(incomplete)}.")
        severity = Severity.UNKNOWN if not results else Severity.NORMAL
        now = datetime.now(timezone.utc)
        return AgentResult(
            agent_id=self.agent_id,
            name=self.name,
            status=AgentState.WARNING if incomplete else AgentState.COMPLETED,
            severity=severity,
            started_at=now,
            completed_at=now,
            duration_ms=0,
            findings=findings,
            recommendations=[],
            observed_data=observed_data,
            assumptions=assumptions,
            warnings=warnings,
            metadata={
                "method": self.method,
                "source_agent_count": len(results),
                "conflict_count": len(conflicts),
            },
        )
