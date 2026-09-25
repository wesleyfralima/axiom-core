from datetime import datetime

import pytest

from b_domain.entities import Task
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.ports.unit_of_work import UowFactoryType
from b_domain.value_objects import RecurrenceInterval, Title, UserId
from b_domain.value_objects.dates import AxiomDate
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity
from b_domain.value_objects.recurrences import SimpleIntervalRule
from c_application.handlers.task_handlers.create_recurring_task_handler import (
    CreateRecurringTaskHandler,
)

pytestmark = pytest.mark.asyncio

DUE = datetime(2026, 1, 1, 9, 0)
TZ = "America/Sao_Paulo"


def _daily_task(estimate: int, average: int) -> Task:
    task = Task.create(
        now=DUE,
        user_id=UserId(),
        title=Title("Treino"),
        due_date=DUE,
        is_floating=True,
        tz_name=TZ,
        recurrence=SimpleIntervalRule(
            start_date=AxiomDate.floating(DUE, TZ),
            frequency=RecurrenceInterval.DAILY,
        ),
        estimated_duration_minutes=estimate,
        complexity=TaskComplexity.LOW,
        required_energy_level=EnergyLevel.HIGH,
    )
    task.average_duration_minutes = average
    return task


async def _complete(uow_factory: UowFactoryType, task: Task) -> Task:
    async with uow_factory() as uow:
        await uow.tasks.add(task)

    event = TaskCompletedEvent(
        task_id=task.id,
        user_id=task.user_id,
        estimated_minutes=task.estimated_duration_minutes,
        actual_minutes=0,
        energy_level_used=task.required_energy_level,
        task_complexity=task.complexity,
        occurred_at=datetime(2026, 1, 1, 10, 0),
    )
    await CreateRecurringTaskHandler(uow_factory()).handle(event)

    async with uow_factory() as uow:
        tasks = [t for t in uow.tasks.tasks.values() if t.id != task.id]
    assert len(tasks) == 1
    return tasks[0]


async def test_without_measured_average_the_estimate_carries_over(
    fake_uow_factory: UowFactoryType,
) -> None:
    next_task = await _complete(fake_uow_factory, _daily_task(45, average=0))

    assert next_task.estimated_duration_minutes == 45
    assert next_task.complexity is TaskComplexity.LOW
    assert next_task.required_energy_level is EnergyLevel.HIGH


async def test_measured_average_becomes_the_estimate(
    fake_uow_factory: UowFactoryType,
) -> None:
    next_task = await _complete(fake_uow_factory, _daily_task(45, average=52))

    assert next_task.estimated_duration_minutes == 52
