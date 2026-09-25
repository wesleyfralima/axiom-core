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


def test_timezone_must_exist() -> None:
    assert UserPrefs().update(timezone="America/Sao_Paulo").timezone == (
        "America/Sao_Paulo"
    )
    with pytest.raises(InvalidValueError, match="time zone"):
        UserPrefs().update(timezone="Mars/Olympus")


@pytest.mark.parametrize(
    ("key", "good", "bad"),
    [("week_start", "Sunday", "friday"), ("theme", "DARK", "neon")],
)
def test_closed_choices(key: str, good: str, bad: str) -> None:
    assert getattr(UserPrefs().update(**{key: good}), key) == good.lower()
    with pytest.raises(InvalidValueError, match="Valid options"):
        UserPrefs().update(**{key: bad})


def test_working_hours_are_hours_of_the_day() -> None:
    assert UserPrefs().update(working_hours_start=8).working_hours_start == 8
    with pytest.raises(InvalidValueError):
        UserPrefs().update(working_hours_end=24)
