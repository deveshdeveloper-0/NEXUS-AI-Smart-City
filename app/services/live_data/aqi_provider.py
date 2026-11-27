import os
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.services.live_data.base import LiveProvider, ProviderError
from app.services.live_data.cache import TTLCache
from app.services.live_data.city_registry import City
from app.services.live_data.normalizer import normalize_cpcb_payload
from app.services.live_data.schemas import DataKind, LiveDataStatus, LiveMetricResponse

CPCB_RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
CPCB_RESOURCE_URL = (
    "https://data.gov.in/resource/real-time-air-quality-index-various-locations"
)
CPCB_API_URL = "https://api.data.gov.in/resource"


class AQIProvider(LiveProvider):
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 8.0,
        cache: TTLCache[LiveMetricResponse] | None = None,
    ) -> None:
        super().__init__(client=client, timeout_seconds=timeout_seconds)
        self.cache = cache or TTLCache(ttl_seconds=300, max_stale_seconds=3600)

    @property
    def configured(self) -> bool:
        return bool(
            os.getenv("DATA_GOV_API_KEY", "").strip()
            and self._resource_id() is not None
        )

    @property
    def configuration_message(self) -> str:
        if not os.getenv("DATA_GOV_API_KEY", "").strip():
            return "DATA_GOV_API_KEY is missing; CPCB data cannot be requested."
        if self._resource_id() is None:
            return "DATA_GOV_RESOURCE_ID is invalid; CPCB data cannot be requested."
        return "A data.gov.in API key is configured; provider is not probed by this status endpoint."

    @staticmethod
    def _resource_id() -> str | None:
        value = os.getenv("DATA_GOV_RESOURCE_ID", "").strip() or CPCB_RESOURCE_ID
        try:
            return str(UUID(value))
        except ValueError:
            return None

    def _unavailable(
        self,
        city: City,
        message: str,
        *,
        fetched_at: datetime | None = None,
    ) -> LiveMetricResponse:
        return LiveMetricResponse(
            city=city.name,
            city_slug=city.slug,
            metric="aqi",
            status=LiveDataStatus.DATA_UNAVAILABLE,
            source=None,
            fetched_at=fetched_at,
            is_live=False,
            data_type=DataKind.OBSERVED_DATA,
            message=message,
            source_url=CPCB_RESOURCE_URL,
        )

    def _stale_or_unavailable(
        self,
        city: City,
        cache_key: str,
        message: str,
    ) -> LiveMetricResponse:
        cached = self.cache.get_stale(cache_key)
        if cached is not None and cached.value.status == LiveDataStatus.LIVE:
            return cached.value.model_copy(
                update={
                    "status": LiveDataStatus.STALE,
                    "is_live": False,
                    "message": "CPCB could not be refreshed; showing the last verified station response.",
                }
            )
        return self._unavailable(city, message, fetched_at=datetime.now(timezone.utc))

    async def get_city_aqi(self, city: City) -> LiveMetricResponse:
        resource_id = self._resource_id()
        cache_key = f"{city.slug}:{resource_id or 'invalid-resource'}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached.value

        api_key = os.getenv("DATA_GOV_API_KEY", "").strip()
        if not api_key:
            return self._stale_or_unavailable(
                city,
                cache_key,
                "DATA_GOV_API_KEY is not configured; no CPCB request was made.",
            )
        if resource_id is None:
            return self._unavailable(
                city,
                "DATA_GOV_RESOURCE_ID is not a valid resource identifier.",
            )

        try:
            payload = await self.request_json(
                "GET",
                f"{CPCB_API_URL}/{resource_id}",
                params={
                    "api-key": api_key,
                    "format": "json",
                    "offset": 0,
                    "limit": "all",
                },
            )
            station_observations, metadata = normalize_cpcb_payload(payload, city)
        except ProviderError:
            return self._stale_or_unavailable(
                city,
                cache_key,
                "CPCB data could not be retrieved or validated.",
            )

        valid_station_values = [
            observation
            for observation in station_observations
            if observation.aqi is not None
        ]
        fetched_at = datetime.now(timezone.utc)
        if len(valid_station_values) == 1:
            observation = valid_station_values[0]
            result = LiveMetricResponse(
                city=city.name,
                city_slug=city.slug,
                metric="aqi",
                status=LiveDataStatus.LIVE,
                value=observation.aqi,
                unit="AQI",
                source="CPCB, data.gov.in",
                station=observation.station,
                observed_at=observation.observed_at,
                fetched_at=fetched_at,
                is_live=True,
                data_type=DataKind.OBSERVED_DATA,
                source_url=CPCB_RESOURCE_URL,
                station_observations=station_observations,
                provider_metadata=metadata,
            )
        elif valid_station_values:
            result = LiveMetricResponse(
                city=city.name,
                city_slug=city.slug,
                metric="aqi",
                status=LiveDataStatus.LIVE,
                unit="AQI",
                source="CPCB, data.gov.in",
                fetched_at=fetched_at,
                is_live=True,
                data_type=DataKind.OBSERVED_DATA,
                message=(
                    "Multiple station readings are returned individually; "
                    "no city-wide average is calculated."
                ),
                source_url=CPCB_RESOURCE_URL,
                station_observations=station_observations,
                provider_metadata=metadata,
            )
        else:
            result = LiveMetricResponse(
                city=city.name,
                city_slug=city.slug,
                metric="aqi",
                status=LiveDataStatus.DATA_UNAVAILABLE,
                source="CPCB, data.gov.in" if station_observations else None,
                fetched_at=fetched_at,
                is_live=False,
                data_type=DataKind.OBSERVED_DATA,
                message=(
                    "CPCB returned no matching monitoring station."
                    if not station_observations
                    else "Matching station records contain no valid AQI value."
                ),
                source_url=CPCB_RESOURCE_URL,
                station_observations=station_observations,
                provider_metadata=metadata,
            )

        if result.status == LiveDataStatus.LIVE:
            self.cache.put(cache_key, result)
        return result
