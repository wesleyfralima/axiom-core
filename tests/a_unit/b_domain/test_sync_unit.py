"""Sync between devices: the clock, the operation and the merge rule."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from a_core.exceptions import ValidationException
from b_domain.services.sync_merge import MergePlan, plan_merge
from b_domain.value_objects.sync import (
    CREATED,
    DELETED,
    FieldKey,
    Hlc,
    SyncEntity,
    SyncOperation,
)

pytestmark = pytest.mark.unit

MINT = UUID("11111111111111111111111111111111")
PHONE = UUID("22222222222222222222222222222222")
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)

TASK = SyncEntity.TASK
CONTEXT = SyncEntity.CONTEXT


def _hlc(ms: int, counter: int = 0, device: UUID = MINT) -> Hlc:
    return Hlc(wall_ms=ms, counter=counter, device_id=device.hex)


def _key(entity_id: UUID, name: str, entity: SyncEntity = TASK) -> FieldKey:
    return FieldKey(entity=entity, entity_id=entity_id, field=name)


def _edit(
    entity_id: UUID, name: str, value: Any, hlc: Hlc, entity: SyncEntity = TASK
) -> SyncOperation:
    return SyncOperation(
        entity=entity, entity_id=entity_id, field=name, value=value, hlc=hlc
    )


# -------------------------------------------------------------------- clock


def test_a_clock_as_text_reads_back_and_sorts_like_the_clock() -> None:
    clocks = [
        _hlc(NOW_MS, 2, PHONE),
        _hlc(NOW_MS, 2, MINT),
        _hlc(NOW_MS - 1, 99_999, PHONE),
        _hlc(NOW_MS, 10, MINT),
        _hlc(0, 0, MINT),
    ]

    assert [Hlc.parse(str(c)) for c in clocks] == clocks
    assert sorted(str(c) for c in clocks) == [str(c) for c in sorted(clocks)]
    assert str(_hlc(5, 3)) == f"000000000000005-00003-{MINT.hex}"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "1-2-3",
        f"00000000000000x-00003-{MINT.hex}",
        f"000000000000005-3-{MINT.hex}",
        "000000000000005-00003-NOTHEX",
        f"000000000000005-00003-{MINT.hex}-extra",
    ],
)
def test_text_that_is_not_a_clock_is_refused(text: str) -> None:
    with pytest.raises(ValidationException):
        Hlc.parse(text)


@pytest.mark.parametrize(
    ("ms", "counter", "device"),
    [
        (-1, 0, MINT.hex),
        (10**15, 0, MINT.hex),
        (0, -1, MINT.hex),
        (0, 100_000, MINT.hex),
        (0, 0, str(MINT)),
        (0, 0, "AB" * 16),
    ],
)
def test_a_clock_out_of_range_is_refused(ms: int, counter: int, device: str) -> None:
    with pytest.raises(ValidationException):
        Hlc(wall_ms=ms, counter=counter, device_id=device)


def test_the_device_breaks_a_tie() -> None:
    assert _hlc(NOW_MS, 1, MINT) < _hlc(NOW_MS, 1, PHONE)
    assert _hlc(NOW_MS, 1, PHONE) < _hlc(NOW_MS, 2, MINT)
    assert _hlc(NOW_MS, 9, PHONE) < _hlc(NOW_MS + 1, 0, MINT)


def test_a_tick_takes_the_time_when_it_moved_on() -> None:
    clock = Hlc.start(MINT)

    ticked = clock.tick(NOW)

    assert ticked == _hlc(NOW_MS, 0)


def test_a_tick_never_goes_back_when_the_time_does() -> None:
    clock = _hlc(NOW_MS, 4)

    assert clock.tick(NOW) == _hlc(NOW_MS, 5)
    assert clock.tick(NOW - timedelta(hours=1)) == _hlc(NOW_MS, 5)


def test_a_full_counter_moves_to_the_next_millisecond() -> None:
    assert _hlc(NOW_MS, Hlc.MAX_COUNTER).tick(NOW) == _hlc(NOW_MS + 1, 0)


def test_receiving_a_later_clock_moves_past_it() -> None:
    mine = _hlc(NOW_MS - 10, 7, MINT)
    theirs = _hlc(NOW_MS + 5_000, 3, PHONE)

    moved = mine.receive(theirs, NOW)

    assert moved == _hlc(NOW_MS + 5_000, 4, MINT)
    assert moved > theirs
    assert moved.tick(NOW) > theirs


@pytest.mark.parametrize(
    ("mine", "theirs", "expected"),
    [
        # Same millisecond everywhere: past both counters
        (_hlc(NOW_MS, 3), _hlc(NOW_MS, 8, PHONE), _hlc(NOW_MS, 9)),
        # Mine is the latest
        (_hlc(NOW_MS + 9, 3), _hlc(NOW_MS, 8, PHONE), _hlc(NOW_MS + 9, 4)),
        # The time is the latest
        (_hlc(NOW_MS - 9, 3), _hlc(NOW_MS - 5, 8, PHONE), _hlc(NOW_MS, 0)),
    ],
)
def test_receiving_a_clock(mine: Hlc, theirs: Hlc, expected: Hlc) -> None:
    assert mine.receive(theirs, NOW) == expected


def test_a_clock_far_ahead_of_the_time_is_noticed() -> None:
    day = timedelta(days=1)

    assert _hlc(NOW_MS + 86_400_001).is_ahead_of(NOW, day)
    assert not _hlc(NOW_MS + 86_400_000).is_ahead_of(NOW, day)
    assert not _hlc(NOW_MS - 1).is_ahead_of(NOW, day)


def test_a_clock_needs_an_aware_time() -> None:
    with pytest.raises(ValidationException):
        Hlc.start(MINT).tick(NOW.replace(tzinfo=None))


# ---------------------------------------------------------------- operation


def test_an_operation_travels_as_json_and_back() -> None:
    task = uuid4()
    op = SyncOperation.created(
        _hlc(NOW_MS, 1), TASK, task, {"title": "Pay the bill", "tags": ["home"]}
    )

    back = SyncOperation.from_payload(op.to_payload())

    assert back == op
    assert back.device_id == MINT.hex
    assert op.to_payload()["hlc"] == str(op.hlc)


@pytest.mark.parametrize(
    "change",
    [
        {"op_id": "nope"},
        {"entity": "project"},
        {"hlc": "yesterday"},
        {"field": "Title"},
        {"entity_id": None},
    ],
)
def test_a_malformed_payload_is_refused(change: dict[str, Any]) -> None:
    payload = _edit(uuid4(), "title", "x", _hlc(NOW_MS)).to_payload() | change

    with pytest.raises(ValidationException):
        SyncOperation.from_payload(payload)


def test_a_payload_missing_a_part_is_refused() -> None:
    payload = _edit(uuid4(), "title", "x", _hlc(NOW_MS)).to_payload()
    del payload["value"]

    with pytest.raises(ValidationException):
        SyncOperation.from_payload(payload)


@pytest.mark.parametrize("name", ["", "Title", "due date", "_secret", "1st", "x" * 70])
def test_a_field_must_be_a_name(name: str) -> None:
    with pytest.raises(ValidationException):
        _edit(uuid4(), name, "x", _hlc(NOW_MS))


@pytest.mark.parametrize("value", [None, "row", ["title"], {"_deleted": True}, {1: 2}])
def test_a_new_row_holds_a_dict_of_fields(value: Any) -> None:
    with pytest.raises(ValidationException):
        SyncOperation(
            entity=TASK, entity_id=uuid4(), field=CREATED, value=value, hlc=_hlc(1)
        )


def test_the_order_of_the_kinds_of_row() -> None:
    assert SyncEntity.USER.rank < SyncEntity.CONTEXT.rank < SyncEntity.TASK.rank
    assert SyncEntity.TASK.rank < SyncEntity.TIME_ENTRY.rank


# -------------------------------------------------------------------- merge


def test_nothing_to_merge() -> None:
    assert plan_merge([], {}) == MergePlan()


def test_a_new_row_takes_every_field_and_its_later_edits() -> None:
    task = uuid4()
    create = SyncOperation.created(
        _hlc(NOW_MS), TASK, task, {"title": "Draft", "priority": "low"}
    )
    edit = _edit(task, "title", "Final", _hlc(NOW_MS + 1))

    plan = plan_merge([edit, create], {})

    [row] = plan.rows
    assert row.create == {"title": "Final", "priority": "low"}
    assert row.fields == {}
    assert plan.clocks == {
        _key(task, CREATED): create.hlc,
        _key(task, "title"): edit.hlc,
        _key(task, "priority"): create.hlc,
    }
    assert plan.dropped == []
    assert plan.latest == edit.hlc


def test_edits_on_different_fields_both_stay() -> None:
    task = uuid4()
    known = {_key(task, CREATED): _hlc(NOW_MS), _key(task, "title"): _hlc(NOW_MS)}
    title = _edit(task, "title", "On the Mint", _hlc(NOW_MS + 5, 0, MINT))
    due = _edit(task, "due_date", {"value": "2026-10-01"}, _hlc(NOW_MS + 2, 0, PHONE))

    [row] = plan_merge([title, due], known).rows

    assert row.create is None
    assert row.fields == {"title": "On the Mint", "due_date": {"value": "2026-10-01"}}


def test_the_same_field_keeps_the_latest_and_drops_the_rest() -> None:
    task = uuid4()
    known = {_key(task, CREATED): _hlc(NOW_MS)}
    old = _edit(task, "title", "Old", _hlc(NOW_MS + 1, 0, PHONE))
    new = _edit(task, "title", "New", _hlc(NOW_MS + 2, 0, MINT))

    plan = plan_merge([new, old], known)

    assert plan.rows[0].fields == {"title": "New"}
    assert plan.dropped == [old]


def test_an_edit_older_than_what_the_device_has_is_dropped() -> None:
    task = uuid4()
    known = {_key(task, CREATED): _hlc(NOW_MS), _key(task, "title"): _hlc(NOW_MS + 9)}
    late = _edit(task, "title", "Late", _hlc(NOW_MS + 3, 0, PHONE))

    plan = plan_merge([late], known)

    assert plan.rows == []
    assert plan.clocks == {}
    assert plan.dropped == [late]


def test_the_same_operation_twice_changes_nothing() -> None:
    task = uuid4()
    op = _edit(task, "title", "Once", _hlc(NOW_MS + 1))

    first = plan_merge([op, op], {_key(task, CREATED): _hlc(NOW_MS)})
    again = plan_merge([op], {_key(task, CREATED): _hlc(NOW_MS)} | first.clocks)

    assert first.rows[0].fields == {"title": "Once"}
    assert first.dropped == [op]
    assert again.rows == []
    assert again.dropped == [op]


def test_a_deleted_row_takes_no_more_changes() -> None:
    ctx = uuid4()
    known = {_key(ctx, DELETED, CONTEXT): _hlc(NOW_MS)}
    rename = _edit(ctx, "name", "Home", _hlc(NOW_MS + 9, 0, PHONE), CONTEXT)

    plan = plan_merge([rename], known)

    assert plan.rows == []
    assert plan.dropped == [rename]


def test_a_deletion_wins_over_edits_in_the_same_batch() -> None:
    ctx = uuid4()
    known = {_key(ctx, CREATED, CONTEXT): _hlc(NOW_MS)}
    delete = SyncOperation.deleted(_hlc(NOW_MS + 1, 0, MINT), CONTEXT, ctx)
    rename = _edit(ctx, "name", "Home", _hlc(NOW_MS + 9, 0, PHONE), CONTEXT)

    plan = plan_merge([rename, delete], known)

    [row] = plan.rows
    assert row.delete
    assert row.fields == {}
    assert plan.clocks == {_key(ctx, DELETED, CONTEXT): delete.hlc}
    assert plan.dropped == [rename]


def test_a_task_restored_after_its_delete_comes_back() -> None:
    task = uuid4()
    known = {
        _key(task, CREATED): _hlc(NOW_MS),
        _key(task, "deleted_at"): _hlc(NOW_MS + 1, 0, MINT),
    }
    restore = _edit(task, "deleted_at", None, _hlc(NOW_MS + 2, 0, PHONE))

    [row] = plan_merge([restore], known).rows

    assert row.fields == {"deleted_at": None}


def test_a_row_created_on_two_devices_merges_field_by_field() -> None:
    task = uuid4()
    here = _hlc(NOW_MS + 1, 0, MINT)
    known = {
        _key(task, CREATED): here,
        _key(task, "title"): here,
        _key(task, "priority"): here,
    }
    there = SyncOperation.created(
        _hlc(NOW_MS + 2, 0, PHONE), TASK, task, {"title": "Pay", "priority": "high"}
    )
    older = SyncOperation.created(_hlc(NOW_MS, 0, PHONE), TASK, task, {"title": "Old"})

    plan = plan_merge([there, older], known)

    [row] = plan.rows
    assert row.create is None
    assert row.fields == {"title": "Pay", "priority": "high"}
    # The row was first created by the older one: what a unique name follows
    assert plan.clocks[_key(task, CREATED)] == older.hlc
    assert plan.dropped == []


def test_a_later_creation_of_a_row_that_changes_nothing_is_dropped() -> None:
    task = uuid4()
    here = _hlc(NOW_MS + 5)
    known = {_key(task, CREATED): here, _key(task, "title"): here}
    there = SyncOperation.created(
        _hlc(NOW_MS + 1, 0, PHONE), TASK, task, {"title": "x"}
    )
    # …and a later one that loses its only field to an edit in the batch
    later = SyncOperation.created(
        _hlc(NOW_MS + 6, 0, PHONE), TASK, task, {"title": "y"}
    )
    edit = _edit(task, "title", "z", _hlc(NOW_MS + 7))

    plan = plan_merge([later, edit], known)
    assert plan.rows[0].fields == {"title": "z"}
    assert plan.dropped == [later]

    plan = plan_merge([there], known | {_key(task, CREATED): _hlc(NOW_MS)})
    assert plan.rows == []
    assert plan.dropped == [there]


def test_rows_come_after_the_rows_they_point_to() -> None:
    task, ctx, entry = uuid4(), uuid4(), uuid4()
    ops = [
        SyncOperation.created(_hlc(NOW_MS + 3), SyncEntity.TIME_ENTRY, entry, {}),
        SyncOperation.created(_hlc(NOW_MS + 2), TASK, task, {"context_id": str(ctx)}),
        SyncOperation.created(_hlc(NOW_MS + 1), CONTEXT, ctx, {"name": "Work"}),
    ]

    plan = plan_merge(reversed(ops), {})

    assert [row.entity_id for row in plan.rows] == [ctx, task, entry]


# ---------------------------------------------------------- convergence


def _apply(
    rows: dict[UUID, dict[str, Any]],
    clocks: dict[FieldKey, Hlc],
    ops: list[SyncOperation],
) -> None:
    """A device's data, applying a plan as a database would."""
    plan = plan_merge(ops, clocks)
    for row in plan.rows:
        if row.delete:
            rows.pop(row.entity_id, None)
        elif row.create is not None:
            rows[row.entity_id] = dict(row.create)
        elif row.entity_id in rows:
            rows[row.entity_id].update(row.fields)
    clocks.update(plan.clocks)


