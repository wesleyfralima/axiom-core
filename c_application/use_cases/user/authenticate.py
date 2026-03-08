from typing import TYPE_CHECKING, Dict

from b_domain.exceptions import SecurityException
from b_domain.ports.use_case import UseCase
from c_application.dtos.auth_dtos import LoginInputDTO, TokenOutputDTO

if TYPE_CHECKING:
    from b_domain.entities import User
    from b_domain.ports.password_hasher import PasswordHasher
    from b_domain.ports.providers import TokenProvider, ClockProvider
    from b_domain.ports.unity_of_work import UnitOfWork


class AuthenticateUserUseCase(UseCase[LoginInputDTO, TokenOutputDTO]):
    """
    Orchestrates the authentication process:
    1. Identity verification.
    2. Password validation (Hashing).
    3. Token generation (JWT).
    """

    def __init__(
            self,
            uow: "UnitOfWork",
            clock: "ClockProvider",
            hasher: "PasswordHasher",
            token_provider: "TokenProvider",
    ):
        super().__init__(uow, clock)
        self.hasher = hasher
        self.token_provider = token_provider

    async def execute(self, dto: LoginInputDTO) -> TokenOutputDTO:
        """
        Validates credentials and issues an access token.
        """
        async with self.uow:
            # 1. Busca (Identidade)
            user: "User" = await self.uow.users.get_by_username(dto.username)

            # 2. Validação (Segurança)
            # O hasher.verify protege contra timing attacks e vazamento de hashes crus
            if not user or not self.hasher.verify(dto.password, user.password_hash):
                # Erro genérico para evitar enumeração de usuários
                raise SecurityException("Usuário ou senha inválidos.")

            # 3. Payload do Token (Contrato JWT)
            # Usamos o 'sub' para o ID e incluímos claims úteis para o Frontend
            payload: Dict[str, str] = {
                "sub": str(user.id),
                "username": user.username,
                "iat": str(int(self.clock.now().timestamp()))  # Issued At
            }

        # 4. Geração via Provider
        token: str = self.token_provider.create_access_token(payload)

        return TokenOutputDTO(
            access_token=token,
            token_type="bearer"
        )
