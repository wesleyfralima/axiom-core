from uuid import UUID, uuid4

import pytest

from a_core.ddd.identities import UniqueId
from b_domain.value_objects.identifiers import TaskId

# ============================================================
# Group 1: UniqueId Behavior
# ============================================================


def test_unique_id_generates_uuid_by_default() -> None:
    """Ensure UniqueId generates a UUID by default."""

    uid: UniqueId = UniqueId()
    assert isinstance(uid.value, UUID)


def test_unique_id_str_returns_uuid_string() -> None:
    """Ensure str(UniqueId) returns the UUID string representation."""

    uid: UniqueId = UniqueId()
    assert str(uid) == str(uid.value)


def test_unique_id_values_are_unique() -> None:
    """Ensure two UniqueId instances generate distinct values."""

    uid1: UniqueId = UniqueId()
    uid2: UniqueId = UniqueId()

    assert uid1 != uid2
    assert uid1.value != uid2.value


def test_unique_id_is_immutable() -> None:
    """Ensure UniqueId value cannot be reassigned after initialization."""

    uid: UniqueId = UniqueId()

    with pytest.raises(Exception):
        uid.value = uuid4()  # type: ignore[misc] # noqa


# ============================================================
# Group 2: TaskId Behavior
# ============================================================


def test_task_id_is_unique_id() -> None:
    """Ensure TaskId is a UniqueId and holds a UUID value."""

    tid: TaskId = TaskId()
    assert isinstance(tid, UniqueId)
    assert isinstance(tid.value, UUID)
