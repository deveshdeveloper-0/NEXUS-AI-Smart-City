import hashlib
import os
import re
from datetime import datetime, timezone

import httpx

from app.services.live_data.base import LiveProvider, ProviderError
from app.services.live_data.cache import TTLCache
from app.services.live_data.city_registry import City, get_city
from app.services.live_data.normalizer import parse_number
from app.services.live_data.schemas import (
    DataKind,
    LiveDataStatus,
    LiveMetricResponse,
    RouteRequest,
    RouteTrafficResponse,
)

GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
GOOGLE_ROUTES_DOCS = "https://developers.google.com/maps/documentation/routes"


class TrafficProvider(LiveProvider):
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 8.0,
        cache: TTLCache[RouteTrafficResponse] | None = None,
    ) -> None:
        super().__init__(client=client, timeout_seconds=timeout_seconds)
        self.cache = cache or TTLCache(ttl_seconds=30, max_stale_seconds=300)

    @property
    def configured(self) -> bool:
        return bool(os.getenv("GOOGLE_MAPS_API_KEY", "").strip())

    async def get_route(self, request: RouteRequest) -> RouteTrafficResponse:
        city = get_city(request.city_slug) if request.city_slug else None
        city_name = city.name if city else None
        key = self._cache_key(request)
        cached = self.cache.get(key)
        if cached is not None:
            return cached.value

        api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
        if not api_key:
            stale = self.cache.get_stale(key)
            if stale and stale.value.status == LiveDataStatus.LIVE:
                return stale.value.model_copy(
                    update={
                        "status": LiveDataStatus.STALE,
                        "is_live": False,
                        "message": "Google Maps could not be refreshed; showing the last verified route response.",
                    }
                )
            return self._unavailable(
                request,
                city_name,
                "GOOGLE_MAPS_API_KEY is not configured; no route request was made.",
            )

        try:
            payload = await self.request_json(
                "POST",
                GOOGLE_ROUTES_URL,
                json={
                    "origin": {"address": request.origin},
                    "destination": {"address": request.destination},
                    "travelMode": "DRIVE",
                    "routingPreference": "TRAFFIC_AWARE",
                    "computeAlternativeRoutes": False,
                },
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": (
                        "routes.distanceMeters,routes.duration,routes.staticDuration"
                    ),
                },
            )
        except ProviderError as exc:
            stale = self.cache.get_stale(key)
            if stale and stale.value.status == LiveDataStatus.LIVE:
                return stale.value.model_copy(
                    update={
                        "status": LiveDataStatus.STALE,
                        "is_live": False,
                        "message": (
                            f"{self._failure_message(exc)} "
                            "Showing the last verified route ETA as stale."
                        ),
                    }
                )
            return self._unavailable(
                request,
                city_name,
                self._failure_message(exc),
            )

        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            provider_status = error.get("status")
            return self._unavailable(
                request,
                city_name,
                self._failure_message(
                    ProviderError(
                        "Google Routes returned an API error.",
                        provider_status=(
                            provider_status if isinstance(provider_status, str) else None
                        ),
                        failure_kind="http",
                    )
                ),
            )
        routes = payload.get("routes") if isinstance(payload, dict) else None
        if not isinstance(routes, list) or not routes:
            return self._unavailable(
                request,
                city_name,
                "Google Routes found no route; check the origin and destination locations.",
            )
        if not isinstance(routes[0], dict):
            return self._unavailable(
                request,
                city_name,
                "Google Routes returned an invalid route response.",
            )
        route = routes[0]
        duration = self._duration(route.get("duration"))
        static_duration = self._duration(route.get("staticDuration"))
        distance_meters = parse_number(route.get("distanceMeters"))
        if duration is None or distance_meters is None or distance_meters < 0:
            return self._unavailable(
                request,
                city_name,
                "Google Routes omitted a valid route distance or traffic-aware duration.",
            )

        result = RouteTrafficResponse(
            city=city_name,
            city_slug=request.city_slug,
            status=LiveDataStatus.LIVE,
            origin=request.origin,
            destination=request.destination,
            distance_meters=distance_meters,
            duration=duration,
            static_duration=static_duration,
            source="Google Maps Routes API",
            fetched_at=datetime.now(timezone.utc),
            is_live=True,
            message="Route-level traffic-aware ETA; this is not a city-wide traffic measurement.",
            source_url=GOOGLE_ROUTES_DOCS,
        )
        self.cache.put(key, result)
        return result

    @staticmethod
    def _duration(value: object) -> str | None:
        if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+)?s", value):
            return None
        return value

    @staticmethod
    def _cache_key(request: RouteRequest) -> str:
        route = (
            f"{request.city_slug or ''}|{request.origin.casefold().strip()}|"
            f"{request.destination.casefold().strip()}"
        )
        return "route:" + hashlib.sha256(route.encode("utf-8")).hexdigest()

    @staticmethod
    def _failure_message(error: ProviderError) -> str:
        provider_status = error.provider_status
        if error.failure_kind == "timeout":
            return "Google Routes request timed out; try again later."
        if error.failure_kind == "network":
            return "Could not reach Google Routes; check the backend network and try again."
        if provider_status in {"RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED"} or error.status_code == 429:
            return "Google Routes quota or rate limit was reached; check usage limits before retrying."
        if provider_status in {"PERMISSION_DENIED", "API_KEY_INVALID", "BILLING_DISABLED"} or error.status_code in {401, 403}:
            return "Google Routes access was denied; verify the API key, Routes API access, and billing."
        if provider_status in {"INVALID_ARGUMENT", "NOT_FOUND"} or error.status_code == 400:
            return "Google Routes rejected the location input; check that both addresses are valid."
        if error.status_code is not None and error.status_code >= 500:
            return "Google Routes is temporarily unavailable; try again later."
        return "Google Routes returned an unavailable or invalid response."

    @staticmethod
    def _unavailable(
        request: RouteRequest,
        city_name: str | None,
        message: str,
    ) -> RouteTrafficResponse:
        return RouteTrafficResponse(
            city=city_name,
            city_slug=request.city_slug,
            status=LiveDataStatus.DATA_UNAVAILABLE,
            origin=request.origin,
            destination=request.destination,
            source=None,
            is_live=False,
            message=message,
            source_url=GOOGLE_ROUTES_DOCS,
        )

    @staticmethod
    def unavailable_city(city: City) -> LiveMetricResponse:
        return LiveMetricResponse(
            city=city.name,
            city_slug=city.slug,
            metric="traffic",
            status=LiveDataStatus.DATA_UNAVAILABLE,
            source=None,
            is_live=False,
            data_type=DataKind.OBSERVED_DATA,
            message="No city-wide traffic feed is configured; request a route-level ETA instead.",
            source_url=GOOGLE_ROUTES_DOCS,
        )
