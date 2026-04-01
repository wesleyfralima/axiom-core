from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from b_domain.ports.providers import ClockProvider
from b_domain.ports.unity_of_work import UnitOfWork, UowFactoryType

# Generic types for Use Case Input (Request) and Output (Response)
TRequest: TypeVar = TypeVar("TRequest")
TResponse: TypeVar = TypeVar("TResponse")


class UseCase(ABC, Generic[TRequest, TResponse]):
    """Base contract for all application Use Cases.

    Enforces that all interaction with the core system (Web, CLI, etc.)
    goes through a well-defined port with a single `execute` method.
    """

    def __init__(
            self,
            uow_factory: UowFactoryType,
            clock: ClockProvider,
    ):
        self._uow_factory = uow_factory
        self.clock = clock

    @property
    def uow(self) -> UnitOfWork:
        """Return a new UnitOfWork instance.

        This property creates a fresh UnitOfWork every time it is accessed.
        It ensures that constructs like `async with self.uow` in subclasses
        always open a new transactional context, preventing reuse of stale
        sessions and guaranteeing isolation.

        Returns:
            UnitOfWork: A newly created UnitOfWork instance.
        """
        return self._uow_factory()

    @abstractmethod
    async def execute(self, request: TRequest) -> TResponse:
        """Executes the business logic of the use case.

        Args:
            request (TRequest): The input payload required for the operation.

        Returns:
            TResponse: The output result of the operation.
        """
