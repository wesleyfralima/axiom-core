"""Context use cases, and contexts as the task use cases see them."""

from uuid import UUID, uuid4

import pytest

from a_core import EntityNotFound, ValidationException
from a_core.exceptions import AmbiguousIdentifierError
from b_domain.entities import Context, Task, User
from b_domain.exceptions import ContextNameTakenError
from b_domain.value_objects import ContextId, Title, UserId
from c_application.dtos import CreateTaskInputDTO
from c_application.dtos.task_dtos import GetTaskRequest, ListTasksRequest
from c_application.use_cases import (
    CreateContextUseCase,
    CreateTaskUseCase,
    DeleteContextUseCase,
    GetTaskUseCase,
    ListContextsUseCase,
    ListTasksUseCase,
    SwitchContextUseCase,
    UpdateContextUseCase,
)
from c_application.use_cases.context.create import CreateContextInputDTO
from c_application.use_cases.context.delete import DeleteContextInputDTO
from c_application.use_cases.context.list import ListContextsInputDTO
from c_application.use_cases.context.switch import SwitchContextInputDTO
from c_application.use_cases.context.update import UpdateContextInputDTO
from c_application.utils import find_context
from tests.conftest import FakeClock, FakeUowFactory, UseCaseDeps

pytestmark = pytest.mark.uc


async def _user(fake_uow_factory: FakeUowFactory) -> User:
    user = User.create(username="ana", email="a@a.com")
    await fake_uow_factory().users.add(user)
    return user


async def _context(
    deps: UseCaseDeps, user: User, name: str, icon: str | None = None
) -> str:
    created = await CreateContextUseCase(**deps).execute(
        CreateContextInputDTO(user_id=str(user.id), name=name, icon=icon)
    )
    return created.id


async def _names(deps: UseCaseDeps, user: User) -> list[str]:
    listed = await ListContextsUseCase(**deps).execute(
        ListContextsInputDTO(user_id=str(user.id))
    )
    return [c.name for c in listed.contexts]


# ---------------------------------------------------------------- create / list


async def test_create_returns_the_context(
    use_case_context: UseCaseDeps,
    fake_uow_factory: FakeUowFactory,
    fake_clock: FakeClock,
) -> None:
    user = await _user(fake_uow_factory)

    created = await CreateContextUseCase(**use_case_context).execute(
        CreateContextInputDTO(user_id=str(user.id), name=" Work ", icon="💼")
    )

    assert (created.name, created.icon, created.is_active) == ("Work", "💼", False)
    stored = fake_uow_factory().contexts.contexts[created.id]
    assert stored.user_id == user.id
    assert stored.created_at == fake_clock.now()


async def test_create_refuses_a_name_the_user_already_has(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "Work")

    with pytest.raises(ContextNameTakenError, match="work"):
        await _context(use_case_context, user, "work")


