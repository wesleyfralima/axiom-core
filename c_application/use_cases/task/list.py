from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from a_core.exceptions import ValidationException
from b_domain.entities import Context, Task, User
from b_domain.entities.user import UserPrefs
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.ports.use_case import UseCase
from b_domain.value_objects import (
    ContextId,
    Priority,
    TaskId,
    TaskStatus,
    UserId,
)
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity
from b_domain.value_objects.texts import normalize_tags
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.dtos.task_dtos import (
    ListTasksRequest,
    TaskListOutputDTO,
    TaskOutputDTO,
)
from c_application.mappers.context_mapper import ContextMapper
from c_application.mappers.task_mapper import TaskMapper
from c_application.utils import find_context
from c_application.utils.date_input import (
    at_time,
    end_of_day,
    local_today,
    resolve_date_input,
    resolve_horizon,
)
from c_application.utils.task_utils import find_task
from c_application.utils.work_calendar import use_work_calendar


class ListTasksUseCase(UseCase[ListTasksRequest, TaskListOutputDTO]):
    """Use case for listing tasks with filtering and domain mapping.

    This use case applies comprehensive filters including GTD attributes,
    temporal ranges, and pagination, then maps the results into output DTOs.
    """

    async def execute(self, request: ListTasksRequest) -> TaskListOutputDTO:
        """Execute the task listing workflow.

        Steps:
            1. Validate and resolve input into value objects.
            2. Build a domain-level filter object.
            3. Query the repository for matching tasks.
            4. Map tasks into output DTOs with consistent formatting.

        Args:
            request (ListTasksRequest): Request object containing filter criteria.

        Returns:
            TaskListOutputDTO: List of tasks matching the filters.

        Raises:
            InvalidValueError: If priority, complexity or max_energy is unknown.
            ValidationException: If the user ID or the status is invalid.
            EntityNotFound: If the context filter matches no context.
            AmbiguousIdentifierError: If the context's ID prefix matches several.
        """

        async with self.uow as uow:
            # 1. Validation and resolution of value objects
            try:
                f_user_id: UserId = UserId.from_string(
                    request.user_id, error_msg="Invalid user ID."
                )
            except ValidationException as e:
                raise ValidationException(e) from e

            try:
                f_status: TaskStatus | None = (
                    TaskStatus(request.status) if request.status else None
                )
            except ValueError as e:
                raise ValidationException(f"Invalid status: {request.status}.") from e

            f_priority: Priority | None = (
                Priority.parse(request.priority) if request.priority else None
            )
            f_complexity: TaskComplexity | None = (
                TaskComplexity.parse(request.complexity) if request.complexity else None
            )

            # The parent: its ID or an ID prefix, among the user's tasks
            f_parent_id: TaskId | None = (
                (await find_task(uow, request.parent_id, f_user_id)).id
                if request.parent_id
                else None
            )

            # The user's contexts: to resolve the filter (name or ID prefix)
            # and to show each task's context
            contexts: list[Context] = await uow.contexts.list_by_user(f_user_id)
            scope: Context | None = None
            user: User | None = await uow.users.get_by_id(f_user_id)
            prefs: UserPrefs = user.preferences if user else UserPrefs()
            active_id: ContextId | None = prefs.active_context_id
            if request.inbox:
                scope = None  # the inbox has no context, whatever is active
            elif request.context_id:
                scope = find_context(contexts, request.context_id)
            elif request.use_active_context and active_id:
                scope = next((c for c in contexts if c.id == active_id), None)
            f_context_id: ContextId | None = scope.id if scope else None

            f_ids: list[TaskId] | None = None
            if request.ids:
                try:
                    f_ids = [TaskId.from_string(i) for i in request.ids]
                except ValidationException as e:
                    raise ValidationException(
                        "One or more IDs in the list are invalid."
                    ) from e

            energy_level: EnergyLevel | None = (
                EnergyLevel.parse(request.max_energy) if request.max_energy else None
            )

            # Dates as typed, in the user's today
            now: datetime = self.clock.now()
            today: date = local_today(now, prefs.timezone)
            due_before: datetime | None = (
                at_time(resolve_date_input(request.due_before, today=today), time())
                if request.due_before is not None
                else None
            )
            due_after: datetime | None = (
                at_time(resolve_date_input(request.due_after, today=today), time())
                if request.due_after is not None
                else None
            )
            horizon: date = resolve_horizon(
                request.ahead if request.ahead is not None else prefs.days_ahead,
                today=today,
            )

            # 2. Build complete domain filter (Mapping DTO -> TaskFilter)
            filters: TaskFilter = TaskFilter(
                # Identifiers & Pagination
                user_id=f_user_id,
                parent_id=f_parent_id,
                ids=f_ids,
                limit=request.limit,
                offset=request.offset,
                # Core attributes
                status=f_status,
                # An explicit status wins over hiding the closed ones;
                # archived tasks only show when asked for by status
                exclude_statuses=(
                    frozenset()
                    if f_status is not None or request.deleted
                    else frozenset({TaskStatus.ARCHIVED})
                    if request.include_closed and not request.inbox
                    else TaskStatus.closed()
                ),
                priority=f_priority,
                context_id=f_context_id,
                tags=sorted(normalize_tags(request.tags)),
                has_context=False if request.inbox else None,
                has_due_date=False if request.inbox else None,
                # GTD specific
                max_energy_level=energy_level,
                complexity=f_complexity,
                # Behavior flags
                is_blocked=None if request.include_blocked else False,
                is_recurring=request.is_recurring,
                only_roots=request.only_roots,
                # Temporal filters ("tomorrow", a date alone: its midnight)
                due_before=due_before,
                due_after=due_after,
                created_before=request.created_before,
                created_after=request.created_after,
                updated_before=request.updated_before,
                updated_after=request.updated_after,
                deleted=request.deleted,
            )

            # 3. Query repository
            tasks: list[Task] = await uow.tasks.list(filters)
            await use_work_calendar(uow, f_user_id, prefs, tasks)

            # 4. Centralized mapping; each parent's title, for a subtask
            # whose parent is not in the list
            by_id: dict[ContextId, Context] = {c.id: c for c in contexts}
            parent_titles: dict[TaskId, str] = {}
            for ref in {t.parent_id for t in tasks if t.parent_id is not None}:
                parent: Task | None = await uow.tasks.get_by_id(ref, f_user_id)
                if parent is not None:
                    parent_titles[ref] = str(parent.title)
            outputs: list[TaskOutputDTO] = []
            projected: list[tuple[datetime, TaskOutputDTO]] = []
            until: datetime = end_of_day(horizon, prefs.timezone)
            for task in tasks:
                output: TaskOutputDTO = TaskMapper.to_output(
                    task,
                    now,
                    context=by_id.get(task.context_id) if task.context_id else None,
                    parent_title=(
                        parent_titles.get(task.parent_id) if task.parent_id else None
                    ),
                )
                outputs.append(output)

                # 5. The occurrences to come, which do not exist yet
                if task.status.is_closed or request.deleted:
                    continue
                for occurrence in task.upcoming_occurrences(now, until):
                    wall: datetime = _wall_clock(occurrence, prefs.timezone)
                    if (due_before and wall > due_before) or (
                        due_after and wall < due_after
                    ):
                        continue
                    projected.append(
                        (
                            wall,
                            replace(
                                output,
                                due_date=occurrence,
                                is_overdue=False,
                                is_projected=True,
                            ),
                        )
                    )

            projected.sort(key=lambda pair: pair[0])
            return TaskListOutputDTO(
                tasks=outputs,
                context=(
                    ContextMapper.to_output(scope, ContextOutputDTO, active_id)
                    if scope
                    else None
                ),
                projected=[dto for _, dto in projected],
            )


def _wall_clock(dt: datetime, tz_name: str) -> datetime:
    """A due date as wall-clock time where the user is (naive)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)
