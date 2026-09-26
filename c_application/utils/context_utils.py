from collections.abc import Sequence

from a_core import EntityNotFound, IdPrefix, ValidationException
from a_core.exceptions import AmbiguousIdentifierError
from b_domain.entities import Context


def find_context(contexts: Sequence[Context], ref: str) -> Context:
    """Find one of the user's contexts by name or by ID prefix.

    The name wins (ignoring case), so a context named like the start of another
    one's ID is still reachable by name.

    Args:
        contexts (Sequence[Context]): The user's contexts.
        ref (str): A context name, a full ID or an ID prefix
            (at least ``IdPrefix.MIN_LENGTH`` characters).

    Returns:
        Context: The context found.

    Raises:
        EntityNotFound: If nothing matches.
        AmbiguousIdentifierError: If the prefix matches several contexts.
    """
    key: str = ref.strip()

    for context in contexts:
        if context.matches_name(key):
            return context

    prefix: IdPrefix | None = _as_prefix(key)
    if prefix is not None:
        matches: list[Context] = [c for c in contexts if prefix.matches(c.id)]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise AmbiguousIdentifierError(
                resource_name="contexts",
                identifier=key,
                matches=[str(c.id)[:8] for c in matches],
            )

    raise EntityNotFound(entity_name="Context", identifier=key)


def _as_prefix(text: str) -> IdPrefix | None:
    """The text as an ID prefix, or None when it cannot be one (a name)."""
    try:
        return IdPrefix(text)
    except ValidationException:
        return None
