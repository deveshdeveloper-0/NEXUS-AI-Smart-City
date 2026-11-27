import asyncio
import json
import secrets
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.live_data.aqi_provider import AQIProvider
from app.services.live_data.base import ProviderError
from app.services.live_data.cache import TTLCache
from app.services.live_data.city_registry import get_city, list_cities
from app.services.live_data.energy_provider import EnergyProvider
from app.services.live_data.normalizer import normalize_cpcb_payload, normalize_name
from app.services.live_data.schemas import (
    DataKind,
    LiveDataStatus,
    RouteRequest,
    RouteTrafficResponse,
    WeatherResponse,
)
from app.services.live_data.traffic_provider import TrafficProvider
from app.services.live_data.weather_provider import WeatherProvider
import app.main as main_module

client = TestClient(app)


def run_async(awaitable):
    return asyncio.run(awaitable)


def configure_test_key(monkeypatch, name):
    value = secrets.token_urlsafe(32)
    monkeypatch.setenv(name, value)
    return value


def cpcb_payload(city="Varanasi", *, aqi="82", station="Station One"):
    latitude = "25.32" if city == "Varanasi" else "27.88"
    longitude = "83.01" if city == "Varanasi" else "79.91"
    return {
        "total": 1,
        "count": 1,
        "limit": "all",
        "offset": 0,
        "records": [
            {
                "country": "India",
                "state": "Uttar Pradesh",
                "city": city,
                "station": station,
                "latitude": latitude,
                "longitude": longitude,
                "pollutant_id": "PM2.5",
                "pollutant_min": "20",
                "pollutant_max": "45",
                "pollutant_avg": "35",
                "aqi": aqi,
                "observed_at": "2026-11-26T10:00:00Z",
            }
        ],
    }


def geocoding_payload(name="Varanasi"):
    return {
        "results": [
            {
                "name": name,
                "country_code": "IN",
                "admin1": "Odisha",
                "latitude": 18.85,
                "longitude": 83.87,
            },
            {
                "name": "Vāranāsi",
                "country_code": "IN",
                "admin1": "Uttar Pradesh",
                "latitude": 25.0,
                "longitude": 83.0,
                "population": 1,
            },
            {
                "name": name,
                "country_code": "IN",
                "admin1": "Uttar Pradesh",
                "latitude": 25.32 if name == "Varanasi" else 27.88,
                "longitude": 83.01 if name == "Varanasi" else 79.91,
                "population": 100,
            },
        ]
    }


def open_meteo_payload():
    return {
        "timezone": "Asia/Kolkata",
        "current": {
            "time": "2026-11-26T22:45",
            "temperature_2m": 17.2,
            "relative_humidity_2m": 79,
            "wind_speed_10m": 4.7,
            "precipitation": 0,
        },
        "current_units": {
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "wind_speed_10m": "km/h",
            "precipitation": "mm",
        },
        "daily_units": {
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "precipitation_sum": "mm",
            "wind_speed_10m_max": "km/h",
        },
        "daily": {
            "time": [
                "2026-11-26",
                "2026-11-27",
                "2026-11-28",
                "2026-11-29",
                "2026-11-30",
                "2026-12-01",
                "2026-12-02",
            ],
            "temperature_2m_max": [28, 27, 27, 26, 26, 25, 25],
            "temperature_2m_min": [17, 16, 16, 15, 15, 14, 14],
            "precipitation_sum": [0, 0, 0, 0, 0, 0, 0],
            "wind_speed_10m_max": [12, 12, 11, 11, 10, 10, 9],
        },
    }


def make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("slug", "expected_name"),
    [("varanasi", "Varanasi"), ("shahjahanpur", "Shahjahanpur")],
)
def test_city_registry_has_only_requested_cities(slug, expected_name):
    city = get_city(slug)

    assert city is not None
    assert city.name == expected_name
    assert city.state == "Uttar Pradesh"
    assert city.country_code == "IN"
    assert {item.slug for item in list_cities()} == {"varanasi", "shahjahanpur"}


