from dataclasses import dataclass

from a_core import DTO
from a_core.exceptions import ValidationException
from b_domain.entities import Context, User
from b_domain.exceptions import ContextNameTakenError
from b_domain.ports.use_case import UseCase
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.mappers.context_mapper import ContextMapper
from c_application.use_cases.context._common import load_user, parse_user_id
from c_application.utils import find_context


@dataclass(frozen=True, kw_only=True)
class UpdateContextInputDTO(DTO):
    """Request to change a context; fields left as None stay as they are.

    Attributes:
        user_id (str): The owner's ID.
        context (str): The context's name or ID prefix.
        name (str | None): New name.
        icon (str | None): New icon.
        description (str | None): New description ("" clears it).
    """

    user_id: str
    context: str
    name: str | None = None
    icon: str | None = None
    description: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdateContextOutputDTO(ContextOutputDTO):
    """The context after the change."""


class UpdateContextUseCase(UseCase[UpdateContextInputDTO, UpdateContextOutputDTO]):
    """Rename a context or change its icon or description."""

    async def execute(self, request: UpdateContextInputDTO) -> UpdateContextOutputDTO:
        """Apply the changes.

        Raises:
            ValidationException: If nothing was asked to change, or a new value
                is invalid.
            EntityNotFound: If the user or the context does not exist.
            AmbiguousIdentifierError: If the ID prefix matches several contexts.
            ContextNameTakenError: If another context already has the new name.
        """
        if (
            request.name is None
            and request.icon is None
            and request.description is None
        ):
            raise ValidationException("Nothing to update.")

        user_id = parse_user_id(request.user_id)

        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            contexts: list[Context] = await uow.contexts.list_by_user(user_id)
            context: Context = find_context(contexts, request.context)

            if request.name is not None and any(
                c.matches_name(request.name) for c in contexts if c.id != context.id
            ):
                raise ContextNameTakenError(request.name.strip())

            context.update(
                self.clock.now(),
                name=request.name,
                icon=request.icon,
                description=request.description,
            )
            await uow.contexts.update(context)

        return ContextMapper.to_output(
            context,
            UpdateContextOutputDTO,
            active_context_id=user.preferences.active_context_id,
        )
