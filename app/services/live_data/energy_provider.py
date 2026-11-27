from app.services.live_data.base import LiveProvider
from app.services.live_data.city_registry import City
from app.services.live_data.schemas import DataKind, LiveDataStatus, LiveMetricResponse


class EnergyProvider(LiveProvider):
    @property
    def configured(self) -> bool:
        return False

    @staticmethod
    async def get_city_energy(city: City) -> LiveMetricResponse:
        return LiveMetricResponse(
            city=city.name,
            city_slug=city.slug,
            metric="energy",
            status=LiveDataStatus.DATA_UNAVAILABLE,
            source=None,
            is_live=False,
            data_type=DataKind.OBSERVED_DATA,
            message="No authorized utility or smart-meter data source is configured.",
        )
