from dataclasses import dataclass, field

from a_core import DTO
from b_domain.entities import Context, User
from b_domain.ports.use_case import UseCase
from c_application.dtos.context_dtos import ContextOutputDTO
from c_application.mappers.context_mapper import ContextMapper
from c_application.use_cases.context._common import load_user, parse_user_id


@dataclass(frozen=True, kw_only=True)
class ListContextsInputDTO(DTO):
    """Request for the user's contexts.

    Attributes:
        user_id (str): The owner's ID.
    """

    user_id: str


@dataclass(frozen=True, kw_only=True)
class ListContextsOutputDTO(DTO):
    """The user's contexts, sorted by name.

    Attributes:
        contexts (list[ContextOutputDTO]): The contexts; the active one has
            ``is_active=True``.
    """

    contexts: list[ContextOutputDTO] = field(default_factory=list)


class ListContextsUseCase(UseCase[ListContextsInputDTO, ListContextsOutputDTO]):
    """List the user's contexts, marking the active one."""

    async def execute(self, request: ListContextsInputDTO) -> ListContextsOutputDTO:
        """List the contexts.

        Raises:
            ValidationException: If the user ID is invalid.
            EntityNotFound: If the user does not exist.
        """
        user_id = parse_user_id(request.user_id)

        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            contexts: list[Context] = await uow.contexts.list_by_user(user_id)

        active = user.preferences.active_context_id
        return ListContextsOutputDTO(
            contexts=[
                ContextMapper.to_output(c, ContextOutputDTO, active_context_id=active)
                for c in contexts
            ]
        )
