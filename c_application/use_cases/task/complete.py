from datetime import datetime

from a_core import IdPrefix
from a_core.exceptions import ValidationException
from b_domain.entities import Task, TimeEntry
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import TaskId, UserId
from c_application.dtos.task_dtos import CompleteTaskOutputDTO, TaskByUserRequest
from c_application.mappers.task_mapper import TaskMapper


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

        now: datetime = request.completed_at or self.clock.now()

        async with self.uow as uow:
            # 1. Resolve the task by prefix
            try:
                task: Task = await self._resolve_task(uow, task_id_prefix, user_id)
            except ValueError as e:
                raise ValidationException(e) from e

            # 2. Close active timers and compute actual duration
            actual_duration: int = await self._close_active_timers(
                uow, task, now, request
            )

            # 3. Domain action: mark task as done (emits TaskCompletedEvent internally)
            task.mark_as_done(now, actual_minutes=actual_duration)

            # 4. Persist changes
            await uow.tasks.update(task)

            # Next occurrence will be generated asynchronously
            # by CreateRecurringTaskHandler
            return self._build_response(task, None, now)

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

    @staticmethod
    async def _close_active_timers(
        uow: UnitOfWork, task: Task, now: datetime, request: TaskByUserRequest
    ) -> int:
        """Close active timers for a task and compute actual duration.

        Args:
            task (Task): Task entity.
            now (datetime): Current time.
            request (TaskByUserRequest): Request containing completion time.

        Returns:
            int: Total elapsed minutes from timers.
        """

        active_timers: list[TimeEntry] = await uow.time_entries.get_actives_for_task(
            task.id
        )
        if not active_timers:
            return 0

        actual_duration: int = 0
        effective_now: datetime = request.completed_at or now

        for timer in active_timers:
            timer.stop(effective_now)
            actual_duration += timer.elapsed_minutes(effective_now)

        await uow.time_entries.update_all(active_timers)
        return actual_duration

    @staticmethod
    def _build_response(
        task: Task, next_task: Task | None, now: datetime
    ) -> CompleteTaskOutputDTO:
        """Build output DTO for completed task."""
        return CompleteTaskOutputDTO(
            completed_task=TaskMapper.to_output(task, now),
            next_occurrence=TaskMapper.to_output(next_task, now) if next_task else None,
        )
