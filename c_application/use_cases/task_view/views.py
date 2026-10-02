"""Saved views: save, list, find, remove."""

from b_domain.ports.use_case import UseCase
from b_domain.value_objects import UserId
from b_domain.value_objects.task_view import TaskView, ViewScope
from c_application.dtos.task_view_dtos import (
    SaveTaskViewInputDTO,
    TaskViewInputDTO,
    TaskViewOutputDTO,
    TaskViewsInputDTO,
    TaskViewsOutputDTO,
)
from c_application.use_cases.task_view._common import (
    check_filters,
    check_name,
    not_found,
    seen_here,
    view_output,
)


def _user(user_id: str) -> UserId:
    return UserId.from_string(user_id, error_msg="Invalid user ID.")


def _scope(everywhere: bool) -> ViewScope:
    return ViewScope.GLOBAL if everywhere else ViewScope.DEVICE


class SaveTaskViewUseCase(UseCase[SaveTaskViewInputDTO, TaskViewOutputDTO]):
    """Save the task list's filters under a name — this device's, or every
    device's — replacing a view of the same name and scope."""

    async def execute(self, request: SaveTaskViewInputDTO) -> TaskViewOutputDTO:
        """Save it.

        Raises:
            ValidationException: If the name or a filter is not valid, or
                there are no filters.
        """
        user_id: UserId = _user(request.user_id)
        view = TaskView(
            user_id=user_id,
            name=check_name(request.name),
            scope=_scope(request.everywhere),
            filters=check_filters(request.filters),
            saved_at=self.clock.now(),
        )
        async with self.uow as uow:
            replaced: bool = any(
                v == view for v in await uow.task_views.list_by_user(user_id)
            )
            await uow.task_views.save(view)
        return view_output(view, replaced=replaced)


class ListTaskViewsUseCase(UseCase[TaskViewsInputDTO, TaskViewsOutputDTO]):
    """The views seen on this device: its own first, then every device's,
    by name."""

    async def execute(self, request: TaskViewsInputDTO) -> TaskViewsOutputDTO:
        user_id: UserId = _user(request.user_id)
        async with self.uow as uow:
            views: list[TaskView] = await uow.task_views.list_by_user(user_id)
        own: set[str] = {v.name for v in views if v.scope == ViewScope.DEVICE}
        ordered: list[TaskView] = sorted(
            views, key=lambda v: (v.scope != ViewScope.DEVICE, v.name)
        )
        return TaskViewsOutputDTO(
            views=[
                view_output(v, hidden=v.scope == ViewScope.GLOBAL and v.name in own)
                for v in ordered
            ]
        )


class GetTaskViewUseCase(UseCase[TaskViewInputDTO, TaskViewOutputDTO]):
    """A view by its name: by default the one seen here (this device's own
    wins over every device's of the same name)."""

    async def execute(self, request: TaskViewInputDTO) -> TaskViewOutputDTO:
        """Find it.

        Raises:
            EntityNotFound: If there is no such view.
        """
        async with self.uow as uow:
            views: list[TaskView] = await uow.task_views.list_by_user(
                _user(request.user_id)
            )
        found: TaskView | None = _named(views, request)
        if found is None:
            raise not_found(request.name, views)
        return view_output(found)


class RemoveTaskViewUseCase(UseCase[TaskViewInputDTO, TaskViewOutputDTO]):
    """Forget a view: by default the one seen here (this device's own, else
    every device's — then on every device)."""

    async def execute(self, request: TaskViewInputDTO) -> TaskViewOutputDTO:
        """Forget it.

        Raises:
            EntityNotFound: If there is no such view.
        """
        user_id: UserId = _user(request.user_id)
        async with self.uow as uow:
            views: list[TaskView] = await uow.task_views.list_by_user(user_id)
            found: TaskView | None = _named(views, request)
            if found is None:
                raise not_found(request.name, views)
            await uow.task_views.remove(
                user_id, found.name, found.scope, self.clock.now()
            )
        return view_output(found)


def _named(views: list[TaskView], request: TaskViewInputDTO) -> TaskView | None:
    if request.everywhere is None:
        return seen_here(views, request.name)
    scope: ViewScope = _scope(request.everywhere)
    return next((v for v in views if v.name == request.name and v.scope == scope), None)
