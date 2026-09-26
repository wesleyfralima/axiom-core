"""The sync rule: which operations from other devices a device applies.

The same rule runs on every device, so all of them end with the same data:

- **The last writer wins, field by field.** For each field of a row the
  operation with the latest clock wins; one older than the clock the device
  keeps for that field is dropped. A title changed on one device and a due
  date on the other both stay.
- **A new row** takes every field from the batch that creates it. Created
  twice (the same ID on two devices), the second creation is an edit of each
  of its fields, by the same rule.
- **A deletion is final**: once a row is deleted, every later change to it is
  dropped. (A task's delete is not one of these: it is its ``deleted_at``
  field, so a restore can win over it.)
- The same operation received twice changes nothing: its clock does not beat
  itself.

``plan_merge`` only decides; the caller applies the plan to its data and keeps
the plan's clocks, in the same transaction.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from b_domain.value_objects.sync import (
    CREATED,
    DELETED,
    FieldKey,
    Hlc,
    SyncEntity,
    SyncOperation,
)


@dataclass(frozen=True, kw_only=True)
class RowChange:
    """What to do to one row.

    Attributes:
        entity (SyncEntity): The kind of row.
        entity_id (UUID): The row.
        create (dict[str, Any] | None): For a new row, every field.
        fields (dict[str, Any]): For an existing row, the fields to change.
        delete (bool): Delete the row (any other change is left out).
    """

    entity: SyncEntity
    entity_id: UUID
    create: dict[str, Any] | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    delete: bool = False


@dataclass(frozen=True, kw_only=True)
class MergePlan:
    """The outcome of a batch of operations.

    Attributes:
        rows (list[RowChange]): The changes, in the order to apply them: a
            row after the rows it points to (``SyncEntity.rank``), then by
            clock.
        clocks (dict[FieldKey, Hlc]): The clocks to keep from now on, for the
            fields that changed (and ``CREATED``/``DELETED`` of a row).
        dropped (list[SyncOperation]): The operations that lost, or arrived
            again.
        latest (Hlc | None): The latest clock of the batch, for the device's
            own clock to move past it (``Hlc.receive``).
    """

    rows: list[RowChange] = field(default_factory=list)
    clocks: dict[FieldKey, Hlc] = field(default_factory=dict)
    dropped: list[SyncOperation] = field(default_factory=list)
    latest: Hlc | None = None


type _RowKey = tuple[SyncEntity, UUID]


def plan_merge(
    incoming: Iterable[SyncOperation], known: Mapping[FieldKey, Hlc]
) -> MergePlan:
    """Decide what a batch of operations changes.

    Args:
        incoming (Iterable[SyncOperation]): Operations from other devices, in
            any order.
        known (Mapping[FieldKey, Hlc]): The clocks the device keeps, for (at
            least) the rows in the batch.

    Returns:
        MergePlan: The changes to apply and the clocks to keep.
    """
    by_row: dict[_RowKey, list[SyncOperation]] = defaultdict(list)
    seen: set[UUID] = set()
    dropped: list[SyncOperation] = []
    for op in incoming:
        if op.op_id in seen:
            dropped.append(op)
            continue
        seen.add(op.op_id)
        by_row[(op.entity, op.entity_id)].append(op)

    planned: list[tuple[int, Hlc, RowChange]] = []
    clocks: dict[FieldKey, Hlc] = {}
    for (entity, entity_id), ops in by_row.items():
        change: RowChange | None = _plan_row(entity, entity_id, ops, known, clocks)
        used: set[UUID] = _used_ops(ops, entity, entity_id, clocks)
        dropped.extend(op for op in ops if op.op_id not in used)
        if change is not None:
            planned.append((entity.rank, min(op.hlc for op in ops), change))

    planned.sort(key=lambda p: (p[0], p[1]))
    return MergePlan(
        rows=[change for _, _, change in planned],
        clocks=clocks,
        dropped=dropped,
        latest=max((op.hlc for ops in by_row.values() for op in ops), default=None),
    )


def _plan_row(
    entity: SyncEntity,
    entity_id: UUID,
    ops: list[SyncOperation],
    known: Mapping[FieldKey, Hlc],
    clocks: dict[FieldKey, Hlc],
) -> RowChange | None:
    """What the batch does to one row; its winning clocks go into ``clocks``."""

    def key(name: str) -> FieldKey:
        return FieldKey(entity=entity, entity_id=entity_id, field=name)

    if key(DELETED) in known:
        return None

    deletions: list[SyncOperation] = [op for op in ops if op.field == DELETED]
    if deletions:
        clocks[key(DELETED)] = min(op.hlc for op in deletions)
        return RowChange(entity=entity, entity_id=entity_id, delete=True)

    creations: list[SyncOperation] = [op for op in ops if op.field == CREATED]

    # The latest value of each field in the batch, a creation's fields
    # included
    latest: dict[str, tuple[Hlc, Any]] = {}
    for op in ops:
        pairs: Iterable[tuple[str, Any]] = (
            op.value.items() if op.field == CREATED else ((op.field, op.value),)
        )
        for name, value in pairs:
            if name not in latest or op.hlc > latest[name][0]:
                latest[name] = (op.hlc, value)

    if creations:
        first: Hlc = min(op.hlc for op in creations)
        held: Hlc | None = known.get(key(CREATED))
        if held is None or first < held:
            clocks[key(CREATED)] = first

    if creations and key(CREATED) not in known:
        for name, (hlc, _) in latest.items():
            clocks[key(name)] = hlc
        return RowChange(
            entity=entity,
            entity_id=entity_id,
            create={name: value for name, (_, value) in latest.items()},
        )

    fields: dict[str, Any] = {}
    for name, (hlc, value) in latest.items():
        mine: Hlc | None = known.get(key(name))
        if mine is None or hlc > mine:
            clocks[key(name)] = hlc
            fields[name] = value
    if not fields:
        return None
    return RowChange(entity=entity, entity_id=entity_id, fields=fields)


def _used_ops(
    ops: list[SyncOperation],
    entity: SyncEntity,
    entity_id: UUID,
    clocks: Mapping[FieldKey, Hlc],
) -> set[UUID]:
    """The operations whose clock won a field (or the row's creation or
    deletion) — the rest were dropped."""
    used: set[UUID] = set()
    for op in ops:
        names: Iterable[str] = (
            (CREATED, *op.value) if op.field == CREATED else (op.field,)
        )
        for name in names:
            won: Hlc | None = clocks.get(
                FieldKey(entity=entity, entity_id=entity_id, field=name)
            )
            if won == op.hlc:
                used.add(op.op_id)
                break
    return used
