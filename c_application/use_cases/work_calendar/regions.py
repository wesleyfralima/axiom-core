from dataclasses import dataclass

from a_core import DTO
from b_domain.entities import User
from b_domain.ports.use_case import UseCase
from b_domain.value_objects.work_calendar import HolidayRegion
from c_application.dtos.calendar_dtos import (
    HolidayRegionOutputDTO,
    HolidayRegionsOutputDTO,
)
from c_application.use_cases.context._common import load_user, parse_user_id
from c_application.utils.holiday_regions import find_regions


@dataclass(frozen=True, kw_only=True)
class ListHolidayRegionsInputDTO(DTO):
    """Request for the regions whose holidays are known.

    Attributes:
        user_id (str): The user (to mark their region).
        query (str | None): None for every country; a country's code (``BR``)
            for its subdivisions; else a search by code or name (``bra``,
            ``Brasil``, ``br-paulo``).
    """

    user_id: str
    query: str | None = None


class ListHolidayRegionsUseCase(
    UseCase[ListHolidayRegionsInputDTO, HolidayRegionsOutputDTO]
):
    """The regions to choose ``holiday_region`` from."""

    async def execute(
        self, request: ListHolidayRegionsInputDTO
    ) -> HolidayRegionsOutputDTO:
        """List every country, a country's subdivisions, or a search.

        Raises:
            ValidationException: If the user ID is invalid.
            EntityNotFound: If the user does not exist.
        """
        user_id = parse_user_id(request.user_id)
        query: str | None = (request.query or "").strip() or None
        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            provider = uow.holidays

            country: HolidayRegion | None = None
            regions: list[HolidayRegion]
            if query is None:
                regions = provider.regions()
            else:
                country = next(
                    (r for r in provider.regions() if r.code == query.upper()), None
                )
                regions = (
                    provider.regions(country.code)
                    if country is not None
                    else find_regions(provider, query)
                )

        return HolidayRegionsOutputDTO(
            query=query,
            country=_output(country) if country else None,
            regions=[_output(r) for r in regions],
            current_region=user.preferences.holiday_region,
        )


def _output(region: HolidayRegion) -> HolidayRegionOutputDTO:
    return HolidayRegionOutputDTO(code=region.code, name=region.name)
