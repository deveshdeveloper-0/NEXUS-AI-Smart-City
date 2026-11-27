from datetime import datetime, timezone

from app.agents.base_agent import BaseAgent
from app.agents.schemas import AgentResult, AgentState, CityIndicators, Severity


class EnergyAgent(BaseAgent):
    agent_id = "energy"
    name = "Energy Intelligence Agent"
    description = "Classifies energy load and suggests demand-management actions."

    async def run(
        self,
        indicators: CityIndicators,
        *,
        prior_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        del prior_results
        value = indicators.energy_load_percent
        if value >= 85:
            category, severity = "critical high load", Severity.ALERT
            recommendation = "Review peak demand and assess operator-approved demand-management options."
        elif value >= 70:
            category, severity = "high load", Severity.WATCH
            recommendation = "Review peak-load periods and assess demand-management options."
        elif value >= 50:
            category, severity = "moderate load", Severity.NORMAL
            recommendation = "Continue load monitoring and compare demand across operating periods."
        else:
            category, severity = "normal load", Severity.NORMAL
            recommendation = "Continue routine energy-load monitoring."

        now = datetime.now(timezone.utc)
        return AgentResult(
            agent_id=self.agent_id,
            name=self.name,
            status=AgentState.COMPLETED,
            severity=severity,
            started_at=now,
            completed_at=now,
            duration_ms=0,
            findings=[f"Energy load {value}% indicates {category}."],
            recommendations=[recommendation],
            observed_data={"energy_load_percent": value},
            assumptions=["The percentage is a supplied load indicator; grid capacity and live demand are not connected."],
            metadata={"method": self.method},
        )
