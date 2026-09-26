"""A rule as plain JSON-safe data, and back — for snapshots (undo)."""

from dataclasses import fields
from datetime import datetime, time
from enum import Enum
from typing import Any

from b_domain.value_objects.dates import AxiomDate, DateKind
from b_domain.value_objects.enums import RecurrenceInterval
from b_domain.value_objects.recurrences._base import RecurrenceRule


def axiom_date_to_dict(value: AxiomDate) -> dict[str, Any]:
    """An AxiomDate as data: ISO value, kind and zone."""
    return {
        "value": value.value.isoformat(),
        "kind": value.kind.value,
        "timezone": value.timezone,
    }


def axiom_date_from_dict(data: dict[str, Any], cls: type[AxiomDate] = AxiomDate) -> Any:
    """An AxiomDate (or a subclass, e.g. DueDate) back from its data."""
    return cls(
        value=datetime.fromisoformat(data["value"]),
        kind=DateKind(data["kind"]),
        timezone=data.get("timezone"),
    )


def rule_to_dict(rule: RecurrenceRule) -> dict[str, Any]:
    """A rule as data: its class name and its own fields (no callables)."""
    data: dict[str, Any] = {"type": type(rule).__name__}
    for f in fields(rule):
        if not f.init:
            continue
        value: Any = getattr(rule, f.name)
        if callable(value):
            continue  # the business-day checker: the user's calendar, not data
        data[f.name] = _plain(value)
    return data


def rule_from_dict(data: dict[str, Any]) -> RecurrenceRule:
    """A rule back from ``rule_to_dict``.

    Raises:
        ValueError: If the rule type is unknown.
    """
    from b_domain.value_objects import recurrences

    cls: Any = getattr(recurrences, str(data.get("type")), None)
    if not (isinstance(cls, type) and issubclass(cls, RecurrenceRule)):
        raise ValueError(f"Unknown recurrence rule: {data.get('type')}")

    params: dict[str, Any] = {}
    for f in fields(cls):
        if not f.init or f.name not in data:
            continue
        value: Any = data[f.name]
        if value is None:
            params[f.name] = None
        elif f.name in ("start_date", "end_date"):
            params[f.name] = axiom_date_from_dict(value)
        elif f.name in ("days_of_week", "days_of_month"):
            params[f.name] = set(value)
        elif f.name in ("window_start", "window_end"):
            params[f.name] = time.fromisoformat(value)
        elif f.name == "frequency":
            params[f.name] = RecurrenceInterval(value)
        else:
            params[f.name] = value
    rule: RecurrenceRule = cls(**params)
    return rule


def _plain(value: Any) -> Any:
    if isinstance(value, AxiomDate):
        return axiom_date_to_dict(value)
    if isinstance(value, set | frozenset):
        return sorted(value)
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
