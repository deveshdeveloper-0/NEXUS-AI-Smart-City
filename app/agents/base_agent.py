from abc import ABC, abstractmethod

from app.agents.schemas import AgentResult, CityIndicators


class BaseAgent(ABC):
    agent_id: str
    name: str
    description: str
    method = "transparent rule-based analysis"

    @abstractmethod
    async def run(
        self,
        indicators: CityIndicators,
        *,
        prior_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Analyze validated city indicators and return a structured result."""
