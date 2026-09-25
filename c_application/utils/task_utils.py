from b_domain.value_objects.recurrences import RecurrenceRule


def format_task_recurrence(recurrence: RecurrenceRule | None) -> str | None:
    """Format a recurrence rule into a human-readable sentence.

    The rule describes its own pattern; this function adds the end condition.

    Args:
        recurrence: The rule to describe.

    Returns:
        A sentence such as "Every 2 weeks on Mondays, until 2026-12-31.", or
        None when there is no rule.
    """

    if recurrence is None:
        return None

    parts: list[str] = [recurrence.describe_pattern()]

    if recurrence.count:
        times: str = "occurrence" if recurrence.count == 1 else "occurrences"
        parts.append(f"for {recurrence.count} {times}")
    elif recurrence.end_date:
        parts.append(f"until {recurrence.end_date.materialize():%Y-%m-%d}")

    return ", ".join(parts) + "."
