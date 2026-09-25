"""Context entity and the user's active context."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from a_core import ValidationException
from b_domain.entities import Context, User
from b_domain.entities.context import DEFAULT_CONTEXT_ICON
from b_domain.events.other_events import ContextSwitchedEvent
from b_domain.value_objects import ContextId, UserId

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.unit


def _context(name: str = "Work", **kwargs: str) -> Context:
    return Context.create(now=NOW, user_id=UserId(uuid4()), name=name, **kwargs)


def test_create_cleans_the_fields_and_stamps_the_given_time() -> None:
    context = _context("  Work  ", icon=" 💼 ", description="  Office stuff ")

    assert context.name == "Work"
    assert context.icon == "💼"
    assert context.description == "Office stuff"
    assert context.created_at == context.updated_at == NOW
    assert isinstance(context.id, ContextId)


def test_create_defaults_the_icon_and_the_description() -> None:
    context = _context()

    assert context.icon == DEFAULT_CONTEXT_ICON
    assert context.description == ""


@pytest.mark.parametrize("name", ["", "   ", "x" * (Context.NAME_MAX_LENGTH + 1)])
def test_create_refuses_an_empty_or_too_long_name(name: str) -> None:
    with pytest.raises(ValidationException, match="Context name"):
        _context(name)


@pytest.mark.parametrize("icon", ["  ", "x" * (Context.ICON_MAX_LENGTH + 1)])
def test_create_refuses_an_empty_or_too_long_icon(icon: str) -> None:
    with pytest.raises(ValidationException, match="Context icon"):
        _context(icon=icon)


def test_update_changes_only_what_was_given() -> None:
    context = _context(icon="💼", description="Office")
    later = NOW + timedelta(hours=1)

    context.update(later, name=" Job ")

    assert (context.name, context.icon, context.description) == ("Job", "💼", "Office")
    assert context.updated_at == later

    context.update(later, description="")
    assert context.description == ""


def test_update_validates_like_create() -> None:
    context = _context()

    with pytest.raises(ValidationException):
        context.update(NOW, name="  ")

    assert context.name == "Work"


def test_matches_name_ignores_case_and_spaces() -> None:
    context = _context("Deep Work")

    assert context.matches_name("  deep work ")
    assert not context.matches_name("deep")


def test_switch_context_records_the_change_and_emits_the_event() -> None:
    user = User.create(username="ana", email="a@a.com")
    context_id = ContextId(uuid4())

    assert user.switch_context(NOW, context_id) is True

    assert user.preferences.active_context_id == context_id
    assert user.updated_at == NOW
    [event] = user.pull_events()
    assert isinstance(event, ContextSwitchedEvent)
    assert event.user_id == user.id
    assert event.old_context_id is None
    assert event.new_context_id == context_id
    assert event.occurred_at == NOW


def test_switching_to_the_active_context_is_a_no_op() -> None:
    user = User.create(username="ana", email="a@a.com")
    context_id = ContextId(uuid4())
    user.switch_context(NOW, context_id)
    user.pull_events()

    assert user.switch_context(NOW, context_id) is False
    assert user.pull_events() == []


def test_switching_to_none_turns_the_filter_off() -> None:
    user = User.create(username="ana", email="a@a.com")
    context_id = ContextId(uuid4())
    user.switch_context(NOW, context_id)
    user.pull_events()

    assert user.switch_context(NOW, None) is True

    assert user.preferences.active_context_id is None
    [event] = user.pull_events()
    assert isinstance(event, ContextSwitchedEvent)
    assert (event.old_context_id, event.new_context_id) == (context_id, None)


@pytest.mark.parametrize("new_id", [ContextId(uuid4()), None])
def test_context_switched_event_survives_the_outbox_round_trip(
    new_id: ContextId | None,
) -> None:
    event = ContextSwitchedEvent(
        user_id=UserId(uuid4()),
        old_context_id=ContextId(uuid4()),
        new_context_id=new_id,
    )

    back = ContextSwitchedEvent.from_dict(event.to_payload())

    assert isinstance(back, ContextSwitchedEvent)
    assert back.user_id == event.user_id
    assert back.old_context_id == event.old_context_id
    assert back.new_context_id == new_id
