from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from a_core.exceptions import ValidationException, InvalidStateTransition
from b_domain.entities import Task, TimeEntry
from b_domain.ports.providers import ClockProvider
from b_domain.ports.unity_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from b_domain.services.user_behavior_learner import UserBehaviorLearner
from b_domain.services.user_behavior_metrics_aggregator import UserBehaviorMetricsAggregator
from b_domain.value_objects import TaskStatus, UserId
from b_domain.value_objects.user_behavior_metrics import UserBehaviorMetrics
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile
from c_application.dtos.task_dtos import CompleteTaskOutputDTO, TaskByUserRequest
from c_application.mappers.task_mapper import TaskMapper


class CompleteTaskUseCase(UseCase[TaskByUserRequest, CompleteTaskOutputDTO]):
    """Use case for completing a Task with support for partial ID matching.

    Allows users to provide a partial UUID (prefix) to identify a task.
    Ensures that ambiguous matches result in an error to prevent
    unintended task completions.
    """

    def __init__(
            self,
            uow: UnitOfWork,
            clock: ClockProvider,
            metrics_aggregator: UserBehaviorMetricsAggregator,
            behavior_learner: UserBehaviorLearner,
    ):
        """Initialize the use case.

        Args:
            uow (UnitOfWork): Unit of Work for transaction handling.
            clock (ClockProvider): Provides current time.
            metrics_aggregator (UserBehaviorMetricsAggregator): Updates metrics.
            behavior_learner (UserBehaviorLearner): Updates behavior profile.
        """

        super().__init__(uow, clock)
        self.metrics_aggregator = metrics_aggregator
        self.behavior_learner = behavior_learner

    async def execute(self, request: TaskByUserRequest) -> CompleteTaskOutputDTO:
        """Execute the task completion logic.

        Args:
            request (TaskByUserRequest): Input containing user and task prefix.

        Returns:
            CompleteTaskOutputDTO: DTO with completed task and next occurrence.
        """

        task_id_prefix: str = self._validate_prefix(request.task_id_prefix)
        user_id: UserId = self._parse_user_id(request.user_id)

        now: datetime = request.completed_at or self.clock.now()

        metrics: UserBehaviorMetrics
        new_metrics: UserBehaviorMetrics
        profile: UserBehaviorProfile
        new_profile: UserBehaviorProfile

        async with self.uow:
            metrics, profile = await self._load_behavior_state(user_id)
            task: Task = await self._resolve_task(task_id_prefix, user_id)
            actual_duration: int = await self._close_active_timers(task, now, request)

            self._update_task_statistics(task, actual_duration)

            new_metrics, new_profile = self._learn_behavior(
                metrics,
                profile,
                task,
                actual_duration,
                now,
            )

            next_task: Task | None = await self._complete_task(task, now, actual_duration)

            await self._unlock_dependencies(task)

            await self._persist_behavior(new_metrics, new_profile)

            await self.uow.tasks.update(task)

        return self._build_response(task, next_task, now)

    @staticmethod
    def _validate_prefix(prefix: str) -> str:
        """Validate that the task ID prefix is sufficiently long.

        Args:
            prefix (str): Task ID prefix.

        Returns:
            str: Validated prefix.

        Raises:
            ValidationException: If prefix length < 4.
        """

        if len(prefix) < 4:
            raise ValidationException("O prefixo do ID deve ter pelo menos 4 caracteres para busca.")
        return prefix

    @staticmethod
    def _parse_user_id(user_id: str) -> UserId:
        """Parse and validate user_id string into UserId.

        Args:
            user_id (str): User ID string.

        Returns:
            UserId: Parsed identifier.

        Raises:
            ValidationException: If user_id is invalid.
        """

        try:
            return UserId(UUID(user_id))
        except ValueError:
            raise ValidationException("O user_id informado é inválido.")

    async def _load_behavior_state(self, user_id: UserId) -> Tuple[UserBehaviorMetrics, UserBehaviorProfile]:
        """Load or initialize user behavior metrics and profile.

        Args:
            user_id (UserId): User identifier.

        Returns:
            tuple: (UserBehaviorMetrics, UserBehaviorProfile).
        """

        metrics: UserBehaviorMetrics = await self.uow.user_behavior_metrics.get_by_user_id(user_id)
        if metrics is None:
            metrics = UserBehaviorMetrics(user_id=user_id)

        profile: UserBehaviorProfile = await self.uow.user_behavior_profiles.get_by_user_id(user_id)
        if profile is None:
            profile = UserBehaviorProfile(user_id=user_id)

        return metrics, profile

    async def _resolve_task(self, prefix: str, user_id: UserId) -> Task:
        """Resolve a task by ID prefix.

        Ensures uniqueness and validates task state.

        Args:
            prefix (str): Task ID prefix.
            user_id (UserId): User identifier.

        Returns:
            Task: Resolved task.

        Raises:
            ValidationException: If no or multiple tasks match.
            InvalidStateTransition: If task is DONE or blocked.
        """

        tasks_found: list[Task] = await self.uow.tasks.find_by_id_prefix(
            id_prefix=prefix,
            user_id=user_id,
        )

        if not tasks_found:
            raise ValidationException(
                f"Nenhuma tarefa encontrada com o ID '{prefix}'."
            )

        if len(tasks_found) > 1:
            conflicting_ids = ", ".join([str(t.id)[:8] for t in tasks_found])

            raise ValidationException(
                f"ID ambíguo. Encontradas {len(tasks_found)} tarefas: [{conflicting_ids}]. "
                "Por favor, forneça um prefixo mais específico."
            )

        task: Task = tasks_found[0]

        if task.status == TaskStatus.DONE:
            raise InvalidStateTransition("task is already DONE")

        if task.is_blocked:
            raise InvalidStateTransition("complete all blocking tasks first")

        return task

    async def _close_active_timers(self, task: Task, now: datetime, request: TaskByUserRequest) -> int:
        """Close active timers for a task and compute actual duration.

        Args:
            task (Task): Task entity.
            now (datetime): Current time.
            request (TaskByUserRequest): Request containing completion time.

        Returns:
            int: Total elapsed minutes from timers.
        """

        actual_duration: int = 0

        active_timers: list[TimeEntry] = await self.uow.time_entries.get_actives_for_task(task.id)

        if not active_timers:
            return 0

        for timer in active_timers:
            timer.stop(request.completed_at)
            actual_duration += timer.elapsed_minutes(now)

        await self.uow.time_entries.update_all(active_timers)

        return actual_duration

    @staticmethod
    def _update_task_statistics(task: Task, duration: int) -> None:
        """Update task statistics after completion.

        Increments attempt/success counts and updates average duration.

        Args:
            task (Task): Task entity.
            duration (int): Duration in minutes.
        """

        task.attempt_count += 1
        task.success_count += 1

        if duration <= 0:
            return

        if task.success_count == 1:
            task.average_duration_minutes = duration
            return

        total_past_minutes: int = task.average_duration_minutes * (task.success_count - 1)
        task.average_duration_minutes = (total_past_minutes + duration) // task.success_count

    def _learn_behavior(
            self,
            metrics: UserBehaviorMetrics,
            profile: UserBehaviorProfile,
            task: Task,
            duration: int,
            now: datetime,
    ) -> Tuple[UserBehaviorMetrics, UserBehaviorProfile]:
        """Update metrics and profile based on completed task.

        Args:
            metrics (UserBehaviorMetrics): Current metrics.
            profile (UserBehaviorProfile): Current profile.
            task (Task): Completed task.
            duration (int): Task duration.
            now (datetime): Completion time.

        Returns:
            tuple: (new_metrics, new_profile).
        """

        new_metrics: UserBehaviorMetrics = self.metrics_aggregator.record_task_completed(
            metrics=metrics,
            duration_minutes=duration,
            energy=task.required_energy_level,
            complexity=task.complexity,
            now=now,
        )

        new_profile: UserBehaviorProfile = self.behavior_learner.learn(
            profile=profile,
            metrics=new_metrics,
        )

        return new_metrics, new_profile

    async def _complete_task(self, task: Task, now: datetime, duration: int) -> Task | None:
        """Mark task as done and create next occurrence if applicable.

        Args:
            task (Task): Task entity.
            now (datetime): Completion time.
            duration (int): Actual duration.

        Returns:
            Optional[Task]: Next occurrence if created.
        """

        task.mark_as_done(now, actual_minutes=duration)

        next_task: Task | None = task.create_next_occurrence(now)
        if not next_task:
            return None

        next_task.estimated_duration_minutes = task.average_duration_minutes

        return await self.uow.tasks.add(next_task)

    async def _unlock_dependencies(self, task: Task) -> None:
        """Remove dependency links from tasks blocked by the completed task.

        Args:
            task (Task): Completed task.
        """

        blocked_tasks: list[Task] = await self.uow.tasks.find_tasks_blocked_by(task.id)

        if not blocked_tasks:
            return

        for blocked in blocked_tasks:
            blocked.remove_dependency(task.id)

        await self.uow.tasks.update_many(blocked_tasks)

    async def _persist_behavior(self, metrics: UserBehaviorMetrics, profile: UserBehaviorProfile) -> None:
        """Persist updated metrics and profile.

        Args:
            metrics (UserBehaviorMetrics): Updated metrics.
            profile (UserBehaviorProfile): Updated profile.
        """
        await self.uow.user_behavior_metrics.save(metrics)
        await self.uow.user_behavior_profiles.save(profile)

    @staticmethod
    def _build_response(task: Task, next_task: Optional[Task], now: datetime) -> CompleteTaskOutputDTO:
        """Build output DTO for completed task and next occurrence.

        Args:
            task (Task): Completed task.
            next_task (Optional[Task]): Next occurrence if any.
            now (datetime): Completion time.

        Returns:
            CompleteTaskOutputDTO: Output DTO.
        """
        return CompleteTaskOutputDTO(
            completed_task=TaskMapper.to_output(task, now),
            next_occurrence=TaskMapper.to_output(next_task, now) if next_task else None,
        )