async def test_another_user_may_reuse_the_name(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    ana = await _user(fake_uow_factory)
    bia = User.create(username="bia", email="b@b.com")
    await fake_uow_factory().users.add(bia)

    await _context(use_case_context, ana, "Work")
    await _context(use_case_context, bia, "Work")

    assert await _names(use_case_context, bia) == ["Work"]


async def test_create_for_an_unknown_user_fails(use_case_context: UseCaseDeps) -> None:
    with pytest.raises(EntityNotFound, match="User"):
        await CreateContextUseCase(**use_case_context).execute(
            CreateContextInputDTO(user_id=str(uuid4()), name="Work")
        )


async def test_list_is_sorted_by_name_and_marks_the_active_one(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    for name in ("work", "Errands", "Home"):
        await _context(use_case_context, user, name)
    await SwitchContextUseCase(**use_case_context).execute(
        SwitchContextInputDTO(user_id=str(user.id), context="home")
    )

    listed = await ListContextsUseCase(**use_case_context).execute(
        ListContextsInputDTO(user_id=str(user.id))
    )

    assert [(c.name, c.is_active) for c in listed.contexts] == [
        ("Errands", False),
        ("Home", True),
        ("work", False),
    ]


# ---------------------------------------------------------------- update


async def test_update_renames_and_keeps_the_rest(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "Work", icon="💼")

    updated = await UpdateContextUseCase(**use_case_context).execute(
        UpdateContextInputDTO(user_id=str(user.id), context="work", name="Job")
    )

    assert (updated.name, updated.icon) == ("Job", "💼")


async def test_update_may_change_the_case_of_its_own_name(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "work")

    updated = await UpdateContextUseCase(**use_case_context).execute(
        UpdateContextInputDTO(user_id=str(user.id), context="work", name="Work")
    )

    assert updated.name == "Work"


async def test_update_refuses_another_contexts_name(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "Work")
    await _context(use_case_context, user, "Home")

    with pytest.raises(ContextNameTakenError):
        await UpdateContextUseCase(**use_case_context).execute(
            UpdateContextInputDTO(user_id=str(user.id), context="home", name="WORK")
        )


async def test_update_without_changes_is_refused(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "Work")

    with pytest.raises(ValidationException, match="Nothing to update"):
        await UpdateContextUseCase(**use_case_context).execute(
            UpdateContextInputDTO(user_id=str(user.id), context="work")
        )


# ---------------------------------------------------------------- switch


async def test_switch_by_name_then_by_id_prefix_then_off(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    work_id = await _context(use_case_context, user, "Work")
    home_id = await _context(use_case_context, user, "Home")
    switch = SwitchContextUseCase(**use_case_context)

    first = await switch.execute(
        SwitchContextInputDTO(user_id=str(user.id), context="WORK")
    )
    assert first.changed
    assert first.active is not None and first.active.id == work_id
    assert first.active.is_active
    assert first.previous is None

    second = await switch.execute(
        SwitchContextInputDTO(user_id=str(user.id), context=home_id[:8])
    )
    assert second.active is not None and second.active.id == home_id
    assert second.previous is not None and second.previous.id == work_id
    assert not second.previous.is_active

    off = await switch.execute(
        SwitchContextInputDTO(user_id=str(user.id), context=None)
    )
    assert off.changed and off.active is None
    stored = fake_uow_factory().users.users[str(user.id)]
    assert stored.preferences.active_context_id is None


async def test_switching_to_the_active_context_changes_nothing(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "Work")
    switch = SwitchContextUseCase(**use_case_context)
    await switch.execute(SwitchContextInputDTO(user_id=str(user.id), context="Work"))

    again = await switch.execute(
        SwitchContextInputDTO(user_id=str(user.id), context="work")
    )

    assert again.changed is False
    assert again.active is not None and again.active.name == "Work"


async def test_switch_to_an_unknown_context_fails(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)

    with pytest.raises(EntityNotFound, match="Context"):
        await SwitchContextUseCase(**use_case_context).execute(
            SwitchContextInputDTO(user_id=str(user.id), context="Mars")
        )


# ---------------------------------------------------------------- delete


async def test_delete_detaches_tasks_and_turns_the_active_context_off(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "Work")
    await SwitchContextUseCase(**use_case_context).execute(
        SwitchContextInputDTO(user_id=str(user.id), context="Work")
    )
    task = await CreateTaskUseCase(**use_case_context).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Report")
    )
    assert task.context_name == "Work"

    deleted = await DeleteContextUseCase(**use_case_context).execute(
        DeleteContextInputDTO(user_id=str(user.id), context="work")
    )

    assert (deleted.name, deleted.was_active) == ("Work", True)
    assert await _names(use_case_context, user) == []
    uow = fake_uow_factory()
    assert uow.users.users[str(user.id)].preferences.active_context_id is None
    stored_task = uow.tasks.tasks[task.id]
    assert stored_task.context_id is None


async def test_delete_an_inactive_context_keeps_the_active_one(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "Work")
    home_id = await _context(use_case_context, user, "Home")
    await SwitchContextUseCase(**use_case_context).execute(
        SwitchContextInputDTO(user_id=str(user.id), context="Home")
    )

    deleted = await DeleteContextUseCase(**use_case_context).execute(
        DeleteContextInputDTO(user_id=str(user.id), context="Work")
    )

    assert deleted.was_active is False
    active = fake_uow_factory().users.users[str(user.id)].preferences.active_context_id
    assert str(active) == home_id


# ---------------------------------------------------------------- find_context


def _ctx(name: str, id_: str) -> Context:
    context = Context.create(now=FakeClock().now(), user_id=UserId(uuid4()), name=name)
    context.id = ContextId(UUID(id_))
    return context


def test_find_context_prefers_the_name_over_an_id_prefix() -> None:
    by_prefix = _ctx("Work", "abcd0000-0000-4000-8000-000000000000")
    named_like_a_prefix = _ctx("abcd", "11110000-0000-4000-8000-000000000000")

    assert find_context([by_prefix, named_like_a_prefix], "abcd") is named_like_a_prefix


def test_find_context_refuses_an_ambiguous_prefix() -> None:
    contexts = [
        _ctx("Work", "abcd0000-0000-4000-8000-000000000000"),
        _ctx("Home", "abcd1111-0000-4000-8000-000000000000"),
    ]

    with pytest.raises(AmbiguousIdentifierError):
        find_context(contexts, "abcd")


def test_find_context_ignores_prefixes_that_are_too_short() -> None:
    contexts = [_ctx("Work", "abcd0000-0000-4000-8000-000000000000")]

    with pytest.raises(EntityNotFound):
        find_context(contexts, "abc")


# ---------------------------------------------------------------- tasks


async def test_task_created_with_a_context_name_shows_it(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    work_id = await _context(use_case_context, user, "Work", icon="💼")

    created = await CreateTaskUseCase(**use_case_context).execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Report", context_id="work")
    )

    assert (created.context_id, created.context_name, created.context_icon) == (
        work_id,
        "Work",
        "💼",
    )
    shown = await GetTaskUseCase(**use_case_context).execute(
        GetTaskRequest(task_id_prefix=created.id[:8], user_id=str(user.id))
    )
    assert shown.context_name == "Work"


async def test_task_with_an_unknown_context_is_refused(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)

    with pytest.raises(EntityNotFound, match="Context"):
        await CreateTaskUseCase(**use_case_context).execute(
            CreateTaskInputDTO(user_id=str(user.id), title="Report", context_id="Mars")
        )


async def test_list_filters_by_context_name_and_shows_each_context(
    use_case_context: UseCaseDeps, fake_uow_factory: FakeUowFactory
) -> None:
    user = await _user(fake_uow_factory)
    await _context(use_case_context, user, "Work")
    await _context(use_case_context, user, "Home")
    create = CreateTaskUseCase(**use_case_context)
    await create.execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Report", context_id="Work")
    )
    await create.execute(
        CreateTaskInputDTO(user_id=str(user.id), title="Dishes", context_id="Home")
    )
    no_context = Task.create(
        now=FakeClock().now(), user_id=user.id, title=Title("Free")
    )
    await fake_uow_factory().tasks.add(no_context)
    list_tasks = ListTasksUseCase(**use_case_context)

    everything = await list_tasks.execute(ListTasksRequest(user_id=str(user.id)))
    only_home = await list_tasks.execute(
        ListTasksRequest(user_id=str(user.id), context_id="home")
    )

    shown = {t.title: t.context_name for t in everything.tasks}
    assert shown == {"Report": "Work", "Dishes": "Home", "Free": None}
    assert [t.title for t in only_home.tasks] == ["Dishes"]
