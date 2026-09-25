from a_core.exceptions import EntityNotFound
from b_domain.ports.use_case import UseCase
from c_application.dtos.context_dtos import SwitchContextRequest


class SwitchContextUseCase(UseCase):

    async def execute(self, request: SwitchContextRequest) -> None:
        async with self.uow as uow:
            user = await uow.users.get_by_id(request.user_id)
            if not user:
                raise EntityNotFound(
                    entity_name="User", identifier=str(request.user_id)[:8]
                )

            # new_prefs = user.update_prefs(active_context_id=request.context_id)

            await uow.users.update(user)
