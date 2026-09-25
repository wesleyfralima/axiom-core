from collections.abc import Iterable


def ordinal_phrase(n: int) -> str:
    """Return the ordinal phrase for a number, supporting both
    positive and negative values.

    Args:
        n (int): The number to convert.

    Returns:
        str: The ordinal phrase (e.g., "first", "second to last").
    """

    if n == 0:
        return "0th"  # Fallback para segurança matemática

    abs_n: int = abs(n)

    # Mapeamento para os casos especiais de 1 a 3
    special_cases = {
        1: ("first", "last"),
        2: ("second", "second to last"),
        3: ("third", "3rd from the end"),
    }

    if abs_n in special_cases:
        pos, neg = special_cases[abs_n]
        return neg if n < 0 else pos

    # Caso padrão para números maiores
    suffix = "from the end" if n < 0 else ""
    return f"{abs_n}th {suffix}".strip()


def ordinal_weekday_phrase(n: int) -> str:
    """Return the ordinal phrase for weekdays in recurrence rules.

    Args:
        n (int): The ordinal position (positive = from start, negative = from end).

    Returns:
        str: The ordinal phrase for weekdays (e.g., "first", "second", "last").
    """
    return ordinal_phrase(n)


def join_naturally(items: Iterable[str]) -> str:
    """Join a list of strings into a natural English phrase.

    Args:
        items (Iterable[str]): The list of items to join.

    Returns:
        str: A human-readable string joined with commas and "and".
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
