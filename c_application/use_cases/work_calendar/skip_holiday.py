from dataclasses import dataclass
from datetime import date, timedelta

from a_core import DTO
from a_core.exceptions import ValidationException
from a_core.text import fold
from b_domain.entities import User
from b_domain.ports.use_case import UseCase
from c_application.dtos.calendar_dtos import HolidaySkippedOutputDTO
from c_application.use_cases.context._common import load_user, parse_user_id
from c_application.utils.date_input import local_today


@dataclass(frozen=True, kw_only=True)
class SkipHolidayInputDTO(DTO):
    """Request to skip one of the region's holidays every year, or undo that.

    Attributes:
        user_id (str): The user.
        name (str): The holiday's name as the provider has it, or a part of
            it ("corpus"). Case and accents don't matter.
        skip (bool): Skip it (True) or count it again (False).
    """

    user_id: str
    name: str
    skip: bool = True


class SkipHolidayUseCase(UseCase[SkipHolidayInputDTO, HolidaySkippedOutputDTO]):
    """Work on one of the region's holidays every year, found by its name.

    A moveable holiday changes date each year, so a yearly working day (by
    date) cannot cover it; skipping it by name can.
    """

    async def execute(self, request: SkipHolidayInputDTO) -> HolidaySkippedOutputDTO:
        """Skip the holiday, or count it again.

        Raises:
            ValidationException: If the user ID is invalid, there is no
                holiday region, or the name matches no holiday (or several).
            EntityNotFound: If the user does not exist.
        """
        user_id = parse_user_id(request.user_id)
        wanted: str = fold(request.name)
        if not wanted:
            raise ValidationException("Which holiday? Give its name.")

        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            prefs = user.preferences
            today: date = local_today(self.clock.now(), prefs.timezone)
            skipped: list[str] = [
                n.strip() for n in prefs.skipped_holidays.split(";") if n.strip()
            ]

            if request.skip:
                if not prefs.holiday_region:
                    raise ValidationException(
                        "No holiday region yet: set one first (holiday_region)."
                    )
                # The next year of holidays, by name (a name may fall twice)
                upcoming: dict[str, date] = {}
                for year in (today.year, today.year + 1):
                    for day, holiday in sorted(
                        uow.holidays.holidays(prefs.holiday_region, year).items()
                    ):
                        if today <= day <= today + timedelta(days=366):
                            upcoming.setdefault(holiday, day)
                name: str = _one(wanted, list(upcoming), request.name, "holiday")
                next_date: date | None = upcoming[name]
                if fold(name) not in {fold(n) for n in skipped}:
                    skipped.append(name)
            else:
                name = _one(wanted, skipped, request.name, "skipped holiday")
                next_date = None
                skipped = [n for n in skipped if n != name]

            user.update_prefs(now=self.clock.now(), skipped_holidays="; ".join(skipped))
            await uow.users.update(user)

        return HolidaySkippedOutputDTO(
            name=name,
            skipped=request.skip,
            next_date=next_date.isoformat() if next_date else None,
            skipped_holidays=skipped,
        )


def _one(wanted: str, names: list[str], typed: str, what: str) -> str:
    """The one name that is ``wanted``, or the only one that contains it.

    Raises:
        ValidationException: If none or several match.
    """
    exact: list[str] = [n for n in names if fold(n) == wanted]
    if exact:
        return exact[0]
    containing: list[str] = [n for n in names if wanted in fold(n)]
    if len(containing) == 1:
        return containing[0]
    if not containing:
        raise ValidationException(f"No {what} is called '{typed}'.")
    raise ValidationException(
        f"'{typed}' could be {', '.join(sorted(containing))}: say which."
    )
