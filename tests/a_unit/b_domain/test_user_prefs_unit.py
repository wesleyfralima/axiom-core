import pytest

from a_core.exceptions import InvalidValueError
from b_domain.entities import UserPrefs

pytestmark = pytest.mark.unit


def test_default_priority_preference_is_normalized() -> None:
    prefs = UserPrefs().update(default_task_priority="HIGH")

    assert prefs.default_task_priority == "high"


def test_default_priority_preference_rejects_unknown() -> None:
    with pytest.raises(InvalidValueError):
        UserPrefs().update(default_task_priority="urgent")