def test_city_name_normalization_handles_accents_and_punctuation():
    assert normalize_name("Vāranāsi, Uttar Pradesh") == "varanasi uttar pradesh"
    assert normalize_name("Shahjahanpur") == "shahjahanpur"


def test_cpcb_returns_actual_single_station_aqi_and_pollutants(monkeypatch):
    api_key = configure_test_key(monkeypatch, "DATA_GOV_API_KEY")
    resource_id = "00000000-0000-0000-0000-000000000001"
    monkeypatch.setenv("DATA_GOV_RESOURCE_ID", resource_id)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=cpcb_payload())

    async def scenario():
        async with make_client(handler) as mocked_client:
            provider = AQIProvider(client=mocked_client)
            return await provider.get_city_aqi(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.LIVE
    assert result.value == 82
    assert result.station == "Station One"
    assert result.observed_at == "2026-11-26T10:00:00Z"
    assert result.station_observations[0].pollutants["PM2.5"].average == 35
    assert result.provider_metadata["total"] == 1
    assert requests[0].url.path.endswith(f"/{resource_id}")
    assert requests[0].url.params["api-key"] == api_key


def test_cpcb_matches_shahjahanpur_records_by_state_and_normalized_city(monkeypatch):
    configure_test_key(monkeypatch, "DATA_GOV_API_KEY")
    payload = cpcb_payload("Shāhjahānpur", aqi="61", station="Shahjahanpur Station")

    async def scenario():
        async with make_client(
            lambda request: httpx.Response(200, json=payload)
        ) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(
                get_city("shahjahanpur")
            )

    result = run_async(scenario())

    assert result.status == LiveDataStatus.LIVE
    assert result.city == "Shahjahanpur"
    assert result.value == 61
    assert result.station == "Shahjahanpur Station"


def test_cpcb_uses_verified_default_resource_id(monkeypatch):
    configure_test_key(monkeypatch, "DATA_GOV_API_KEY")
    monkeypatch.delenv("DATA_GOV_RESOURCE_ID", raising=False)
    request_path = []

    def handler(request):
        request_path.append(request.url.path)
        return httpx.Response(200, json=cpcb_payload())

    async def scenario():
        async with make_client(handler) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.LIVE
    assert request_path[0].endswith("3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69")


def test_cpcb_never_treats_pollutant_average_as_aqi(monkeypatch):
    configure_test_key(monkeypatch, "DATA_GOV_API_KEY")

    def handler(request):
        payload = cpcb_payload()
        del payload["records"][0]["aqi"]
        return httpx.Response(200, json=payload)

    async def scenario():
        async with make_client(handler) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.value is None
    assert result.station_observations[0].pollutants["PM2.5"].average == 35
    assert "no valid AQI" in result.message


def test_cpcb_does_not_average_multiple_station_readings(monkeypatch):
    configure_test_key(monkeypatch, "DATA_GOV_API_KEY")
    payload = cpcb_payload()
    payload["records"].append(dict(payload["records"][0], station="Station Two", aqi="90"))

    async def scenario():
        async with make_client(
            lambda request: httpx.Response(200, json=payload)
        ) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.LIVE
    assert result.value is None
    assert len(result.station_observations) == 2
    assert "no city-wide average" in result.message


def test_cpcb_returns_data_unavailable_when_city_has_no_station(monkeypatch):
    configure_test_key(monkeypatch, "DATA_GOV_API_KEY")

    async def scenario():
        async with make_client(
            lambda request: httpx.Response(200, json={"records": [], "total": 0})
        ) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(get_city("shahjahanpur"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.value is None
    assert result.source is None
    assert result.station_observations == []
    assert "no matching monitoring station" in result.message


def test_cpcb_missing_api_key_does_not_make_request(monkeypatch):
    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    calls = []

    async def scenario():
        async with make_client(lambda request: calls.append(request)) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.value is None
    assert calls == []
    assert "not configured" in result.message


def test_cpcb_failure_does_not_expose_api_key_in_response_or_logs(monkeypatch, caplog):
    api_key = configure_test_key(monkeypatch, "DATA_GOV_API_KEY")

    async def scenario():
        async with make_client(
            lambda request: httpx.Response(403, json={"error": "unauthorized"})
        ) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(
                get_city("varanasi")
            )

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert api_key not in result.model_dump_json()
    assert api_key not in caplog.text


def test_cpcb_invalid_resource_id_does_not_make_request(monkeypatch):
    configure_test_key(monkeypatch, "DATA_GOV_API_KEY")
    monkeypatch.setenv("DATA_GOV_RESOURCE_ID", "not-a-resource-id")
    calls = []

    async def scenario():
        async with make_client(lambda request: calls.append(request)) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(
                get_city("varanasi")
            )

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.value is None
    assert calls == []
    assert "not a valid resource identifier" in result.message


@pytest.mark.parametrize(
    "payload",
    [{"records": "not-a-list"}, {"message": "unexpected schema"}, None],
)
def test_cpcb_malformed_responses_never_create_values(monkeypatch, payload):
    configure_test_key(monkeypatch, "DATA_GOV_API_KEY")

    async def scenario():
        async with make_client(
            lambda request: httpx.Response(200, json=payload)
        ) as mocked_client:
            return await AQIProvider(client=mocked_client).get_city_aqi(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.value is None


def test_cpcb_provider_failure_uses_stale_verified_data(monkeypatch):
    configure_test_key(monkeypatch, "DATA_GOV_API_KEY")
    responses = [httpx.Response(200, json=cpcb_payload()), httpx.Response(503)]
    cache = TTLCache(ttl_seconds=0, max_stale_seconds=60)

    async def scenario():
        async with make_client(lambda request: responses.pop(0)) as mocked_client:
            provider = AQIProvider(client=mocked_client, cache=cache)
            await provider.get_city_aqi(get_city("varanasi"))
            return await provider.get_city_aqi(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.STALE
    assert result.value == 82
    assert not result.is_live


@pytest.mark.parametrize(
    ("city_slug", "city_name", "latitude"),
    [
        ("varanasi", "Varanasi", "25.32"),
        ("shahjahanpur", "Shahjahanpur", "27.88"),
    ],
)
def test_open_meteo_geocodes_city_and_returns_seven_day_model_forecast(
    city_slug, city_name, latitude
):
    requested_paths = []

    def handler(request):
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=geocoding_payload(city_name))
        assert request.url.params["forecast_days"] == "7"
        assert request.url.params["latitude"] == latitude
        return httpx.Response(200, json=open_meteo_payload())

    async def scenario():
        async with make_client(handler) as mocked_client:
            provider = WeatherProvider(client=mocked_client)
            return await provider.get_city_weather(get_city(city_slug))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.LIVE
    assert result.city == city_name
    assert result.data_type == DataKind.FORECAST_DATA
    assert result.model_based is True
    assert result.source.startswith("Open-Meteo")
    assert result.current.temperature == 17.2
    assert result.current.humidity == 79
    assert result.current.wind_speed == 4.7
    assert result.current.precipitation == 0
    assert len(result.forecast) == 7
    assert result.forecast_units["precipitation_sum"] == "mm"
    assert requested_paths == ["/v1/search", "/v1/forecast"]


def test_open_meteo_fallback_is_used_when_imd_fetcher_fails():
    async def failing_imd(city):
        raise ProviderError("IMD unavailable")

    def handler(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=geocoding_payload())
        return httpx.Response(200, json=open_meteo_payload())

    async def scenario():
        async with make_client(handler) as mocked_client:
            provider = WeatherProvider(client=mocked_client, imd_fetcher=failing_imd)
            return await provider.get_city_weather(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.LIVE
    assert result.source.startswith("Open-Meteo")
    assert "IMD request failed" in result.message
    assert "not a direct observation" in result.message


def test_open_meteo_rejects_wrong_city_or_malformed_weather():
    async def run_with(handler):
        async with make_client(handler) as mocked_client:
            return await WeatherProvider(client=mocked_client).get_city_weather(
                get_city("varanasi")
            )

    wrong_city = run_async(
        run_with(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Varanasi",
                            "country_code": "IN",
                            "admin1": "Odisha",
                            "latitude": 18,
                            "longitude": 83,
                        }
                    ]
                },
            )
        )
    )
    malformed_weather = run_async(
        run_with(
            lambda request: httpx.Response(
                200,
                json=geocoding_payload()
                if request.url.path.endswith("/search")
                else {"current": {}, "daily": {"time": []}},
            )
        )
    )

    assert wrong_city.status == LiveDataStatus.DATA_UNAVAILABLE
    assert wrong_city.current is None
    assert malformed_weather.status == LiveDataStatus.DATA_UNAVAILABLE
    assert malformed_weather.current is None


def test_open_meteo_failure_returns_stale_last_verified_data():
    cache = TTLCache(ttl_seconds=0, max_stale_seconds=60)
    call = {"count": 0}

    def handler(request):
        call["count"] += 1
        if call["count"] == 1 and request.url.path.endswith("/search"):
            return httpx.Response(200, json=geocoding_payload())
        if call["count"] == 2:
            return httpx.Response(200, json=open_meteo_payload())
        return httpx.Response(503)

    async def scenario():
        async with make_client(handler) as mocked_client:
            provider = WeatherProvider(client=mocked_client, cache=cache)
            await provider.get_city_weather(get_city("varanasi"))
            return await provider.get_city_weather(get_city("varanasi"))

    result = run_async(scenario())

    assert result.status == LiveDataStatus.STALE
    assert result.current.temperature == 17.2
    assert result.is_live is False


def test_missing_google_key_does_not_make_route_request(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    calls = []

    async def scenario():
        async with make_client(lambda request: calls.append(request)) as mocked_client:
            provider = TrafficProvider(client=mocked_client)
            return await provider.get_route(
                RouteRequest(origin="Varanasi Junction", destination="Airport")
            )

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.duration is None
    assert result.static_duration is None
    assert result.route_level_only is True
    assert calls == []


def test_google_routes_requests_traffic_aware_and_returns_documented_durations(monkeypatch):
    configure_test_key(monkeypatch, "GOOGLE_MAPS_API_KEY")
    captured = {}

    def handler(request):
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "distanceMeters": 8722,
                        "duration": "1034s",
                        "staticDuration": "800s",
                    }
                ]
            },
        )

    async def scenario():
        async with make_client(handler) as mocked_client:
            provider = TrafficProvider(client=mocked_client)
            return await provider.get_route(
                RouteRequest(
                    origin="Varanasi Junction",
                    destination="Lal Bahadur Shastri Airport",
                    city_slug="varanasi",
                )
            )

    result = run_async(scenario())

    assert result.status == LiveDataStatus.LIVE
    assert result.distance_meters == 8722
    assert result.duration == "1034s"
    assert result.static_duration == "800s"
    assert result.model_dump(by_alias=True)["distanceMeters"] == 8722
    assert result.model_dump(by_alias=True)["staticDuration"] == "800s"
    assert captured["payload"]["routingPreference"] == "TRAFFIC_AWARE"
    assert captured["headers"]["X-Goog-FieldMask"] == (
        "routes.distanceMeters,routes.duration,routes.staticDuration"
    )
    assert result.route_level_only is True


