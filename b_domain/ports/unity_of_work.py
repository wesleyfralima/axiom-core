from abc import ABC, abstractmethod
from types import TracebackType
from typing import Optional, Type

from b_domain.ports.event_bus import EventBus
from b_domain.ports.repositories import TaskRepository
from b_domain.ports.repositories.time_entry_repository import TimeEntryRepository
from b_domain.ports.repositories.user_repository import UserRepository


class UnitOfWork(ABC):
    """Defines an atomic unit of work.

    A UnitOfWork:
      - Exposes repositories
      - Controls transaction boundaries
    """

    tasks: TaskRepository
    users: UserRepository
    time_entries: TimeEntryRepository

    def __init__(self, event_bus: "EventBus"):
        self.event_bus = event_bus
        self._seen_entities = set()

    async def __aenter__(self) -> "UnitOfWork":
        """Enter the UnitOfWork context.

        Returns:
            UnitOfWork: The current UnitOfWork instance.
        """
        return self

    async def __aexit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc: Optional[BaseException],
            traceback: Optional[TracebackType],
    ) -> None:
        """Exit the UnitOfWork context.

        Commits if no exception occurred, otherwise rolls back.

        Args:
            exc_type (Optional[Type[BaseException]]): Exception type if raised.
            exc (Optional[BaseException]): Exception instance if raised.
            traceback (Optional[TracebackType]): Traceback object if available.
        """
        if exc_type is None:
            try:
                await self.commit()
                await self._publish_domain_events()
            except Exception:
                # Se o commit falhar (ex: queda de rede, integridade de dados),
                # garantimos a limpeza da transação e repassamos o erro.
                await self.rollback()
                raise
        else:
            # Se uma exceção já vinha do código de dentro do bloco 'async with',
            # apenas fazemos o rollback. O Python já vai propagar o 'exc' naturalmente.
            await self.rollback()

    async def _publish_domain_events(self):
        """Coleta eventos de todas as entidades envolvidas e publica."""
        for entity in self._seen_entities:
            for event in entity.pull_events():
                await self.event_bus.publish(event)
        self._seen_entities.clear()

    @abstractmethod
    async def commit(self) -> None:
        """Commit the current transaction."""
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the current transaction."""
        raise NotImplementedError
