import math
import re
import unicodedata
from datetime import datetime
from typing import Any

from app.services.live_data.base import ProviderError
from app.services.live_data.city_registry import City
from app.services.live_data.schemas import AQIStationObservation, PollutantValues


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks.casefold()).split())


def parse_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or value.casefold() in {"na", "n/a", "null", "-"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if number.is_integer():
        return int(number)
    return number


def parse_aqi(value: Any) -> int | float | None:
    number = parse_number(value)
    return number if number is not None and 0 <= number <= 500 else None


def parse_nonnegative_number(value: Any) -> int | float | None:
    number = parse_number(value)
    return number if number is not None and number >= 0 else None


def parse_coordinate(value: Any, *, minimum: float, maximum: float) -> float | None:
    number = parse_number(value)
    return float(number) if number is not None and minimum <= number <= maximum else None


def parse_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}", candidate):
        return None
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    return candidate


def normalize_cpcb_payload(
    payload: Any,
    city: City,
) -> tuple[list[AQIStationObservation], dict[str, str | int | float | None]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ProviderError("The CPCB response did not contain a records list.")

    records = payload["records"]
    grouped: dict[tuple[str, float | None, float | None], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        state = record.get("state")
        city_name = record.get("city")
        if not isinstance(state, str) or normalize_name(state) != normalize_name(city.state):
            continue
        if not isinstance(city_name, str) or normalize_name(city_name) != normalize_name(city.name):
            continue

        station_value = record.get("station")
        station = station_value.strip() if isinstance(station_value, str) and station_value.strip() else None
        latitude = parse_coordinate(record.get("latitude"), minimum=-90, maximum=90)
        longitude = parse_coordinate(record.get("longitude"), minimum=-180, maximum=180)
        key = (station or "", latitude, longitude)
        group = grouped.setdefault(
            key,
            {
                "station": station,
                "latitude": latitude,
                "longitude": longitude,
                "timestamps": [],
                "aqi_values": [],
                "pollutants": {},
            },
        )

        timestamp = None
        for field in ("observed_at", "last_update", "last_updated", "timestamp", "datetime"):
            timestamp = parse_timestamp(record.get(field))
            if timestamp is not None:
                break
        if timestamp:
            group["timestamps"].append(timestamp)

        aqi_value = None
        for field in ("aqi", "air_quality_index", "air quality index"):
            aqi_value = parse_aqi(record.get(field))
            if aqi_value is not None:
                break
        if aqi_value is not None:
            group["aqi_values"].append(aqi_value)

        pollutant_value = record.get("pollutant_id")
        if isinstance(pollutant_value, str) and pollutant_value.strip():
            pollutant_id = pollutant_value.strip().upper()
            if pollutant_id in {"NA", "N/A", "-"}:
                continue
            group["pollutants"][pollutant_id] = PollutantValues(
                average=parse_nonnegative_number(record.get("pollutant_avg")),
                minimum=parse_nonnegative_number(record.get("pollutant_min")),
                maximum=parse_nonnegative_number(record.get("pollutant_max")),
            )

    observations: list[AQIStationObservation] = []
    for group in grouped.values():
        aqi_values = set(group["aqi_values"])
        aqi = next(iter(aqi_values)) if len(aqi_values) == 1 else None
        timestamps = sorted(group["timestamps"])
        observations.append(
            AQIStationObservation(
                station=group["station"],
                aqi=aqi,
                latitude=group["latitude"],
                longitude=group["longitude"],
                observed_at=timestamps[-1] if timestamps else None,
                pollutants=group["pollutants"],
            )
        )

    metadata: dict[str, str | int | float | None] = {"records_received": len(records)}
    for field in ("title", "version", "created", "updated", "total", "count", "limit", "offset", "updated_date"):
        value = payload.get(field)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            metadata[field] = value
    return observations, metadata
