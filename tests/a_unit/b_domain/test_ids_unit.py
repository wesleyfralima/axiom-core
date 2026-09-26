from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest

from a_core.ddd.identities import IdPrefix, UniqueId
from a_core.exceptions import ValidationException
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

    with pytest.raises(FrozenInstanceError):
        uid.value = uuid4()  # type: ignore[misc]


# ============================================================
# Group 2: TaskId Behavior
# ============================================================


def test_task_id_is_unique_id() -> None:
    """Ensure TaskId is a UniqueId and holds a UUID value."""

    tid: TaskId = TaskId()
    assert isinstance(tid, UniqueId)
    assert isinstance(tid.value, UUID)


# ============================================================
# IdPrefix: dashes and case do not count
# ============================================================

_ID = "45e45de9-5581-44bf-bca8-67f208bd1bff"


@pytest.mark.parametrize(
    "typed",
    [
        "45e4",
        "45e45de9",
        "45e45de9-55",
        "45E45DE95581",
        "45e45de9558144bfbca867f208bd1bff",
        _ID,
    ],
)
def test_a_prefix_matches_with_or_without_dashes(typed: str) -> None:
    prefix = IdPrefix(typed)

    assert prefix.matches(_ID)
    assert prefix.matches(UUID(_ID))
    assert not prefix.matches("ffff0000-0000-0000-0000-000000000000")


@pytest.mark.parametrize(
    ("typed", "message"),
    [
        ("abc", "at least 4"),
        ("4-5-e", "at least 4"),
        ("work", "not an ID"),
        (_ID + "0", "cannot exceed 36"),
    ],
)
def test_what_is_not_a_prefix(typed: str, message: str) -> None:
    with pytest.raises(ValidationException, match=message):
        IdPrefix(typed)
