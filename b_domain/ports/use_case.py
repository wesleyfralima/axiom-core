from abc import ABC, abstractmethod
from typing import TypeVar, Generic

from b_domain.ports.providers import ClockProvider
from b_domain.ports.unity_of_work import UnitOfWork

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
            uow: "UnitOfWork",
            clock: "ClockProvider",
    ):
        self.uow = uow
        self.clock = clock

    @abstractmethod
    def execute(self, request: TRequest) -> TResponse:
        """Executes the business logic of the use case.

        Args:
            request (TRequest): The input payload required for the operation.

        Returns:
            TResponse: The output result of the operation.
        """