@pytest.mark.parametrize(
    ("status_code", "provider_status", "expected_message"),
    [
        (400, "INVALID_ARGUMENT", "valid"),
        (403, "PERMISSION_DENIED", "billing"),
        (429, "RESOURCE_EXHAUSTED", "quota"),
        (503, "UNAVAILABLE", "temporarily unavailable"),
    ],
)
def test_google_routes_http_errors_are_classified(
    monkeypatch,
    status_code,
    provider_status,
    expected_message,
):
    configure_test_key(monkeypatch, "GOOGLE_MAPS_API_KEY")

    async def scenario():
        async with make_client(
            lambda request: httpx.Response(
                status_code,
                json={"error": {"status": provider_status}},
            )
        ) as mocked_client:
            return await TrafficProvider(client=mocked_client).get_route(
                RouteRequest(origin="Origin Place", destination="Destination Place")
            )

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.distance_meters is None
    assert result.duration is None
    assert expected_message in result.message


def test_google_routes_network_failure_returns_no_route_values(monkeypatch):
    configure_test_key(monkeypatch, "GOOGLE_MAPS_API_KEY")

    def handler(request):
        raise httpx.ConnectError("connection failed", request=request)

    async def scenario():
        async with make_client(handler) as mocked_client:
            return await TrafficProvider(client=mocked_client).get_route(
                RouteRequest(origin="Origin Place", destination="Destination Place")
            )

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.distance_meters is None
    assert result.duration is None
    assert "network" in result.message


