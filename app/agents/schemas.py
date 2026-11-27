from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AgentState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    WARNING = "warning"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class Severity(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    ALERT = "alert"
    UNKNOWN = "unknown"


class ReportState(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class CityIndicators(BaseModel):
    model_config = ConfigDict(extra="forbid")

    traffic_index: int = Field(ge=0, le=100)
    air_quality_index: int = Field(ge=0, le=500)
    energy_load_percent: int = Field(ge=0, le=100)


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicators: CityIndicators | None = None


class AgentDefinition(BaseModel):
    agent_id: str
    name: str
    description: str
    method: str


class AgentExecutionStatus(BaseModel):
    agent_id: str
    name: str
    status: AgentState
    updated_at: datetime | None = None
    error: str | None = None


class AgentResult(BaseModel):
    agent_id: str
    name: str
    status: AgentState
    severity: Severity = Severity.UNKNOWN
    started_at: datetime
    completed_at: datetime
    duration_ms: float = Field(ge=0)
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    observed_data: dict[str, int | float | str | None] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    error: str | None = None


class IntelligenceReport(BaseModel):
    report_id: str
    status: ReportState
    started_at: datetime
    completed_at: datetime
    duration_ms: float = Field(ge=0)
    data_source: str
    data_mode: str
    input_data: CityIndicators
    summary: str
    results: list[AgentResult]
    limitations: list[str]


class AgentStatusResponse(BaseModel):
    execution_active: bool
    agents: list[AgentExecutionStatus]
