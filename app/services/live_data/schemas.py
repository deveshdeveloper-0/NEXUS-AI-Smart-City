from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LiveDataStatus(str, Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    PARTIAL = "PARTIAL"


class DataKind(str, Enum):
    OBSERVED_DATA = "OBSERVED_DATA"
    FORECAST_DATA = "FORECAST_DATA"
    MODEL_PREDICTION = "MODEL_PREDICTION"
    DEMO_DATA = "DEMO_DATA"


class LiveCity(BaseModel):
    slug: str
    name: str
    state: str
    country: str
    country_code: str


class PollutantValues(BaseModel):
    average: float | None = None
    minimum: float | None = None
    maximum: float | None = None


class AQIStationObservation(BaseModel):
    station: str | None = None
    aqi: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    observed_at: str | None = None
    pollutants: dict[str, PollutantValues] = Field(default_factory=dict)


class LiveMetricResponse(BaseModel):
    city: str
    city_slug: str
    metric: str
    status: LiveDataStatus
    value: float | int | None = None
    unit: str | None = None
    source: str | None = None
    station: str | None = None
    observed_at: str | None = None
    fetched_at: datetime | None = None
    is_live: bool = False
    data_type: DataKind
    message: str | None = None
    source_url: str | None = None
    station_observations: list[AQIStationObservation] = Field(default_factory=list)
    provider_metadata: dict[str, str | int | float | None] = Field(default_factory=dict)


class WeatherCurrent(BaseModel):
    valid_at: str | None = None
    temperature: float | None = None
    temperature_unit: str | None = None
    humidity: float | None = None
    humidity_unit: str | None = None
    wind_speed: float | None = None
    wind_speed_unit: str | None = None
    precipitation: float | None = None
    precipitation_unit: str | None = None


class DailyWeatherForecast(BaseModel):
    date: str
    temperature_max: float | None = None
    temperature_min: float | None = None
    precipitation_sum: float | None = None
    wind_speed_max: float | None = None


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class WeatherResponse(BaseModel):
    city: str
    city_slug: str
    metric: Literal["weather"] = "weather"
    status: LiveDataStatus
    value: None = None
    unit: None = None
    source: str | None = None
    station: None = None
    observed_at: None = None
    fetched_at: datetime | None = None
    is_live: bool = False
    data_type: DataKind = DataKind.FORECAST_DATA
    message: str | None = None
    source_url: str | None = None
    model_based: bool = True
    coordinates: Coordinates | None = None
    timezone: str | None = None
    current: WeatherCurrent | None = None
    forecast: list[DailyWeatherForecast] = Field(default_factory=list)
    forecast_units: dict[str, str] = Field(default_factory=dict)


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origin: str = Field(min_length=2, max_length=256)
    destination: str = Field(min_length=2, max_length=256)
    city_slug: Literal["varanasi", "shahjahanpur"] | None = None


class RouteTrafficResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    city: str | None = None
    city_slug: str | None = None
    metric: Literal["route_traffic"] = "route_traffic"
    status: LiveDataStatus
    origin: str
    destination: str
    routing_preference: Literal["TRAFFIC_AWARE"] = "TRAFFIC_AWARE"
    distance_meters: int | float | None = Field(default=None, alias="distanceMeters")
    duration: str | None = None
    static_duration: str | None = Field(default=None, alias="staticDuration")
    source: str | None = None
    data_type: DataKind = DataKind.FORECAST_DATA
    fetched_at: datetime | None = None
    is_live: bool = False
    route_level_only: Literal[True] = True
    message: str | None = None
    source_url: str | None = None


class LiveOverview(BaseModel):
    city: LiveCity
    status: LiveDataStatus
    fetched_at: datetime
    aqi: LiveMetricResponse
    weather: WeatherResponse
    energy: LiveMetricResponse
    traffic: LiveMetricResponse


class ProviderStatus(BaseModel):
    provider: str
    status: str
    configured: bool
    message: str


class LiveStatusResponse(BaseModel):
    api_status: Literal["ONLINE"] = "ONLINE"
    checked_at: datetime
    providers: list[ProviderStatus]
