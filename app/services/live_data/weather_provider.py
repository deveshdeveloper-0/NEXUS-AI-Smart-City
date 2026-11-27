from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.live_data.base import LiveProvider, ProviderError
from app.services.live_data.cache import TTLCache
from app.services.live_data.city_registry import City
from app.services.live_data.normalizer import normalize_name, parse_number
from app.services.live_data.schemas import (
    Coordinates,
    DailyWeatherForecast,
    DataKind,
    LiveDataStatus,
    WeatherCurrent,
    WeatherResponse,
)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_URL = "https://open-meteo.com/en/docs"
WEATHER_SOURCE = "Open-Meteo (model-based; not direct IMD station observations)"


class WeatherProvider(LiveProvider):
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 8.0,
        cache: TTLCache[WeatherResponse] | None = None,
        imd_fetcher: Callable[[City], Awaitable[WeatherResponse]] | None = None,
    ) -> None:
        super().__init__(client=client, timeout_seconds=timeout_seconds)
        self.cache = cache or TTLCache(ttl_seconds=300, max_stale_seconds=3600)
        self.imd_fetcher = imd_fetcher

    async def get_city_weather(self, city: City) -> WeatherResponse:
        cached = self.cache.get(city.slug)
        if cached is not None:
            return cached.value

        fallback_reason = "IMD was not queried because no verified IMD city/station mapping is configured."
        if self.imd_fetcher is not None:
            try:
                imd_response = await self.imd_fetcher(city)
                if imd_response.status == LiveDataStatus.LIVE:
                    self.cache.put(city.slug, imd_response)
                    return imd_response
                fallback_reason = imd_response.message or "IMD data was unavailable."
            except ProviderError:
                fallback_reason = "IMD request failed; Open-Meteo fallback was used."

        try:
            response = await self._fetch_open_meteo(city, fallback_reason)
        except ProviderError:
            stale = self.cache.get_stale(city.slug)
            if stale is not None and stale.value.status == LiveDataStatus.LIVE:
                return stale.value.model_copy(
                    update={
                        "status": LiveDataStatus.STALE,
                        "is_live": False,
                        "message": (
                            "Open-Meteo could not be refreshed; showing the last "
                            "verified model-based response."
                        ),
                    }
                )
            return WeatherResponse(
                city=city.name,
                city_slug=city.slug,
                status=LiveDataStatus.DATA_UNAVAILABLE,
                source=None,
                fetched_at=datetime.now(timezone.utc),
                is_live=False,
                data_type=DataKind.FORECAST_DATA,
                message="IMD and Open-Meteo weather data are unavailable.",
                source_url=OPEN_METEO_URL,
            )

        if response.status == LiveDataStatus.LIVE:
            self.cache.put(city.slug, response)
        return response

    async def _fetch_open_meteo(
        self,
        city: City,
        fallback_reason: str,
    ) -> WeatherResponse:
        geocoding = await self.request_json(
            "GET",
            GEOCODING_URL,
            params={
                "name": city.name,
                "count": 10,
                "language": "en",
                "format": "json",
            },
        )
        coordinates = self._resolve_coordinates(geocoding, city)
        forecast = await self.request_json(
            "GET",
            FORECAST_URL,
            params={
                "latitude": coordinates.latitude,
                "longitude": coordinates.longitude,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
                "daily": (
                    "temperature_2m_max,temperature_2m_min,"
                    "precipitation_sum,wind_speed_10m_max"
                ),
                "forecast_days": 7,
                "timezone": "auto",
            },
        )
        if not isinstance(forecast, dict):
            raise ProviderError("Open-Meteo returned an invalid forecast response.")
        current_data = forecast.get("current")
        daily_data = forecast.get("daily")
        if not isinstance(current_data, dict) or not isinstance(daily_data, dict):
            raise ProviderError("Open-Meteo omitted current or daily weather data.")
        current_units = forecast.get("current_units")
        if not isinstance(current_units, dict):
            current_units = {}
        current = WeatherCurrent(
            valid_at=self._string_field(current_data, "time"),
            temperature=self._bounded_number(current_data.get("temperature_2m"), -100, 70),
            temperature_unit=self._string_field(current_units, "temperature_2m"),
            humidity=self._bounded_number(current_data.get("relative_humidity_2m"), 0, 100),
            humidity_unit=self._string_field(current_units, "relative_humidity_2m"),
            wind_speed=self._bounded_number(current_data.get("wind_speed_10m"), 0, 500),
            wind_speed_unit=self._string_field(current_units, "wind_speed_10m"),
            precipitation=self._bounded_number(current_data.get("precipitation"), 0, 1000),
            precipitation_unit=self._string_field(current_units, "precipitation"),
        )
        if not any(
            value is not None
            for value in (
                current.temperature,
                current.humidity,
                current.wind_speed,
                current.precipitation,
            )
        ):
            raise ProviderError("Open-Meteo returned no valid current weather values.")

        forecast_days = self._normalize_daily(daily_data)
        daily_units = forecast.get("daily_units")
        if not isinstance(daily_units, dict):
            daily_units = {}
        missing_current_fields = any(
            value is None
            for value in (
                current.temperature,
                current.humidity,
                current.wind_speed,
                current.precipitation,
            )
        )
        message = (
            "Model-based weather output; it is not a direct observation from an IMD station. "
            + fallback_reason
        )
        if len(forecast_days) != 7:
            message += " Open-Meteo returned fewer than seven forecast dates."
        if missing_current_fields:
            message += " One or more current weather fields were absent or invalid."
        return WeatherResponse(
            city=city.name,
            city_slug=city.slug,
            status=LiveDataStatus.LIVE,
            source=WEATHER_SOURCE,
            fetched_at=datetime.now(timezone.utc),
            is_live=True,
            data_type=DataKind.FORECAST_DATA,
            message=message,
            source_url=OPEN_METEO_URL,
            model_based=True,
            coordinates=coordinates,
            timezone=self._string_field(forecast, "timezone"),
            current=current,
            forecast=forecast_days,
            forecast_units={
                key: value
                for key, value in daily_units.items()
                if isinstance(key, str) and isinstance(value, str)
            },
        )

    @staticmethod
    def _resolve_coordinates(payload: Any, city: City) -> Coordinates:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ProviderError("Open-Meteo geocoding returned no results list.")
        matches = []
        for result in payload["results"]:
            if not isinstance(result, dict):
                continue
            if result.get("country_code") != city.country_code:
                continue
            admin1 = result.get("admin1")
            name = result.get("name")
            if not isinstance(admin1, str) or normalize_name(admin1) != normalize_name(city.state):
                continue
            if not isinstance(name, str) or normalize_name(name) != normalize_name(city.name):
                continue
            latitude = parse_number(result.get("latitude"))
            longitude = parse_number(result.get("longitude"))
            if latitude is None or longitude is None:
                continue
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                continue
            matches.append(
                (
                    name.casefold() != city.name.casefold(),
                    -(parse_number(result.get("population")) or 0),
                    Coordinates(latitude=latitude, longitude=longitude),
                )
            )
        if not matches:
            raise ProviderError("Open-Meteo geocoding found no matching city in Uttar Pradesh.")
        matches.sort(key=lambda item: (item[0], item[1]))
        return matches[0][2]

    @staticmethod
    def _string_field(payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _bounded_number(value: Any, minimum: float, maximum: float) -> float | None:
        number = parse_number(value)
        if number is None or not minimum <= number <= maximum:
            return None
        return float(number)

    @staticmethod
    def _normalize_daily(payload: dict[str, Any]) -> list[DailyWeatherForecast]:
        dates = payload.get("time")
        if not isinstance(dates, list):
            raise ProviderError("Open-Meteo daily response omitted its time list.")
        fields = {
            "temperature_2m_max": payload.get("temperature_2m_max"),
            "temperature_2m_min": payload.get("temperature_2m_min"),
            "precipitation_sum": payload.get("precipitation_sum"),
            "wind_speed_10m_max": payload.get("wind_speed_10m_max"),
        }
        forecasts = []
        for index, date in enumerate(dates[:7]):
            if not isinstance(date, str):
                continue
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                continue

            def at(field: str) -> float | None:
                values = fields[field]
                if not isinstance(values, list) or index >= len(values):
                    return None
                value = parse_number(values[index])
                if value is None:
                    return None
                if field in {"precipitation_sum", "wind_speed_10m_max"} and value < 0:
                    return None
                if field.startswith("temperature_2m") and not -100 <= value <= 70:
                    return None
                return float(value)

            forecasts.append(
                DailyWeatherForecast(
                    date=date,
                    temperature_max=at("temperature_2m_max"),
                    temperature_min=at("temperature_2m_min"),
                    precipitation_sum=at("precipitation_sum"),
                    wind_speed_max=at("wind_speed_10m_max"),
                )
            )
        return forecasts
