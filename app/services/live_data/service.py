import asyncio
from datetime import datetime, timezone

from app.services.live_data.aqi_provider import AQIProvider
from app.services.live_data.city_registry import City, get_city, list_cities
from app.services.live_data.energy_provider import EnergyProvider
from app.services.live_data.schemas import (
    LiveCity,
    LiveDataStatus,
    LiveMetricResponse,
    LiveOverview,
    LiveStatusResponse,
    ProviderStatus,
    RouteRequest,
    RouteTrafficResponse,
    WeatherResponse,
)
from app.services.live_data.traffic_provider import TrafficProvider
from app.services.live_data.weather_provider import WeatherProvider


class LiveDataService:
    def __init__(
        self,
        aqi_provider: AQIProvider | None = None,
        weather_provider: WeatherProvider | None = None,
        traffic_provider: TrafficProvider | None = None,
        energy_provider: EnergyProvider | None = None,
    ) -> None:
        self.aqi = aqi_provider or AQIProvider()
        self.weather = weather_provider or WeatherProvider()
        self.traffic = traffic_provider or TrafficProvider()
        self.energy = energy_provider or EnergyProvider()

    @staticmethod
    def cities() -> list[LiveCity]:
        return [
            LiveCity(
                slug=city.slug,
                name=city.name,
                state=city.state,
                country=city.country,
                country_code=city.country_code,
            )
            for city in list_cities()
        ]

    @staticmethod
    def resolve_city(city_slug: str) -> City | None:
        return get_city(city_slug)

    def status(self) -> LiveStatusResponse:
        data_gov_configured = self.aqi.configured
        google_configured = self.traffic.configured
        return LiveStatusResponse(
            checked_at=datetime.now(timezone.utc),
            providers=[
                ProviderStatus(
                    provider="CPCB / data.gov.in",
                    status="CONFIGURED" if data_gov_configured else LiveDataStatus.DATA_UNAVAILABLE.value,
                    configured=data_gov_configured,
                    message=self.aqi.configuration_message,
                ),
                ProviderStatus(
                    provider="India Meteorological Department",
                    status=LiveDataStatus.DATA_UNAVAILABLE.value,
                    configured=False,
                    message=(
                        "No verified IMD city/station mapping is configured. "
                        "Open-Meteo is used as the model-based fallback."
                    ),
                ),
                ProviderStatus(
                    provider="Open-Meteo",
                    status="READY",
                    configured=True,
                    message=(
                        "No key is required; READY is not a live-data claim. "
                        "A validated response is required before a city result is marked LIVE."
                    ),
                ),
                ProviderStatus(
                    provider="Google Maps Routes API",
                    status="CONFIGURED" if google_configured else LiveDataStatus.DATA_UNAVAILABLE.value,
                    configured=google_configured,
                    message=(
                        "A Google Maps API key is configured; route access is not probed by this status endpoint."
                        if google_configured
                        else "GOOGLE_MAPS_API_KEY is missing; route-level traffic cannot be requested."
                    ),
                ),
                ProviderStatus(
                    provider="Authorized energy utility / smart meter",
                    status=LiveDataStatus.DATA_UNAVAILABLE.value,
                    configured=self.energy.configured,
                    message="No authorized utility or smart-meter connection is configured.",
                ),
            ],
        )

    async def get_aqi(self, city: City) -> LiveMetricResponse:
        return await self.aqi.get_city_aqi(city)

    async def get_weather(self, city: City) -> WeatherResponse:
        return await self.weather.get_city_weather(city)

    async def get_traffic_route(
        self,
        request: RouteRequest,
    ) -> RouteTrafficResponse:
        return await self.traffic.get_route(request)

    async def get_overview(self, city: City) -> LiveOverview:
        aqi, weather, energy = await asyncio.gather(
            self.get_aqi(city),
            self.get_weather(city),
            self.energy.get_city_energy(city),
        )
        traffic = self.traffic.unavailable_city(city)
        statuses = (aqi.status, weather.status, energy.status, traffic.status)
        if all(value == LiveDataStatus.LIVE for value in statuses):
            overview_status = LiveDataStatus.LIVE
        elif any(value == LiveDataStatus.LIVE for value in statuses):
            overview_status = LiveDataStatus.PARTIAL
        elif any(value == LiveDataStatus.STALE for value in statuses):
            overview_status = LiveDataStatus.STALE
        else:
            overview_status = LiveDataStatus.DATA_UNAVAILABLE
        return LiveOverview(
            city=LiveCity(
                slug=city.slug,
                name=city.name,
                state=city.state,
                country=city.country,
                country_code=city.country_code,
            ),
            status=overview_status,
            fetched_at=datetime.now(timezone.utc),
            aqi=aqi,
            weather=weather,
            energy=energy,
            traffic=traffic,
        )
