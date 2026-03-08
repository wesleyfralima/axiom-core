from typing import TYPE_CHECKING, Optional, Dict

from b_domain.exceptions.security import ExpiredTokenError, InvalidTokenError
from b_domain.ports.use_case import UseCase
from c_application.dtos.user_dtos import UserOutputDTO
from c_application.mappers.user_mapper import UserMapper

if TYPE_CHECKING:
    from b_domain.ports.providers import TokenProvider, ClockProvider
    from b_domain.ports.unity_of_work import UnitOfWork


class GetCurrentUserFromTokenUseCase(UseCase[str, Optional[UserOutputDTO]]):
    """
    Validates an access token and retrieves the current authenticated user.
    """

    def __init__(
            self,
            uow: "UnitOfWork",
            clock: "ClockProvider",
            token_provider: "TokenProvider",
    ):
        super().__init__(uow, clock)
        self.token_provider = token_provider

    async def execute(self, token: str) -> Optional[UserOutputDTO]:
        """
        Args:
            token: The raw JWT string.
        """

        try:
            # 1. Validação técnica do Token via Provider
            payload: Dict = self.token_provider.decode_access_token(token)
        except (ExpiredTokenError, InvalidTokenError):
            return None

        username = payload.get("username")
        if not username:
            return None

        # 2. Validação de Existência e Integridade
        async with self.uow:

            user = await self.uow.users.get_by_username(username)

            if not user:
                return None

        # 3. Mapeamento de Saída
        # Usamos o UserMapper para garantir que o DTO contenha as preferências (timezone, etc)
        return UserMapper.to_output(user)
