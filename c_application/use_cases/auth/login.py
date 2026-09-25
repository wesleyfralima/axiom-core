from dataclasses import dataclass, field

from a_core import DTO
from b_domain.entities import User
from b_domain.exceptions.security import InvalidCredentialsError
from b_domain.ports.password_hasher import PasswordHasher
from b_domain.ports.providers import ClockProvider, TokenProvider
from b_domain.ports.use_case import UowFactoryType, UseCase


@dataclass(frozen=True)
class LoginInputDTO(DTO):
    """Input DTO for user login requests.

    Encapsulates the credentials provided by the user during
    the authentication process.

    Attributes:
        username (str): The username of the user attempting to log in.
        password (str): The raw password provided by the user.
            Marked as `repr=False` to avoid accidental logging.
    """

    username: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class LoginOutputDTO(DTO):
    """Output DTO for successful authentication responses.

    Represents the result of a successful login, containing
    the generated access token and its type.

    Attributes:
        access_token (str): The JWT access token issued to the user.
        token_type (str): The type of token, typically "bearer".
    """

    access_token: str
    token_type: str = "bearer"


class LoginUseCase(UseCase[LoginInputDTO, LoginOutputDTO]):
    """Use case for authenticating a user.

    This use case orchestrates the authentication process:
    1. Identity verification (lookup by username).
    2. Password validation using secure hash comparison.
    3. Token generation (JWT) with claims for session management.
    """

    def __init__(
        self,
        uow_factory: UowFactoryType,
        clock: ClockProvider,
        hasher: PasswordHasher,
        token_provider: TokenProvider,
    ):
        """Initialize the authentication use case.

        Args:
            uow_factory (UowFactoryType): Unit of Work factory for managing
                repositories and transactions.
            clock (ClockProvider): Provides current time for token claims.
            hasher (PasswordHasher): Service for verifying password hashes securely.
            token_provider (TokenProvider): Service for generating JWT access tokens.
        """
        super().__init__(uow_factory, clock)
        self.hasher = hasher
        self.token_provider = token_provider

    async def execute(self, dto: LoginInputDTO) -> LoginOutputDTO:
        """Validate user credentials and issue an access token.

        Steps:
            1. Retrieve user by username.
            2. Verify password using secure hash comparison.
            3. Build JWT payload with claims.
            4. Generate access token via provider.

        Args:
            dto (LoginInputDTO): Input data containing username and password.

        Returns:
            LoginOutputDTO: Output containing the access token and token type.

        Raises:
            InvalidCredentialsError: If the username does not exist or the
                password is invalid.
        """

        async with self.uow as uow:

            # 1. Identity lookup
            user: User | None = await uow.users.get_by_username(dto.username)

            if not user or not user.password_hash:
                raise InvalidCredentialsError()

            # 2. Security validation
            if not self.hasher.verify(dto.password, user.password_hash):
                # Generic error to prevent user enumeration
                raise InvalidCredentialsError()

            # 3. JWT payload
            payload: dict[str, str] = {
                "sub": str(user.id),  # Subject claim (user ID)
                "username": user.username,
                "iat": str(int(self.clock.now().timestamp())),  # Issued At
            }

        # 4. Token generation
        token: str = self.token_provider.create_access_token(payload)

        return LoginOutputDTO(access_token=token, token_type="bearer")
