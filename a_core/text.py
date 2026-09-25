"""Small helpers to build English phrases (ordinals, natural lists)."""

from collections.abc import Iterable

_ORDINAL_WORDS: dict[int, str] = {1: "first", 2: "second", 3: "third"}


def ordinal(n: int) -> str:
    """Return the numeric ordinal of a positive number.

    Args:
        n: The number (1 or more).

    Returns:
        The number with its English suffix: "1st", "2nd", "11th", "23rd".
    """

    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def ordinal_phrase(n: int) -> str:
    """Return the ordinal phrase of a position counted from either end.

    Positive values count from the start, negative values from the end.

    Args:
        n: The position; cannot be 0.

    Returns:
        "first", "second", "third", "4th", …; "last", "second to last",
        "third to last", "4th to last", ….

    Raises:
        ValueError: If ``n`` is 0.
    """

    if n == 0:
        raise ValueError("A position cannot be 0.")
    if n == -1:
        return "last"

    abs_n: int = abs(n)
    word: str = _ORDINAL_WORDS.get(abs_n) or ordinal(abs_n)
    return f"{word} to last" if n < 0 else word


def join_naturally(items: Iterable[str]) -> str:
    """Join strings into a natural English list.

    Args:
        items: The items to join.

    Returns:
        "", "a", "a and b" or "a, b, and c".
    """

    items_list: list[str] = list(items)
    length: int = len(items_list)

    if length == 0:
        return ""
    if length == 1:
        return items_list[0]
    if length == 2:
        return f"{items_list[0]} and {items_list[1]}"

    return f"{', '.join(items_list[:-1])}, and {items_list[-1]}"
