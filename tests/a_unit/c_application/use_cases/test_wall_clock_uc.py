"""Where the user is now (the unit of work's zone) is where a floating due
date is read: set at 08:00 in São Paulo, it is late after 08:00 in Lisbon.
A fixed one stays the instant it is.

The fake clock says Monday 2026-10-19, 07:30 UTC: 08:30 in Lisbon, 04:30 in
São Paulo. The user's preference is São Paulo.
"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from b_domain.entities import User
from c_application.dtos.task_dtos import CreateTaskInputDTO, GetTaskRequest
from c_application.use_cases import CreateTaskUseCase, GetTaskUseCase
from tests.conftest import FakeClock, FakeUnitOfWork, FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory, fake_clock: FakeClock) -> User:
    created = User.create(username="wesley", email="wesley@test.com")
    created.preferences = replace(created.preferences, timezone="America/Sao_Paulo")
    await fake_uow_factory().users.add(created)
    fake_clock.set_time(datetime(2026, 10, 19, 7, 30, tzinfo=UTC))
    return created


def _in(zone: str, factory: FakeUowFactory, clock: FakeClock) -> UseCaseDeps:
    def where(trigger_relay: bool = False) -> FakeUnitOfWork:
        uow = factory(trigger_relay)
        uow.timezone = zone
        return uow

    return {"uow_factory": where, "clock": clock}


async def test_floating_is_the_hour_where_you_are_fixed_the_instant(
    fake_uow_factory: FakeUowFactory, fake_clock: FakeClock, user: User
) -> None:
    in_sp = _in("America/Sao_Paulo", fake_uow_factory, fake_clock)
    in_lisbon = _in("Europe/Lisbon", fake_uow_factory, fake_clock)
    create = CreateTaskUseCase(**in_sp)
    wake = await create.execute(
        CreateTaskInputDTO(
            user_id=str(user.id),
            title="Wake up",
            due_date="2026-10-19 08:00",
            strict_due=True,
        )
    )
    call = await create.execute(
        CreateTaskInputDTO(
            user_id=str(user.id),
            title="Call",
            due_date="2026-10-19 08:00",
            is_floating=False,
            strict_due=True,
        )
    )

    async def shown(deps: UseCaseDeps, task_id: str) -> tuple[bool, datetime | None]:
        got = await GetTaskUseCase(**deps).execute(
            GetTaskRequest(user_id=str(user.id), task_id_prefix=task_id[:8])
        )
        return got.is_overdue, got.deadline

    # In São Paulo it is 04:30: neither is late
    assert (await shown(in_sp, wake.id))[0] is False
    assert (await shown(in_sp, call.id))[0] is False
    # In Lisbon it is 08:30: the alarm went off at 08:00 there; the call is
    # at 08:00 in São Paulo, 12:00 in Lisbon
    late, deadline = await shown(in_lisbon, wake.id)
    assert late is True
    assert deadline is not None
    assert deadline.astimezone(UTC) == datetime(2026, 10, 19, 7, 0, tzinfo=UTC)
    late, deadline = await shown(in_lisbon, call.id)
    assert late is False
    assert deadline is not None
    assert deadline.astimezone(UTC) == datetime(2026, 10, 19, 11, 0, tzinfo=UTC)