def test_google_routes_rejects_malformed_response(monkeypatch):
    configure_test_key(monkeypatch, "GOOGLE_MAPS_API_KEY")

    async def scenario():
        async with make_client(
            lambda request: httpx.Response(200, json={"routes": [{"duration": "invalid"}]})
        ) as mocked_client:
            return await TrafficProvider(client=mocked_client).get_route(
                RouteRequest(origin="Start", destination="Finish")
            )

    result = run_async(scenario())

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.duration is None
    assert result.static_duration is None


def test_energy_never_substitutes_demo_values():
    result = run_async(EnergyProvider.get_city_energy(get_city("shahjahanpur")))

    assert result.status == LiveDataStatus.DATA_UNAVAILABLE
    assert result.value is None
    assert result.source is None
    assert result.data_type == DataKind.OBSERVED_DATA


def test_live_api_endpoints_and_invalid_city_without_external_requests(monkeypatch):
    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    cities = client.get("/api/live/cities")
    status_response = client.get("/api/live/status")
    aqi = client.get("/api/live/varanasi/aqi")
    route = client.post(
        "/api/live/traffic/route",
        json={"origin": "Varanasi Junction", "destination": "Airport"},
    )
    invalid_city = client.get("/api/live/unknown/aqi")
    invalid_route = client.post(
        "/api/live/traffic/route",
        json={"origin": "Start", "destination": "Finish", "city_slug": "unknown"},
    )

    assert cities.status_code == 200
    assert [city["slug"] for city in cities.json()] == ["varanasi", "shahjahanpur"]
    assert status_response.status_code == 200
    assert status_response.json()["api_status"] == "ONLINE"
    assert aqi.status_code == 200
    assert aqi.json()["status"] == "DATA_UNAVAILABLE"
    assert aqi.json()["value"] is None
    assert route.status_code == 200
    assert route.json()["status"] == "DATA_UNAVAILABLE"
    assert invalid_city.status_code == 404
    assert invalid_route.status_code == 422


