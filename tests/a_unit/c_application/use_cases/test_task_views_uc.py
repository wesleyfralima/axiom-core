"""Saved views (product Backlog 03, Part 2): the task list's filters under a
name, this device's or every device's."""

from datetime import UTC, date, datetime

import pytest

from a_core.exceptions import EntityNotFound, ValidationException
from b_domain.entities import User
from c_application.dtos.task_dtos import CreateTaskInputDTO
from c_application.dtos.task_view_dtos import (
    SaveTaskViewInputDTO,
    TaskViewInputDTO,
    TaskViewOutputDTO,
    TaskViewsInputDTO,
)
from c_application.use_cases import CreateTaskUseCase, ListTasksUseCase
from c_application.use_cases.task_view import (
    VIEW_FIELDS,
    GetTaskViewUseCase,
    ListTaskViewsUseCase,
    RemoveTaskViewUseCase,
    SaveTaskViewUseCase,
    list_request,
)
from tests.conftest import FakeUowFactory, UseCaseDeps

pytestmark = [pytest.mark.asyncio, pytest.mark.uc]


@pytest.fixture
async def user(fake_uow_factory: FakeUowFactory) -> User:
    created = User.create(username="ana", email="ana@test.com")
    await fake_uow_factory().users.add(created)
    return created


async def _save(
    deps: UseCaseDeps,
    user: User,
    name: str,
    everywhere: bool = False,
    **filters: object,
) -> TaskViewOutputDTO:
    return await SaveTaskViewUseCase(**deps).execute(
        SaveTaskViewInputDTO(
            user_id=str(user.id), name=name, filters=filters, everywhere=everywhere
        )
    )


async def test_a_view_keeps_the_lists_filters_as_data(
    use_case_context: UseCaseDeps, user: User
) -> None:
    saved = await _save(
        use_case_context,
        user,
        "urgent-work",
        context_id="Work",
        priority="high",
        due_before="tomorrow",
        tags=["client"],
        created_after=datetime(2026, 10, 1, tzinfo=UTC),
        due_on=date(2026, 10, 2),
    )

    assert (saved.name, saved.everywhere, saved.replaced) == (
        "urgent-work",
        False,
        False,
    )
    # Plain data: a date as typed stays relative, instants and days as ISO
    assert saved.filters["due_before"] == "tomorrow"
    assert saved.filters["created_after"] == "2026-10-01T00:00:00+00:00"
    assert saved.filters["due_on"] == "2026-10-02"
    # …and back to the list's request, with what is asked on top of it
    request = list_request(str(user.id), saved.filters, priority="low", limit=5)
    assert request.created_after == datetime(2026, 10, 1, tzinfo=UTC)
    assert (request.priority, request.limit, request.context_id) == ("low", 5, "Work")
    assert "user_id" not in VIEW_FIELDS


async def test_a_view_runs_as_the_task_list(
    use_case_context: UseCaseDeps, user: User
) -> None:
    create = CreateTaskUseCase(**use_case_context)
    for title, priority in (("Call the client", 3), ("Water the plants", 1)):
        await create.execute(
            CreateTaskInputDTO(user_id=str(user.id), title=title, priority=priority)
        )
    view = await _save(use_case_context, user, "urgent", priority="high")

    listed = await ListTasksUseCase(**use_case_context).execute(
        list_request(str(user.id), view.filters)
    )

    assert [t.title for t in listed.tasks] == ["Call the client"]


@pytest.mark.parametrize(
    ("name", "filters", "error"),
    [
        ("Urgent Work", {"priority": "high"}, "can't be a view's name"),
        ("x" * 31, {"priority": "high"}, "can't be a view's name"),
        ("ok", {}, "needs filters"),
        ("ok", {"user_id": "someone"}, "no filter user_id"),
        ("ok", {"colour": "red"}, "no filter colour"),
        ("ok", {"tags": [1, 2]}, "not plain data"),
    ],
)
async def test_what_a_view_refuses(
    use_case_context: UseCaseDeps,
    user: User,
    name: str,
    filters: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValidationException, match=error):
        await _save(use_case_context, user, name, **filters)  # type: ignore[arg-type]


async def test_this_devices_view_hides_the_accounts_of_the_same_name(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _save(use_case_context, user, "today", everywhere=True, due_on="today")
    await _save(use_case_context, user, "work", everywhere=True, context_id="Work")
    mine = await _save(use_case_context, user, "today", due_on="today", tags=["a"])
    again = await _save(use_case_context, user, "today", due_on="today")

    listed = await ListTaskViewsUseCase(**use_case_context).execute(
        TaskViewsInputDTO(user_id=str(user.id))
    )
    seen = await GetTaskViewUseCase(**use_case_context).execute(
        TaskViewInputDTO(user_id=str(user.id), name="today")
    )
    account = await GetTaskViewUseCase(**use_case_context).execute(
        TaskViewInputDTO(user_id=str(user.id), name="today", everywhere=True)
    )

    assert (mine.replaced, again.replaced) == (False, True)
    assert [(v.name, v.everywhere, v.hidden) for v in listed.views] == [
        ("today", False, False),
        ("today", True, True),
        ("work", True, False),
    ]
    assert (seen.everywhere, seen.filters) == (False, {"due_on": "today"})
    assert account.everywhere


async def test_removing_a_view(use_case_context: UseCaseDeps, user: User) -> None:
    await _save(use_case_context, user, "today", everywhere=True, due_on="today")
    await _save(use_case_context, user, "today", due_on="today")
    remove = RemoveTaskViewUseCase(**use_case_context)

    first = await remove.execute(TaskViewInputDTO(user_id=str(user.id), name="today"))
    second = await remove.execute(TaskViewInputDTO(user_id=str(user.id), name="today"))
    with pytest.raises(EntityNotFound, match="No view called 'today'"):
        await remove.execute(TaskViewInputDTO(user_id=str(user.id), name="today"))
    with pytest.raises(EntityNotFound, match="Your views: none yet"):
        await GetTaskViewUseCase(**use_case_context).execute(
            TaskViewInputDTO(user_id=str(user.id), name="today")
        )

    # This device's goes first, then every device's
    assert (first.everywhere, second.everywhere) == (False, True)


async def test_removing_one_scope_only(
    use_case_context: UseCaseDeps, user: User
) -> None:
    await _save(use_case_context, user, "today", due_on="today")
    remove = RemoveTaskViewUseCase(**use_case_context)

    with pytest.raises(EntityNotFound, match="Your views: today"):
        await remove.execute(
            TaskViewInputDTO(user_id=str(user.id), name="today", everywhere=True)
        )
