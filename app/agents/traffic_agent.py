from datetime import datetime, timezone

from app.agents.base_agent import BaseAgent
from app.agents.schemas import AgentResult, AgentState, CityIndicators, Severity


class TrafficAgent(BaseAgent):
    agent_id = "traffic"
    name = "Traffic Intelligence Agent"
    description = "Classifies the traffic index and suggests monitoring actions."

    async def run(
        self,
        indicators: CityIndicators,
        *,
        prior_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        del prior_results
        value = indicators.traffic_index
        if value >= 70:
            category, severity = "high congestion", Severity.ALERT
            recommendation = "Review congestion hotspots and consider signal-timing optimization."
        elif value >= 40:
            category, severity = "moderate congestion", Severity.WATCH
            recommendation = "Monitor corridor-level traffic and compare conditions during peak periods."
        else:
            category, severity = "low congestion", Severity.NORMAL
            recommendation = "Continue monitoring traffic conditions."

        now = datetime.now(timezone.utc)
        return AgentResult(
            agent_id=self.agent_id,
            name=self.name,
            status=AgentState.COMPLETED,
            severity=severity,
            started_at=now,
            completed_at=now,
            duration_ms=0,
            findings=[f"Traffic index {value}/100 indicates {category}."],
            recommendations=[recommendation],
            observed_data={"traffic_index": value},
            assumptions=["The traffic index is a supplied city indicator; it is not a measured vehicle count."],
            metadata={"method": self.method},
        )
