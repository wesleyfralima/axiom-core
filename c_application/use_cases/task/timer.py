"""Timers: `task start` and `task pause` — one thing at a time."""

from dataclasses import dataclass
from datetime import datetime

from a_core import DTO
from b_domain.entities import Task, TimeEntry
from b_domain.ports.repositories.filters import TimeEntryFilter
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskId, TaskStatus, UserId
from c_application.dtos import TaskOutputDTO
from c_application.dtos.task_dtos import TaskByUserRequest
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils.task_utils import find_task


@dataclass(frozen=True, kw_only=True)
class TaskTimerOutputDTO(DTO):
    """A timer started or stopped.

    Attributes:
        task (TaskOutputDTO): The task, with its time.
        session_minutes (int | None): The session that just ended (pause).
        paused_other (str | None): The task that was running and got paused
            to make room (start: one thing at a time).
    """

    task: TaskOutputDTO
    session_minutes: int | None = None
    paused_other: str | None = None


class StartTaskUseCase(UseCase[TaskByUserRequest, TaskTimerOutputDTO]):
    """Start working on a task: a timer runs, and whatever was running pauses."""

    async def execute(self, request: TaskByUserRequest) -> TaskTimerOutputDTO:
        """Start the task.

        Raises:
            ValidationException: If the user ID or the prefix is invalid.
            EntityNotFound: If the user has no such task.
            InvalidStateTransition: If it cannot start (closed, waiting on
                other tasks, already in progress).
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            task.start(now)  # first: nothing else changes if it cannot start
            started = task.peek_events()[-1]

            paused_other: str | None = None
            running: TimeEntry | None = await uow.time_entries.get_active_for_user(
                user_id
            )
            if running is not None and running.task_id != task.id:
                minutes: int = running.elapsed_minutes(now)
                running.stop(now)
                await uow.time_entries.update(running)
                other: Task | None = await uow.tasks.get_by_id(running.task_id, user_id)
                if other is not None and other.status == TaskStatus.IN_PROGRESS:
                    other.pause(now, minutes, caused_by=started.id)
                    await uow.tasks.update(other)
                    paused_other = str(other.title)

            await uow.time_entries.add(
                TimeEntry(task_id=task.id, user_id=user_id, start_time=now)
            )
            await uow.tasks.update(task)
            return TaskTimerOutputDTO(
                task=await _output(uow, task, user_id, now),
                paused_other=paused_other,
            )


class PauseTaskUseCase(UseCase[TaskByUserRequest, TaskTimerOutputDTO]):
    """Stop working on a task for now: its timer stops."""

    async def execute(self, request: TaskByUserRequest) -> TaskTimerOutputDTO:
        """Pause the task.

        Raises:
            ValidationException: If the user ID or the prefix is invalid.
            EntityNotFound: If the user has no such task.
            InvalidStateTransition: If it is not in progress.
        """
        user_id: UserId = UserId.from_string(
            request.user_id, error_msg="Invalid user ID."
        )
        now: datetime = self.clock.now()

        async with self.uow as uow:
            task: Task = await find_task(uow, request.task_id_prefix, user_id)
            running: list[TimeEntry] = await uow.time_entries.get_actives_for_task(
                task.id
            )
            minutes: int = sum(e.elapsed_minutes(now) for e in running)
            task.pause(now, minutes)
            for entry in running:
                entry.stop(now)
            if running:
                await uow.time_entries.update_all(running)
            await uow.tasks.update(task)
            return TaskTimerOutputDTO(
                task=await _output(uow, task, user_id, now), session_minutes=minutes
            )


async def time_of(
    uow: UnitOfWork, task_id: TaskId, now: datetime
) -> tuple[int, datetime | None]:
    """A task's time: minutes spent so far, and since when a timer runs."""
    entries: list[TimeEntry] = await uow.time_entries.search(
        TimeEntryFilter(task_id=task_id, limit=10_000)
    )
    spent: int = sum(e.elapsed_minutes(now) for e in entries)
    running: list[datetime] = [e.start_time for e in entries if e.end_time is None]
    return spent, max(running) if running else None


async def _output(
    uow: UnitOfWork, task: Task, user_id: UserId, now: datetime
) -> TaskOutputDTO:
    spent, since = await time_of(uow, task.id, now)
    context = (
        await uow.contexts.get_by_id(task.context_id, user_id)
        if task.context_id
        else None
    )
    return TaskMapper.to_output(
        task, now, context=context, time_spent_minutes=spent, running_since=since
    )
