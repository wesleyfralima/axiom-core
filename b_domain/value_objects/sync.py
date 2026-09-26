"""What devices exchange to stay in sync: one changed field at a time.

Sync carries **results, not commands**: the device where a change happens runs
the use case, and what it wrote goes out as operations (``SyncOperation``) —
one per changed field of a row. The other devices apply them straight to their
data, deciding each field by its clock (``Hlc``): the last writer wins, field
by field (``b_domain.services.sync_merge``).
"""

import dataclasses
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, ClassVar, Self
from uuid import UUID, uuid4

from a_core import ValueObject
from a_core.exceptions import ValidationException

_HEX32: re.Pattern[str] = re.compile(r"[0-9a-f]{32}")
_FIELD_NAME: re.Pattern[str] = re.compile(r"_?[a-z][a-z0-9_]{0,63}")


@dataclass(frozen=True, order=True)
class Hlc(ValueObject):
    """A hybrid logical clock: the moment of a change, comparable on every
    device.

    A wall-clock time in milliseconds, a counter for changes within the same
    millisecond, and the device that made it. Clocks compare in that order,
    so the device breaks ties and every device reaches the same answer.

    A device never goes back: each local change takes the later of its
    wall-clock time and the last clock it has seen (``tick``), and every
    clock it receives moves it forward (``receive``). A device whose clock
    runs behind still writes after what it has already seen.

    Written as text (``str``, ``parse``) it sorts the same way:
    ``000001790000000-00003-<device hex>``.

    Attributes:
        wall_ms (int): Milliseconds since the Unix epoch.
        counter (int): Changes within that millisecond, from 0.
        device_id (str): The device, as 32 lowercase hex digits.
    """

    wall_ms: int
    counter: int
    device_id: str

    MAX_COUNTER: ClassVar[int] = 99_999
    _WALL_DIGITS: ClassVar[int] = 15
    _COUNTER_DIGITS: ClassVar[int] = 5

    def __post_init__(self) -> None:
        """Check the parts.

        Raises:
            ValidationException: If a part is out of range or the device is
                not 32 lowercase hex digits.
        """
        if not 0 <= self.wall_ms < 10**self._WALL_DIGITS:
            raise ValidationException(f"A clock's time is out of range: {self.wall_ms}")
        if not 0 <= self.counter <= self.MAX_COUNTER:
            raise ValidationException(
                f"A clock's counter is out of range: {self.counter}"
            )
        if not _HEX32.fullmatch(self.device_id):
            raise ValidationException(
                f"A device ID must be 32 lowercase hex digits: {self.device_id!r}"
            )

    def __str__(self) -> str:
        """The clock as text that sorts like the clock."""
        return (
            f"{self.wall_ms:0{self._WALL_DIGITS}d}"
            f"-{self.counter:0{self._COUNTER_DIGITS}d}-{self.device_id}"
        )

    @classmethod
    def parse(cls, text: str) -> Self:
        """Read a clock written by ``str``.

        Raises:
            ValidationException: If the text is not a clock.
        """
        parts: list[str] = text.split("-")
        if (
            len(parts) != 3
            or len(parts[0]) != cls._WALL_DIGITS
            or len(parts[1]) != cls._COUNTER_DIGITS
            or not (parts[0] + parts[1]).isdigit()
        ):
            raise ValidationException(f"Not a clock: {text!r}")
        return cls(wall_ms=int(parts[0]), counter=int(parts[1]), device_id=parts[2])

    @classmethod
    def start(cls, device: UUID) -> Self:
        """A device's clock before its first change."""
        return cls(wall_ms=0, counter=0, device_id=device.hex)

    def tick(self, now: datetime) -> Self:
        """The clock of a new local change, after this one.

        Args:
            now (datetime): The device's time (aware).

        Returns:
            Hlc: A clock later than this one and not before ``now``.
        """
        wall: int = max(self.wall_ms, _ms(now))
        counter: int = self.counter + 1 if wall == self.wall_ms else 0
        return self._next(wall, counter)

    def receive(self, remote: "Hlc", now: datetime) -> Self:
        """This device's clock after seeing another device's.

        Args:
            remote (Hlc): A clock that came from another device.
            now (datetime): The device's time (aware).

        Returns:
            Hlc: A clock of this device later than both clocks.
        """
        wall: int = max(self.wall_ms, remote.wall_ms, _ms(now))
        if wall == self.wall_ms == remote.wall_ms:
            counter: int = max(self.counter, remote.counter) + 1
        elif wall == self.wall_ms:
            counter = self.counter + 1
        elif wall == remote.wall_ms:
            counter = remote.counter + 1
        else:
            counter = 0
        return self._next(wall, counter)

    def is_ahead_of(self, now: datetime, tolerance: timedelta) -> bool:
        """Whether the clock runs ahead of ``now`` by more than ``tolerance``
        — a device with a wrong clock, whose changes would win every time."""
        return self.wall_ms - _ms(now) > tolerance / timedelta(milliseconds=1)

    def _next(self, wall: int, counter: int) -> Self:
        """This device's clock at ``wall``/``counter``; a full counter moves to
        the next millisecond."""
        if counter > self.MAX_COUNTER:
            wall, counter = wall + 1, 0
        return type(self)(wall_ms=wall, counter=counter, device_id=self.device_id)


