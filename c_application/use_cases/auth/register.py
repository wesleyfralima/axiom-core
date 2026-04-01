from dataclasses import dataclass, field

from a_core import DTO
from b_domain.entities.user import User
from b_domain.exceptions.user import UsernameAlreadyExistsError, EmailAlreadyExistsError
from b_domain.ports.password_hasher import PasswordHasher
from b_domain.ports.providers import ClockProvider
from b_domain.ports.use_case import UowFactoryType, UseCase
from c_application.dtos.user_dtos import UserOutputDTO
from c_application.mappers.user_mapper import UserMapper


@dataclass(frozen=True, kw_only=True)
class RegisterUserInputDTO(DTO):
    """Input DTO for user registration requests.

    Encapsulates the data required to create a new user securely.

    Attributes:
        username (str): Desired username for the new account.
        email (str): Email address associated with the user.
        password (str): Raw password provided by the user.
            Marked as `repr=False` to avoid accidental logging.
    """
    username: str
    email: str
    password: str = field(repr=False)


@dataclass
class RegisterUserOutputDTO(UserOutputDTO):
    """Output DTO for user registration responses.

    Represents the public-facing details of a newly created user,
    including their preferences and identifiers.
    """


class RegisterUserUseCase(UseCase[RegisterUserInputDTO, RegisterUserOutputDTO]):
    """Use case for registering a new user.

    This use case orchestrates the registration process, including:
    1. Unique constraint validation (username and email).
    2. Password hashing for security.
    3. Entity creation and persistence.
    4. Output mapping for response.
    """

    def __init__(
            self,
            uow_factory: UowFactoryType,
            clock: ClockProvider,
            hasher: PasswordHasher,
    ):
        """Initialize the RegisterUserUseCase.

        Args:
            uow_factory (UowFactoryType): Unit of Work factory for managing repositories and transactions.
            clock (ClockProvider): Provides current time for entity creation.
            hasher (PasswordHasher): Service for hashing user passwords securely.
        """
        super().__init__(uow_factory, clock)
        self.hasher = hasher

    async def execute(self, dto: RegisterUserInputDTO) -> RegisterUserOutputDTO:
        """Register a new user in the system.

        Steps:
            1. Validate uniqueness of the username and email.
            2. Hash the provided password securely.
            3. Create a new User entity via factory method.
            4. Persist the entity in the repository.
            5. Map the entity to an output DTO.

        Args:
            dto (RegisterUserInputDTO): Input data containing username, email, and password.

        Returns:
            RegisterUserOutputDTO: Output data representing the newly created user.

        Raises:
            UsernameAlreadyExistsError: If the username is already in use.
            EmailAlreadyExistsError: If the email is already in use.
        """

        async with self.uow as uow:

            # 1. Business rule validation (uniqueness)
            existing_user: User | None = await uow.users.get_by_username(dto.username)
            if existing_user:
                raise UsernameAlreadyExistsError(dto.username)

            existing_user = await uow.users.get_by_email(dto.email)
            if existing_user:
                raise EmailAlreadyExistsError(dto.email)

            # 2. Security: password hashing
            password_hash: str = self.hasher.hash(dto.password)

            # 3. Entity creation via factory method
            user: User = User.create(
                now=self.clock.now(),
                username=dto.username,
                email=dto.email,
                password_hash=password_hash,
            )

            # 4. Persistence
            await uow.users.add(user)

        # 5. Centralized output mapping
        return UserMapper.to_output(
            user,
            dto_class=RegisterUserOutputDTO,
        )
