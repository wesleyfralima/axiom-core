from typing import Dict

from b_domain.entities import User
from b_domain.exceptions import SecurityException
from b_domain.ports.password_hasher import PasswordHasher
from b_domain.ports.providers import TokenProvider, ClockProvider
from b_domain.ports.unity_of_work import UnitOfWork
from b_domain.ports.use_case import UseCase
from c_application.dtos.auth_dtos import LoginInputDTO, TokenOutputDTO


class AuthenticateUserUseCase(UseCase[LoginInputDTO, TokenOutputDTO]):
    """Use case for authenticating a user.

    Orchestrates the authentication process:
    1. Identity verification.
    2. Password validation (hash comparison).
    3. Token generation (JWT).
    """

    def __init__(
            self,
            uow: UnitOfWork,
            clock: ClockProvider,
            hasher: PasswordHasher,
            token_provider: TokenProvider,
    ):
        """Initialize the authentication use case.

        Args:
            uow (UnitOfWork): Unit of Work for managing repositories and transactions.
            clock (ClockProvider): Provides current time for token claims.
            hasher (PasswordHasher): Service for verifying password hashes.
            token_provider (TokenProvider): Service for generating JWT access tokens.
        """
        super().__init__(uow, clock)
        self.hasher = hasher
        self.token_provider = token_provider

    async def execute(self, dto: LoginInputDTO) -> TokenOutputDTO:
        """Validate user credentials and issue an access token.

        Steps:
            1. Retrieve user by username.
            2. Verify password using secure hash comparison.
            3. Build JWT payload with claims.
            4. Generate access token via provider.

        Args:
            dto (LoginInputDTO): Input data containing username and password.

        Returns:
            TokenOutputDTO: Output containing the access token and token type.

        Raises:
            SecurityException: If the username does not exist or the password is invalid.
        """

        async with self.uow:

            # 1. Identity lookup
            user: User = await self.uow.users.get_by_username(dto.username)

            # 2. Security validation
            # `hasher.verify` protects against timing attacks and raw hash leaks
            if not user or not self.hasher.verify(dto.password, user.password_hash):
                # Generic error to prevent user enumeration
                raise SecurityException("Invalid username or password.")

            # 3. JWT payload
            # 'sub' is used for subject (user ID), plus useful claims for frontend
            payload: Dict[str, str] = {
                "sub": str(user.id),
                "username": user.username,
                "iat": str(int(self.clock.now().timestamp())),  # Issued At
            }

        # 4. Token generation
        token: str = self.token_provider.create_access_token(payload)

        return TokenOutputDTO(
            access_token=token,
            token_type="bearer"
        )
