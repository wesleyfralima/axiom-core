from dataclasses import dataclass

from a_core import DTO
from b_domain.entities import Context, User
from b_domain.ports.use_case import UseCase
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.mappers.context_mapper import ContextMapper
from c_application.use_cases.context._common import load_user, parse_user_id
from c_application.utils import find_context


@dataclass(frozen=True, kw_only=True)
class SwitchContextInputDTO(DTO):
    """Request to change the active context.

    Attributes:
        user_id (str): The user's ID.
        context (str | None): The new context's name or ID prefix; None turns
            the context filter off.
    """

    user_id: str
    context: str | None


@dataclass(frozen=True, kw_only=True)
class SwitchContextOutputDTO(DTO):
    """The switch's result.

    Attributes:
        active (ContextOutputDTO | None): The active context now (None: off).
        previous (ContextOutputDTO | None): The one before, if it still exists.
        changed (bool): False when the requested context was already active.
    """

    active: ContextOutputDTO | None
    previous: ContextOutputDTO | None
    changed: bool


class SwitchContextUseCase(UseCase[SwitchContextInputDTO, SwitchContextOutputDTO]):
    """Change the user's active context (``UserPrefs.active_context_id``).

    New tasks inherit the active context. A real change emits
    ``ContextSwitchedEvent``.
    """

    async def execute(self, request: SwitchContextInputDTO) -> SwitchContextOutputDTO:
        """Switch the context.

        Raises:
            ValidationException: If the user ID is invalid.
            EntityNotFound: If the user or the context does not exist.
            AmbiguousIdentifierError: If the ID prefix matches several contexts.
        """
        user_id = parse_user_id(request.user_id)

        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            contexts: list[Context] = await uow.contexts.list_by_user(user_id)

            target: Context | None = (
                find_context(contexts, request.context)
                if request.context is not None
                else None
            )
            previous: Context | None = next(
                (c for c in contexts if c.id == user.preferences.active_context_id),
                None,
            )

            changed: bool = user.switch_context(
                self.clock.now(), target.id if target else None
            )
            if changed:
                await uow.users.update(user)

        active_id = user.preferences.active_context_id
        return SwitchContextOutputDTO(
            active=(
                ContextMapper.to_output(target, ContextOutputDTO, active_id)
                if target
                else None
            ),
            previous=(
                ContextMapper.to_output(previous, ContextOutputDTO, active_id)
                if previous
                else None
            ),
            changed=changed,
        )
