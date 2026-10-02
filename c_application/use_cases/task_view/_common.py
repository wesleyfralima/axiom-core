"""What every saved-view use case shares: the filters as data, and the
task list request they make."""

from collections.abc import Mapping
from dataclasses import fields
from datetime import date, datetime
from typing import Any

from a_core.exceptions import ValidationException
from b_domain.exceptions.task_view import TaskViewNotFound
from b_domain.value_objects.task_view import VIEW_NAME, TaskView, ViewScope
from c_application.dtos.task_dtos import ListTasksRequest
from c_application.dtos.task_view_dtos import TaskViewOutputDTO

VIEW_FIELDS: frozenset[str] = frozenset(
    f.name for f in fields(ListTasksRequest) if f.name != "user_id"
)
"""What a view keeps: the task list request's fields, its owner aside."""

_INSTANTS: frozenset[str] = frozenset(
    {"created_after", "created_before", "updated_after", "updated_before"}
)
"""Fields kept as ISO text and given back as instants."""


def check_name(name: str) -> str:
    """A view's name, checked.

    Raises:
        ValidationException: If it is not one.
    """
    if not VIEW_NAME.match(name):
        raise ValidationException(
            f"'{name}' can't be a view's name: lower case letters, digits, - "
            "and _ (up to 30), e.g. urgent-work."
        )
    return name


def check_filters(filters: Mapping[str, Any]) -> dict[str, Any]:
    """A view's filters as JSON data: known fields only, instants as ISO
    text.

    Raises:
        ValidationException: If there is none, or a field the task list does
            not have, or a value that is not plain data.
    """
    if not filters:
        raise ValidationException("A view needs filters: e.g. a context, a priority.")
    unknown: list[str] = sorted(set(filters) - VIEW_FIELDS)
    if unknown:
        raise ValidationException(f"The task list has no filter {', '.join(unknown)}.")
    kept: dict[str, Any] = {}
    for name, value in filters.items():
        if isinstance(value, date):  # an instant too: ISO text, read back
            value = value.isoformat()
        if not _plain(value):
            raise ValidationException(f"The filter {name} is not plain data.")
        kept[name] = value
    return kept


def _plain(value: Any) -> bool:
    if value is None or isinstance(value, bool | int | float | str):
        return True
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def list_request(
    user_id: str, filters: Mapping[str, Any], **overrides: Any
) -> ListTasksRequest:
    """The task list request a view makes, with what was asked on top of it
    (``overrides`` win)."""
    values: dict[str, Any] = {**filters, **overrides}
    for name in _INSTANTS & values.keys():
        if isinstance(values[name], str):
            values[name] = datetime.fromisoformat(values[name])
    return ListTasksRequest(user_id=user_id, **values)


def seen_here(views: list[TaskView], name: str) -> TaskView | None:
    """The view of that name seen on this device: its own, else every
    device's."""
    same: list[TaskView] = [v for v in views if v.name == name]
    return next(
        (v for v in same if v.scope == ViewScope.DEVICE),
        next(iter(same), None),
    )


def not_found(name: str, views: list[TaskView]) -> TaskViewNotFound:
    return TaskViewNotFound(name, sorted({v.name for v in views}))


def view_output(
    view: TaskView, *, hidden: bool = False, replaced: bool = False
) -> TaskViewOutputDTO:
    return TaskViewOutputDTO(
        name=view.name,
        everywhere=view.scope == ViewScope.GLOBAL,
        filters=dict(view.filters),
        hidden=hidden,
        replaced=replaced,
    )
