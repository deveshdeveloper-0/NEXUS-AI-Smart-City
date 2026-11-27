from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    slug: str
    name: str
    state: str = "Uttar Pradesh"
    country: str = "India"
    country_code: str = "IN"


CITY_REGISTRY = {
    "varanasi": City(slug="varanasi", name="Varanasi"),
    "shahjahanpur": City(slug="shahjahanpur", name="Shahjahanpur"),
}


def get_city(city_slug: str) -> City | None:
    return CITY_REGISTRY.get(city_slug.strip().lower())


def list_cities() -> list[City]:
    return list(CITY_REGISTRY.values())