@pytest.mark.parametrize("seed", range(20))
def test_devices_that_receive_the_same_changes_end_the_same(seed: int) -> None:
    rng = random.Random(seed)
    tasks = [uuid4() for _ in range(3)]
    devices = [MINT, PHONE, UUID("33333333333333333333333333333333")]
    ops: list[SyncOperation] = [
        SyncOperation.created(
            _hlc(NOW_MS, 0, devices[0]), TASK, task, {"title": "t", "priority": "low"}
        )
        for task in tasks
    ]
    for n in range(40):
        ops.append(
            _edit(
                rng.choice(tasks),
                rng.choice(["title", "priority", "deleted_at"]),
                n,
                _hlc(NOW_MS + rng.randint(1, 10), n, rng.choice(devices)),
            )
        )
    creates, edits = ops[:3], ops[3:]

    results = []
    for _ in range(4):
        rows: dict[UUID, dict[str, Any]] = {}
        clocks: dict[FieldKey, Hlc] = {}
        _apply(rows, clocks, creates)
        shuffled = edits[:]
        rng.shuffle(shuffled)
        # Arriving in batches of any size, in any order
        while shuffled:
            size = rng.randint(1, 8)
            _apply(rows, clocks, shuffled[:size])
            shuffled = shuffled[size:]
        results.append(rows)

    assert all(result == results[0] for result in results)