def _ms(now: datetime) -> int:
    """An aware instant in milliseconds since the Unix epoch.

    Raises:
        ValidationException: If ``now`` has no time zone.
    """
    if now.tzinfo is None:
        raise ValidationException("A clock needs an aware time.")
    return int(now.timestamp() * 1000)


class SyncEntity(StrEnum):
    """The kinds of row that sync between devices."""

    USER = "user"
    CONTEXT = "context"
    CALENDAR_DAY = "calendar_day"
    TASK = "task"
    TIME_ENTRY = "time_entry"
    TASK_HISTORY = "task_history"

    @property
    def rank(self) -> int:
        """Where its rows go when applying: a row comes after the ones it
        points to (a task after its context, a timer after its task)."""
        return list(SyncEntity).index(self)


CREATED: str = "_created"
"""The field of a new row's operation; its value holds every field."""

DELETED: str = "_deleted"
"""The field of a row's deletion, which is final."""


@dataclass(frozen=True, kw_only=True)
class SyncOperation(ValueObject):
    """One changed field of one row, as it travels between devices.

    Attributes:
        entity (SyncEntity): The kind of row.
        entity_id (UUID): The row.
        field (str): The field that changed; ``CREATED`` for a new row (the
            value holds every field), ``DELETED`` for a deleted one. A field
            may be a group that travels whole (the due date).
        value (Any): The new value, as JSON (None, bool, int, float, str,
            list, dict).
        hlc (Hlc): When it changed, and on which device.
        op_id (UUID): The operation itself: the same one received twice is
            applied once.
    """

    entity: SyncEntity
    entity_id: UUID
    field: str
    value: Any
    hlc: Hlc
    op_id: UUID = dataclasses.field(default_factory=uuid4)

    def __post_init__(self) -> None:
        """Check the field and the value.

        Raises:
            ValidationException: If the field is not a name, or a new row's
                value is not a dict of fields.
        """
        if not _FIELD_NAME.fullmatch(self.field):
            raise ValidationException(f"Not a field name: {self.field!r}")
        if self.field.startswith("_") and self.field not in (CREATED, DELETED):
            raise ValidationException(f"Unknown special field: {self.field!r}")
        if self.field == CREATED and not (
            isinstance(self.value, dict)
            and all(
                isinstance(name, str)
                and _FIELD_NAME.fullmatch(name)
                and not name.startswith("_")
                for name in self.value
            )
        ):
            raise ValidationException("A new row's value must be a dict of fields.")

    @classmethod
    def created(
        cls, hlc: Hlc, entity: SyncEntity, entity_id: UUID, fields: dict[str, Any]
    ) -> Self:
        """A new row with every field."""
        return cls(
            entity=entity, entity_id=entity_id, field=CREATED, value=fields, hlc=hlc
        )

    @classmethod
    def deleted(cls, hlc: Hlc, entity: SyncEntity, entity_id: UUID) -> Self:
        """A row deleted for good."""
        return cls(
            entity=entity, entity_id=entity_id, field=DELETED, value=None, hlc=hlc
        )

    @property
    def device_id(self) -> str:
        """The device that made the change."""
        return self.hlc.device_id

    def to_payload(self) -> dict[str, Any]:
        """The operation as JSON-ready data (``from_payload`` reads it)."""
        return {
            "op_id": str(self.op_id),
            "entity": str(self.entity),
            "entity_id": str(self.entity_id),
            "field": self.field,
            "value": self.value,
            "hlc": str(self.hlc),
        }

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        """Read an operation written by ``to_payload``.

        Raises:
            ValidationException: If something is missing or malformed.
        """
        try:
            return cls(
                op_id=UUID(data["op_id"]),
                entity=SyncEntity(data["entity"]),
                entity_id=UUID(data["entity_id"]),
                field=data["field"],
                value=data["value"],
                hlc=Hlc.parse(data["hlc"]),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise ValidationException(f"Not a sync operation: {e}") from e


@dataclass(frozen=True, order=True)
class FieldKey(ValueObject):
    """A field of a row: what a clock is kept for."""

    entity: SyncEntity
    entity_id: UUID
    field: str
