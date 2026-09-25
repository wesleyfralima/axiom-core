from dataclasses import dataclass

from a_core import DTO
from b_domain.entities import Context, User
from b_domain.exceptions import ContextNameTakenError
from b_domain.ports.use_case import UseCase
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.mappers.context_mapper import ContextMapper
from c_application.use_cases.context._common import load_user, parse_user_id


@dataclass(frozen=True, kw_only=True)
class CreateContextInputDTO(DTO):
    """Request to create a context.

    Attributes:
        user_id (str): The owner's ID.
        name (str): The context's name, unique per user (ignoring case).
        icon (str | None): Emoji or symbol; defaults to 🏷️.
        description (str | None): Optional descriptive text.
    """

    user_id: str
    name: str
    icon: str | None = None
    description: str | None = None


@dataclass(frozen=True, kw_only=True)
class CreateContextOutputDTO(ContextOutputDTO):
    """The context just created."""


class CreateContextUseCase(UseCase[CreateContextInputDTO, CreateContextOutputDTO]):
    """Create a context for the user."""

    async def execute(self, request: CreateContextInputDTO) -> CreateContextOutputDTO:
        """Create the context.

        Raises:
            ValidationException: If the user ID, the name or the icon is invalid.
            EntityNotFound: If the user does not exist.
            ContextNameTakenError: If the user already has a context with that
                name (ignoring case).
        """
        user_id = parse_user_id(request.user_id)
        context: Context = Context.create(
            now=self.clock.now(),
            user_id=user_id,
            name=request.name,
            icon=request.icon,
            description=request.description,
        )

        async with self.uow as uow:
            user: User = await load_user(uow, user_id)

            existing: list[Context] = await uow.contexts.list_by_user(user_id)
            if any(c.matches_name(context.name) for c in existing):
                raise ContextNameTakenError(context.name)

            await uow.contexts.add(context)

        return ContextMapper.to_output(
            context,
            CreateContextOutputDTO,
            active_context_id=user.preferences.active_context_id,
        )
