import asyncio
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from app.agents.base_agent import BaseAgent
from app.agents.energy_agent import EnergyAgent
from app.agents.pollution_agent import PollutionAgent
from app.agents.prediction_agent import PredictionAgent
from app.agents.research_agent import ResearchAgent
from app.agents.schemas import (
    AgentDefinition,
    AgentExecutionStatus,
    AgentResult,
    AgentState,
    CityIndicators,
    IntelligenceReport,
    ReportState,
    Severity,
)
from app.agents.traffic_agent import TrafficAgent

logger = logging.getLogger(__name__)

LIMITATIONS = [
    "Default indicators are synthetic demonstration values, not live city telemetry.",
    "Traffic, pollution, and energy findings use transparent rules and are not trained predictions.",
    "No prediction models are configured; no prediction values or horizons are available.",
    "Research summaries use only the supplied indicators and agent outputs; no external sources are consulted.",
    "Recommendations are decision support for human review; agents do not control infrastructure.",
]


class ExecutionInProgressError(Exception):
    """Raised when a coordinated run is already in progress."""


class IntelligenceCoordinator:
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.agents: dict[str, BaseAgent] = {
            agent.agent_id: agent
            for agent in (
                TrafficAgent(),
                PollutionAgent(),
                EnergyAgent(),
                PredictionAgent(),
                ResearchAgent(),
            )
        }
        self.timeout_seconds = timeout_seconds
        self._run_lock = asyncio.Lock()
        self._active = False
        self._latest_report: IntelligenceReport | None = None
        self._statuses = {
            agent_id: AgentExecutionStatus(
                agent_id=agent_id,
                name=agent.name,
                status=AgentState.IDLE,
            )
            for agent_id, agent in self.agents.items()
        }

    @property
    def execution_active(self) -> bool:
        return self._active

    def definitions(self) -> list[AgentDefinition]:
        return [
            AgentDefinition(
                agent_id=agent.agent_id,
                name=agent.name,
                description=agent.description,
                method=agent.method,
            )
            for agent in self.agents.values()
        ]

    def statuses(self) -> list[AgentExecutionStatus]:
        return [status.model_copy() for status in self._statuses.values()]

    def latest_report(self) -> IntelligenceReport | None:
        return self._latest_report

    def _set_status(
        self,
        agent: BaseAgent,
        status: AgentState,
        *,
        error: str | None = None,
    ) -> None:
        self._statuses[agent.agent_id] = AgentExecutionStatus(
            agent_id=agent.agent_id,
            name=agent.name,
            status=status,
            updated_at=datetime.now(timezone.utc),
            error=error,
        )

    async def _execute(
        self,
        agent: BaseAgent,
        indicators: CityIndicators,
        prior_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        started_at = datetime.now(timezone.utc)
        started_clock = time.perf_counter()
        self._set_status(agent, AgentState.RUNNING)
        try:
            result = await asyncio.wait_for(
                agent.run(indicators, prior_results=prior_results),
                timeout=self.timeout_seconds,
            )
            result.started_at = started_at
            result.completed_at = datetime.now(timezone.utc)
            result.duration_ms = round((time.perf_counter() - started_clock) * 1000, 3)
            self._set_status(agent, result.status, error=result.error)
            return result
        except asyncio.TimeoutError:
            message = f"Execution timed out after {self.timeout_seconds:g} seconds."
            logger.warning("Agent %s timed out", agent.agent_id)
            result = self._failed_result(agent, started_at, started_clock, message)
            self._set_status(agent, AgentState.FAILED, error=message)
            return result
        except Exception:
            logger.exception("Agent %s execution failed", agent.agent_id)
            message = "Agent execution failed; consult server logs."
            result = self._failed_result(agent, started_at, started_clock, message)
            self._set_status(agent, AgentState.FAILED, error=message)
            return result

    @staticmethod
    def _failed_result(
        agent: BaseAgent,
        started_at: datetime,
        started_clock: float,
        message: str,
    ) -> AgentResult:
        return AgentResult(
            agent_id=agent.agent_id,
            name=agent.name,
            status=AgentState.FAILED,
            severity=Severity.UNKNOWN,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            duration_ms=round((time.perf_counter() - started_clock) * 1000, 3),
            warnings=[message],
            error=message,
        )

    async def run(
        self,
        indicators: CityIndicators,
        *,
        data_source: str,
        data_mode: str,
    ) -> IntelligenceReport:
        if self._run_lock.locked():
            raise ExecutionInProgressError("An agent run is already in progress.")
        await self._run_lock.acquire()
        self._active = True
        started_at = datetime.now(timezone.utc)
        started_clock = time.perf_counter()
        try:
            independent_ids = ("traffic", "pollution", "energy", "prediction")
            independent_results = await asyncio.gather(
                *(
                    self._execute(self.agents[agent_id], indicators)
                    for agent_id in independent_ids
                )
            )
            research = await self._execute(
                self.agents["research"],
                indicators,
                prior_results=independent_results,
            )
            results = [*independent_results, research]
            statuses = {result.status for result in results}
            successful_independent = any(
                result.status == AgentState.COMPLETED
                for result in independent_results
            )
            if not successful_independent:
                report_status = ReportState.FAILED
            elif any(
                status in {AgentState.FAILED, AgentState.WARNING, AgentState.UNAVAILABLE}
                for status in statuses
            ):
                report_status = ReportState.PARTIAL
            else:
                report_status = ReportState.COMPLETED
            alerts = sum(
                result.severity == Severity.ALERT
                for result in independent_results
                if result.status == AgentState.COMPLETED
            )
            watches = sum(
                result.severity == Severity.WATCH
                for result in independent_results
                if result.status == AgentState.COMPLETED
            )
            summary = (
                f"Rule-based agents reported {alerts} alert-level and {watches} watch-level finding(s)."
            )
            if report_status != ReportState.COMPLETED:
                summary += " One or more agents returned incomplete or unavailable results."

            report = IntelligenceReport(
                report_id=str(uuid4()),
                status=report_status,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                duration_ms=round((time.perf_counter() - started_clock) * 1000, 3),
                data_source=data_source,
                data_mode=data_mode,
                input_data=indicators,
                summary=summary,
                results=results,
                limitations=LIMITATIONS,
            )
            self._latest_report = report
            return report
        finally:
            self._active = False
            for agent_id, status in tuple(self._statuses.items()):
                if status.status == AgentState.RUNNING:
                    agent = self.agents[agent_id]
                    self._set_status(
                        agent,
                        AgentState.FAILED,
                        error="Execution was cancelled before the agent completed.",
                    )
            self._run_lock.release()
