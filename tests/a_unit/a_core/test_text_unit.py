import pytest

from a_core.text import join_naturally, ordinal, ordinal_phrase

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (22, "22nd"),
        (23, "23rd"),
        (31, "31st"),
        (111, "111th"),
    ],
)
def test_ordinal(n: int, expected: str) -> None:
    assert ordinal(n) == expected


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, "first"),
        (2, "second"),
        (3, "third"),
        (21, "21st"),
        (-1, "last"),
        (-2, "second to last"),
        (-3, "third to last"),
        (-4, "4th to last"),
    ],
)
def test_ordinal_phrase(n: int, expected: str) -> None:
    assert ordinal_phrase(n) == expected


def test_ordinal_phrase_rejects_zero() -> None:
    with pytest.raises(ValueError):
        ordinal_phrase(0)


@pytest.mark.parametrize(
    ("items", "expected"),
    [([], ""), (["a"], "a"), (["a", "b"], "a and b"), (["a", "b", "c"], "a, b, and c")],
)
def test_join_naturally(items: list[str], expected: str) -> None:
    assert join_naturally(items) == expected
