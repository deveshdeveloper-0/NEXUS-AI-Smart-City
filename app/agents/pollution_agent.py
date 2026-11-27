from datetime import datetime, timezone

from app.agents.base_agent import BaseAgent
from app.agents.schemas import AgentResult, AgentState, CityIndicators, Severity


class PollutionAgent(BaseAgent):
    agent_id = "pollution"
    name = "Pollution Intelligence Agent"
    description = "Classifies AQI indicators and suggests air-quality monitoring."

    async def run(
        self,
        indicators: CityIndicators,
        *,
        prior_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        del prior_results
        value = indicators.air_quality_index
        if value <= 50:
            category, severity = "good", Severity.NORMAL
            recommendation = "Continue routine air-quality monitoring."
        elif value <= 100:
            category, severity = "moderate", Severity.WATCH
            recommendation = "Continue monitoring and review local air-quality advisories."
        elif value <= 150:
            category, severity = "unhealthy for sensitive groups", Severity.ALERT
            recommendation = "Monitor local advisories and investigate relevant emission indicators."
        elif value <= 200:
            category, severity = "unhealthy", Severity.ALERT
            recommendation = "Issue appropriate public-health guidance and investigate potential emission sources."
        elif value <= 300:
            category, severity = "very unhealthy", Severity.ALERT
            recommendation = "Escalate monitoring and follow applicable public-health guidance."
        else:
            category, severity = "hazardous", Severity.ALERT
            recommendation = "Escalate air-quality monitoring and follow emergency public-health guidance."

        now = datetime.now(timezone.utc)
        return AgentResult(
            agent_id=self.agent_id,
            name=self.name,
            status=AgentState.COMPLETED,
            severity=severity,
            started_at=now,
            completed_at=now,
            duration_ms=0,
            findings=[f"AQI {value} is categorized as {category} on the standard 0–500 scale."],
            recommendations=[recommendation],
            observed_data={"air_quality_index": value},
            assumptions=["The AQI value is supplied by the request or synthetic demo data; no sensor source is connected."],
            metadata={"method": self.method, "scale": "AQI 0–500"},
        )