def test_route_endpoint_serializes_google_eta_fields(monkeypatch):
    async def fake_route(request):
        return RouteTrafficResponse(
            city="Varanasi",
            city_slug=request.city_slug,
            status=LiveDataStatus.LIVE,
            origin=request.origin,
            destination=request.destination,
            distance_meters=8722,
            duration="1034s",
            static_duration="800s",
            source="Google Maps Routes API",
            fetched_at=datetime.now(timezone.utc),
            is_live=True,
            message="Route-level traffic-aware ETA.",
        )

    monkeypatch.setattr(main_module.live_data, "get_traffic_route", fake_route)
    response = client.post(
        "/api/live/traffic/route",
        json={
            "city_slug": "varanasi",
            "origin": "Varanasi Junction",
            "destination": "Lanka, Varanasi",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "LIVE"
    assert result["distanceMeters"] == 8722
    assert result["duration"] == "1034s"
    assert result["staticDuration"] == "800s"
    assert result["source"] == "Google Maps Routes API"
    assert result["fetched_at"] is not None
    assert result["route_level_only"] is True


def test_live_weather_endpoint_uses_provider_response(monkeypatch):
    async def fake_weather(city):
        return WeatherResponse(
            city=city.name,
            city_slug=city.slug,
            status=LiveDataStatus.LIVE,
            source="Open-Meteo (mocked test provider)",
            is_live=True,
            data_type=DataKind.FORECAST_DATA,
            message="Mock response for endpoint test.",
        )

    monkeypatch.setattr(main_module.live_data, "get_weather", fake_weather)
    response = client.get("/api/live/shahjahanpur/weather")

    assert response.status_code == 200
    assert response.json()["city"] == "Shahjahanpur"
    assert response.json()["status"] == "LIVE"
    assert response.json()["data_type"] == "FORECAST_DATA"


def test_live_overview_endpoint_serializes_each_data_source(monkeypatch):
    async def fake_overview(city):
        return {
            "city": {
                "slug": city.slug,
                "name": city.name,
                "state": city.state,
                "country": city.country,
                "country_code": city.country_code,
            },
            "status": "PARTIAL",
            "fetched_at": "2026-11-26T17:00:00Z",
            "aqi": {
                "city": city.name,
                "city_slug": city.slug,
                "metric": "aqi",
                "status": "DATA_UNAVAILABLE",
                "value": None,
                "unit": None,
                "source": None,
                "station": None,
                "observed_at": None,
                "fetched_at": None,
                "is_live": False,
                "data_type": "OBSERVED_DATA",
                "message": "No configured key.",
            },
            "weather": {
                "city": city.name,
                "city_slug": city.slug,
                "status": "LIVE",
                "source": "Open-Meteo",
                "fetched_at": "2026-11-26T17:00:00Z",
                "is_live": True,
                "data_type": "FORECAST_DATA",
                "model_based": True,
                "current": None,
                "forecast": [],
            },
            "energy": {
                "city": city.name,
                "city_slug": city.slug,
                "metric": "energy",
                "status": "DATA_UNAVAILABLE",
                "value": None,
                "source": None,
                "is_live": False,
                "data_type": "OBSERVED_DATA",
                "message": "No authorized source.",
            },
            "traffic": {
                "city": city.name,
                "city_slug": city.slug,
                "metric": "traffic",
                "status": "DATA_UNAVAILABLE",
                "value": None,
                "source": None,
                "is_live": False,
                "data_type": "OBSERVED_DATA",
                "message": "No city-wide feed.",
            },
        }

    monkeypatch.setattr(main_module.live_data, "get_overview", fake_overview)
    response = client.get("/api/live/varanasi/overview")

    assert response.status_code == 200
    assert response.json()["city"]["name"] == "Varanasi"
    assert response.json()["aqi"]["value"] is None
    assert response.json()["weather"]["data_type"] == "FORECAST_DATA"
    assert response.json()["energy"]["status"] == "DATA_UNAVAILABLE"


def test_frontend_has_separate_live_mode_and_provider_panels():
    html = client.get("/").text
    script = client.get("/app.js").text

    assert 'id="live-mode-button"' in html
    assert 'id="demo-mode-content"' in html
    assert 'id="live-aqi"' in html
    assert 'id="live-weather"' in html
    assert 'id="live-energy"' in html
    assert 'id="live-city-traffic"' in html
    assert 'id="route-form"' in html
    assert "/api/live/cities" in script
    assert "/api/live/status" in script
    assert "/api/live/traffic/route" in script
    assert "distanceMeters" in script
    assert "Estimated travel duration (traffic-aware)" in script
    assert "Static duration" in script
    assert "Route-level only, not city-wide traffic" in script
    assert "GOOGLE_MAPS_API_KEY" not in script


def test_normalizer_rejects_invalid_timestamp_and_aqi_values():
    payload = cpcb_payload()
    payload["records"][0]["aqi"] = "9999"
    payload["records"][0]["observed_at"] = "2026-99-99T99:99:99Z"

    observations, _ = normalize_cpcb_payload(payload, get_city("varanasi"))

    assert observations[0].aqi is None
    assert observations[0].observed_at is None