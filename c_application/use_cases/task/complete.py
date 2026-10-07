from dataclasses import replace
from datetime import UTC, datetime

from a_core import IdPrefix
from a_core.exceptions import ValidationException
from b_domain.entities import Context, Task, TimeEntry, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskId, UserId
from c_application.dtos.task_dtos import (
    CompleteTaskOutputDTO,
    TaskByUserRequest,
)
from c_application.mappers.task_mapper import TaskMapper
from c_application.use_cases.task.relations import (
    is_open,
    link,
    refuse_while_waiting,
    subtasks_of,
)
from c_application.use_cases.task.timer import time_of
from c_application.utils.date_input import (
    local_instant,
    local_today,
    resolve_date_input,
)


class CompleteTaskUseCase(UseCase[TaskByUserRequest, CompleteTaskOutputDTO]):
    """Use case for completing a Task with support for partial ID matching.

    Responsibilities:
      - Identify the correct task by ID prefix.
      - Close active timers and compute actual duration.
      - Mark the task as completed (generating a TaskCompletedEvent).
      - Persist changes atomically via UnitOfWork.

    Side effects such as metrics aggregation, learning, recurrence,
    and dependency unlocking are delegated to event handlers.
    """

    async def execute(self, request: TaskByUserRequest) -> CompleteTaskOutputDTO:
        """Execute the task completion workflow.

        Args:
            request (TaskByUserRequest): Input containing user ID and task prefix.

        Returns:
            CompleteTaskOutputDTO: DTO with details of the completed task.
        """

        # Fail fast: UX safeguard
        try:
            task_id_prefix: IdPrefix = IdPrefix(request.task_id_prefix)
            user_id: UserId = UserId.from_string(
                request.user_id, error_msg="Invalid user ID."
            )
        except ValidationException as e:
            raise ValidationException(e) from e

        async with self.uow as uow:
            # When it was done: now, or a moment the user typed (done and
            # forgotten)
            now: datetime = await self._moment(uow, request, user_id)

            # 1. Resolve the task by prefix
            try:
                task: Task = await self._resolve_task(uow, task_id_prefix, user_id)
            except ValueError as e:
                raise ValidationException(e) from e

            # A dependency the user set is never ignored: not this task, nor
            # a parent whose open subtask waits
            subtasks: list[Task] = await subtasks_of(uow, task)
            await refuse_while_waiting(uow, task, subtasks, user_id)

            # 2. Close active timers and compute actual duration
            actual_duration: int = await self._close_active_timers(uow, task, now)

            # 3. Domain action: mark task as done (emits TaskCompletedEvent internally)
            task.mark_as_done(now, actual_minutes=actual_duration)
            # A measured time: the running average (the next occurrence's
            # estimate) learns from it
            task.record_duration(actual_duration)

            # 4. Persist changes
            await uow.tasks.update(task)

            # 5. Its open subtasks are done with it, at the same time (linked
            # to its completion, so undo takes them back together)
            done_below: int = 0
            completion = task.peek_events()[-1].id
            for sub in reversed(subtasks):
                if not is_open(sub):
                    continue
                minutes: int = await self._close_active_timers(uow, sub, now)
                sub.mark_as_done(now, actual_minutes=minutes, caused_by=completion)
                sub.record_duration(minutes)
                await uow.tasks.update(sub)
                done_below += 1

            context = (
                await uow.contexts.get_by_id(task.context_id, user_id)
                if task.context_id
                else None
            )

            # The last open subtask: its parent may be done too (the user
            # says so; a parent without open subtasks is fine)
            parent: Task | None = (
                await uow.tasks.get_by_id(task.parent_id, user_id)
                if task.parent_id
                else None
            )
            ready: bool = (
                parent is not None
                and is_open(parent)
                and not any(
                    is_open(sibling)
                    for sibling in await uow.tasks.get_subtasks(parent.id, limit=10_000)
                    if sibling.id != task.id
                )
            )

            # Next occurrence will be generated asynchronously
            # by CreateRecurringTaskHandler
            return replace(
                self._build_response(task, None, now, context),
                subtasks_done=done_below,
                parent_ready=link(parent) if parent is not None and ready else None,
            )

    @staticmethod
    async def _resolve_task(uow: UnitOfWork, prefix: IdPrefix, user_id: UserId) -> Task:
        """Resolve a task by ID prefix and validate its state for completion.

        Args:
            uow (UnitOfWork): UnitOfWork used to resolve the task.
            prefix (IdPrefix): Prefix used to resolve the task.
            user_id (UserId): User ID used to resolve the task.

        Raises:
            ValidationException: If no task or multiple ambiguous tasks are found.
        """

        # Despite going twice to the database, this method is correct and safe

        id_iterable: list[IdPrefix] = [prefix]
        ids_found: list[TaskId] = await uow.tasks.task_ids_from_id_prefixes(id_iterable)

        if not ids_found:
            raise ValidationException(f"No task found with ID prefix '{prefix}'.")
        if len(ids_found) > 1:
            raise ValidationException(
                f"Ambiguous ID prefix '{prefix}': it matches {len(ids_found)} tasks."
            )

        task_found: Task | None = await uow.tasks.get_by_id(
            task_id=ids_found[0],
            user_id=user_id,
        )

        if not task_found:
            raise ValidationException("No task found with ID prefix")

        return task_found

    async def _moment(
        self, uow: UnitOfWork, request: TaskByUserRequest, user_id: UserId
    ) -> datetime:
        """When the task was done: now, or ``completed_at`` as typed, a
        wall-clock time where the user is.

        Raises:
            ValidationException: If the moment has no time of day or is in
                the future.
            InvalidValueError: If it is not a date the user can type.
        """
        now: datetime = self.clock.now()
        if request.completed_at is None:
            return now
        user: User | None = await uow.users.get_by_id(user_id)
        prefs: UserPrefs = user.preferences if user else UserPrefs()
        resolved = resolve_date_input(
            request.completed_at, today=local_today(now, prefs.timezone)
        )
        if not isinstance(resolved, datetime):
            raise ValidationException(
                "When it was done needs a time of day, e.g. 'yesterday 21:00'."
            )
        moment: datetime = local_instant(resolved, prefs.timezone)
        if moment > (now if now.tzinfo else now.replace(tzinfo=UTC)):
            raise ValidationException("A task cannot be done in the future.")
        return moment

    @staticmethod
    async def _close_active_timers(uow: UnitOfWork, task: Task, now: datetime) -> int:
        """Close active timers for a task and compute actual duration.

        Args:
            task (Task): Task entity.
            now (datetime): When it was done.

        Returns:
            int: Minutes spent on the task: every session, the ones just
            closed included.

        Raises:
            ValidationException: If a timer started after ``now`` (its session
                would end before it began).
        """

        active_timers: list[TimeEntry] = await uow.time_entries.get_actives_for_task(
            task.id
        )
        for timer in active_timers:
            started: datetime = timer.start_time
            if (started if started.tzinfo else started.replace(tzinfo=UTC)) > now:
                raise ValidationException(
                    f"'{task.title}' has a timer that started after that: "
                    "it was done later, or pause it first."
                )
            timer.stop(now)
        if active_timers:
            await uow.time_entries.update_all(active_timers)

        # Every session counts, the paused ones too (not only the running one)
        spent, _ = await time_of(uow, task.id, now)
        return spent

    @staticmethod
    def _build_response(
        task: Task, next_task: Task | None, now: datetime, context: Context | None
    ) -> CompleteTaskOutputDTO:
        """Build output DTO for completed task."""
        return CompleteTaskOutputDTO(
            completed_task=TaskMapper.to_output(task, now, context=context),
            next_occurrence=(
                TaskMapper.to_output(next_task, now, context=context)
                if next_task
                else None
            ),
        )
