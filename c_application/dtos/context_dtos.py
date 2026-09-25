from dataclasses import dataclass

from a_core import DTO
from b_domain.value_objects import UserId
from b_domain.value_objects.identifiers import ContextId


@dataclass
class SwitchContextRequest(DTO):
    """Data Transfer Object (DTO) for switching a user's active context.

    This request is used when a user changes their current context
    (e.g., from "Work" to "Home"). A `None` value for `context_id`
    disables the context filter entirely.

    Attributes:
        user_id (UserId): Identifier of the user requesting the switch.
        context_id (Optional[ContextId]): Identifier of the new context.
            If None, the active context filter is deactivated.
    """

    user_id: UserId
    context_id: ContextId | None  # None disables the filter
