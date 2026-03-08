from typing import TYPE_CHECKING, Any, Dict

from a_core.exceptions import DomainException
from b_domain.ports.use_case import UseCase
from c_application.dtos.user_dtos import UserOutputDTO, UserPrefsInputDTO, UpdateUserPreferencesRequest
from c_application.mappers.user_mapper import UserMapper

if TYPE_CHECKING:
    from b_domain.entities.user import User


class UpdateUserPreferencesUseCase(UseCase[UserPrefsInputDTO, UserOutputDTO]):
    """
    Handles partial updates to user settings.
    Ensures that only provided fields are changed, keeping others intact.
    """

    async def execute(self, request: UpdateUserPreferencesRequest) -> UserOutputDTO:
        """
        Executes the preference update.

        Args:
            request (UpdateUserPreferencesRequest): Request object.
        """

        async with self.uow:
            # 1. Recuperação do Agregado
            user: "User" = await self.uow.users.get_by_username(request.username)
            if not user:
                raise DomainException(f"Usuário '{request.username}' não encontrado.")

            # 2. Preparação de Mudanças Parciais
            # Filtramos o que é None para permitir que o DTO seja parcial
            changes: Dict[str, Any] = {
                k: v for k, v in request.preferences.__dict__.items()
                if v is not None
            }

            # 3. Lógica de Domínio (Delegada à Entidade)
            # A entidade User criará um novo UserPrefs usando replace() internamente
            user.update_prefs(
                now=self.clock.now(),
                **changes
            )

            # 4. Persistência
            # O repositório salva o estado completo do objeto de preferências
            await self.uow.users.update(user)

        # 5. Mapeamento de Saída
        return UserMapper.to_output(user)
