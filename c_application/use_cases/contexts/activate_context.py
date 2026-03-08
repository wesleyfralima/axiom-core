from b_domain.ports.use_case import UseCase


class ActivateContextUseCase(UseCase[UUID, None]):

    async def execute(self, context_id: UUID) -> None:

        async with self.uow:

            # 1. Desativa todos os contextos do usuário
            user_id = self.current_user.id  # Assumindo contexto de auth
            await self.uow.contexts.deactivate_all_for_user(user_id)

            # 2. Ativa o contexto específico
            context = await self.uow.contexts.get_by_id(context_id)
            if context:
                context.is_active = True
                await self.uow.contexts.update(context)

            await self.uow.commit()
