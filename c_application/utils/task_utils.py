from a_core import EntityNotFound, IdPrefix
from a_core.exceptions import AmbiguousIdentifierError
from b_domain.entities import Task
from b_domain.ports.unit_of_work import UnitOfWork
from b_domain.value_objects import UserId
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


async def find_task(uow: UnitOfWork, ref: str, user_id: UserId) -> Task:
    """Find one of the user's tasks by its ID or ID prefix.

    Args:
        uow (UnitOfWork): The open unit of work.
        ref (str): A full task ID or a prefix of at least
            ``IdPrefix.MIN_LENGTH`` characters.
        user_id (UserId): The owner; other users' tasks are never matched.

    Returns:
        Task: The task found.

    Raises:
        ValidationException: If the prefix is too short.
        EntityNotFound: If nothing matches.
        AmbiguousIdentifierError: If the prefix matches several tasks.
    """
    prefix: IdPrefix = IdPrefix(ref)
    found: list[Task] = await uow.tasks.find_by_id_prefix(
        id_prefix=prefix, user_id=user_id
    )
    if not found:
        raise EntityNotFound(entity_name="Task", identifier=str(prefix))
    if len(found) > 1:
        raise AmbiguousIdentifierError(
            resource_name="tasks",
            identifier=str(prefix),
            matches=[str(t.id)[:8] for t in found],
        )
    return found[0]
