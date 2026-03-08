from abc import ABC, abstractmethod

from a_core.base import DomainEvent


class EventBus(ABC):
    """Porta de saída para publicação de eventos de domínio."""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        pass
