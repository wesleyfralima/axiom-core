from a_core.exceptions import DomainException
from b_domain.entities.user import User
from b_domain.ports.password_hasher import PasswordHasher
from b_domain.ports.providers import ClockProvider
from b_domain.ports.use_case import UseCase, UowFactoryType
from c_application.dtos.user_dtos import CreateUserInputDTO, UserOutputDTO
from c_application.mappers.user_mapper import UserMapper


class CreateUserUseCase(UseCase[CreateUserInputDTO, UserOutputDTO]):
    """Use case for registering a new user.

    Orchestrates the registration process, including:
    1. Unique constraint validation (username).
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
        """Initialize the CreateUserUseCase.

        Args:
            uow_factory (UowFactoryType): Unit of Work factory for managing repositories and transactions.
            clock (ClockProvider): Provides current time for entity creation.
            hasher (PasswordHasher): Service for hashing user passwords.
        """
        super().__init__(uow_factory, clock)
        self.hasher = hasher

    async def execute(self, dto: CreateUserInputDTO) -> UserOutputDTO:
        """Register a new user in the system.

        Steps:
            1. Validate uniqueness of the username.
            2. Hash the provided password securely.
            3. Create a new User entity via factory method.
            4. Persist the entity in the repository.
            5. Map the entity to an output DTO.

        Args:
            dto (CreateUserInputDTO): Input data containing username and password.

        Returns:
            UserOutputDTO: Output data representing the newly created user.

        Raises:
            DomainException: If the username is already in use.
        """

        async with self.uow as uow:

            # 1. Business rule validation (uniqueness)
            existing_user: User | None = await uow.users.get_by_username(dto.username)
            if existing_user:
                raise DomainException(f"Username '{dto.username}' can not be used.")

            existing_user = await uow.users.get_by_email(dto.email)
            if existing_user:
                raise DomainException(f"Email '{dto.email}' can not be used.")

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
        return UserMapper.to_output(user)
