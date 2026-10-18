"""A floating date is wall-clock time: 06:00 is 06:00 wherever the user is.
A fixed one is an instant: a call at 08:00 in São Paulo is at 12:00 in
Lisbon (product Backlog 05, the owner's rule of 2026-10-17)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from b_domain.entities import Task
from b_domain.value_objects import RecurrenceInterval, Title, UserId
from b_domain.value_objects.dates import (
    AxiomDate,
    DueDate,
    reset_wall_clock_zone,
    set_wall_clock_zone,
    wall_clock_zone,
)
from b_domain.value_objects.recurrences import SimpleIntervalRule

SP = "America/Sao_Paulo"
LISBON = ZoneInfo("Europe/Lisbon")  # UTC+1 in October 2026


@contextmanager
def _in(zone: str | None) -> Iterator[None]:
    token = set_wall_clock_zone(zone)
    try:
        yield
    finally:
        reset_wall_clock_zone(token)


def _lisbon(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 19, hour, minute, tzinfo=LISBON).astimezone(UTC)


def test_a_floating_hour_is_the_same_hour_where_the_user_is() -> None:
    wake_up = DueDate.floating(datetime(2026, 10, 19, 8, 0), source_tz=SP)

    with _in("Europe/Lisbon"):
        assert wake_up.deadline(strict=True) == datetime(
            2026, 10, 19, 8, 0, tzinfo=LISBON
        )
        assert not wake_up.is_overdue(_lisbon(7, 59), strict=True)
        assert wake_up.is_overdue(_lisbon(8, 1), strict=True)
    # Where it was set, without a zone for now: as before
    assert wake_up.deadline(strict=True) == datetime(
        2026, 10, 19, 8, 0, tzinfo=ZoneInfo(SP)
    )


def test_a_fixed_hour_is_the_same_instant_anywhere() -> None:
    call = DueDate.fixed(datetime(2026, 10, 19, 8, 0, tzinfo=ZoneInfo(SP)))

    with _in("Europe/Lisbon"):
        assert call.deadline(strict=True) == datetime(2026, 10, 19, 11, 0, tzinfo=UTC)
        assert not call.is_overdue(_lisbon(9, 0), strict=True)
        assert call.is_overdue(_lisbon(12, 1), strict=True)


def test_a_habit_catches_up_to_where_the_user_is() -> None:
    """06:00 set in São Paulo, done at 07:00 in Lisbon (03:00 in São
    Paulo): today's 06:00 has passed there, so the next is tomorrow's."""
    task = Task.create(
        now=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        user_id=UserId(),
        title=Title("Wake up"),
        due_date=datetime(2026, 10, 18, 6, 0),
        tz_name=SP,
        recurrence=SimpleIntervalRule(
            start_date=AxiomDate.floating(datetime(2026, 10, 18, 6, 0), SP),
            frequency=RecurrenceInterval.DAILY,
            catch_up=True,
        ),
    )

    with _in("Europe/Lisbon"):
        following = task.create_next_occurrence(_lisbon(7, 0))
        upcoming = task.upcoming_occurrences(_lisbon(7, 0), _lisbon(23, 0))

    assert following is not None and following.due_date is not None
    assert following.due_date.value == datetime(2026, 10, 20, 6, 0)
    assert following.due_date.is_floating
    assert upcoming == []  # today's 06:00 is behind, in Lisbon

    # In São Paulo it is 03:00: today's 06:00 is still ahead
    with _in(SP):
        here = task.create_next_occurrence(_lisbon(7, 0))
    assert here is not None and here.due_date is not None
    assert here.due_date.value == datetime(2026, 10, 19, 6, 0)


def test_the_zone_is_only_for_now() -> None:
    assert wall_clock_zone() is None
    with _in("Europe/Lisbon"):
        assert wall_clock_zone() == "Europe/Lisbon"
    assert wall_clock_zone() is None
