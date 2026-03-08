from typing import TYPE_CHECKING

from a_core.exceptions import DomainException
from b_domain.entities.user import User
from b_domain.ports.use_case import UseCase
from c_application.dtos.user_dtos import CreateUserInputDTO, UserOutputDTO
from c_application.mappers.user_mapper import UserMapper

if TYPE_CHECKING:
    from b_domain.ports.password_hasher import PasswordHasher
    from b_domain.ports.providers import ClockProvider
    from b_domain.ports.unity_of_work import UnitOfWork


class CreateUserUseCase(UseCase[CreateUserInputDTO, UserOutputDTO]):
    """
    Orchestrates user registration, including password hashing,
    unique constraint validation, and preference initialization.
    """

    def __init__(
            self,
            uow: "UnitOfWork",
            clock: "ClockProvider",
            hasher: "PasswordHasher",
    ):
        super().__init__(uow, clock)
        self.hasher = hasher

    async def execute(self, dto: CreateUserInputDTO) -> UserOutputDTO:
        """Registers a new user in the system."""

        async with self.uow:

            # 1. Validação de Regra de Negócio (Unicidade)
            existing_user = await self.uow.users.get_by_username(dto.username)
            if existing_user:
                raise DomainException(f"O nome de usuário '{dto.username}' já está em uso.")

            # 2. Segurança: Hashing da senha
            password_hash = self.hasher.hash(dto.password)

            # 3. Criação da Entidade via Factory Method
            # Passamos o DTO de preferências diretamente para a entidade
            user = User.create(
                now=self.clock.now(),
                username=dto.username,
                password_hash=password_hash,
            )

            # 4. Persistência
            await self.uow.users.add(user)

        # 5. Mapeamento de Saída centralizado
        return UserMapper.to_output(user)
