from datetime import datetime, timezone

from app.agents.base_agent import BaseAgent
from app.agents.schemas import AgentResult, AgentState, CityIndicators, Severity


class PredictionAgent(BaseAgent):
    agent_id = "prediction"
    name = "Prediction Agent"
    description = "Runs configured predictive models when trained model artifacts are available."
    method = "trained-model inference (not configured)"

    async def run(
        self,
        indicators: CityIndicators,
        *,
        prior_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        del prior_results
        now = datetime.now(timezone.utc)
        return AgentResult(
            agent_id=self.agent_id,
            name=self.name,
            status=AgentState.UNAVAILABLE,
            severity=Severity.UNKNOWN,
            started_at=now,
            completed_at=now,
            duration_ms=0,
            findings=["No trained prediction models or model artifacts are present in this project."],
            recommendations=[],
            observed_data={},
            warnings=["No prediction values were generated."],
            metadata={
                "model_status": "unavailable",
                "model_names": None,
                "prediction_horizon": None,
            },
        )
