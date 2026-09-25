from dataclasses import dataclass

from a_core import DTO
from b_domain.entities import Context, User
from b_domain.ports.use_case import UseCase
from c_application.use_cases.context._common import load_user, parse_user_id
from c_application.utils import find_context


@dataclass(frozen=True, kw_only=True)
class DeleteContextInputDTO(DTO):
    """Request to delete a context.

    Attributes:
        user_id (str): The owner's ID.
        context (str): The context's name or ID prefix.
    """

    user_id: str
    context: str


@dataclass(frozen=True, kw_only=True)
class DeleteContextOutputDTO(DTO):
    """What was deleted.

    Attributes:
        id (str): The deleted context's ID.
        name (str): Its name.
        was_active (bool): Whether it was the active context (the user is left
            without one).
    """

    id: str
    name: str
    was_active: bool


class DeleteContextUseCase(UseCase[DeleteContextInputDTO, DeleteContextOutputDTO]):
    """Delete a context. Its tasks stay, without a context."""

    async def execute(self, request: DeleteContextInputDTO) -> DeleteContextOutputDTO:
        """Delete the context, turning the filter off if it was the active one.

        Raises:
            ValidationException: If the user ID is invalid.
            EntityNotFound: If the user or the context does not exist.
            AmbiguousIdentifierError: If the ID prefix matches several contexts.
        """
        user_id = parse_user_id(request.user_id)

        async with self.uow as uow:
            user: User = await load_user(uow, user_id)
            contexts: list[Context] = await uow.contexts.list_by_user(user_id)
            context: Context = find_context(contexts, request.context)

            was_active: bool = user.preferences.active_context_id == context.id
            if was_active:
                user.switch_context(self.clock.now(), None)
                await uow.users.update(user)

            await uow.contexts.delete(context.id)

        return DeleteContextOutputDTO(
            id=str(context.id), name=context.name, was_active=was_active
        )
