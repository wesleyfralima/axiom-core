from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from b_domain.value_objects.enums import EnergyLevel
from b_domain.value_objects.identifiers import UserId, ContextId

if TYPE_CHECKING:
    from b_domain.value_objects import Priority, TaskId, TaskStatus


@dataclass(kw_only=True)
class BaseFilter:
    """Base class for all repository filters providing standard pagination.

    Attributes:
        limit (int): Maximum number of records to return. Defaults to 100 to prevent OOM.
        offset (int): Number of records to skip. Defaults to 0.
    """
    limit: int = 100
    offset: int = 0


@dataclass(kw_only=True)
class TaskFilter(BaseFilter):
    """Encapsulates search criteria for querying Tasks.

    Allows adding new filters in the future without breaking method signatures
    in the TaskRepository.
    """

    user_id: Optional[UserId] = None
    parent_id: Optional["TaskId"] = None
    status: Optional["TaskStatus"] = None
    priority: Optional["Priority"] = None

    context_id: Optional[ContextId] = None

    # Filtra tarefas que exigem até X energia (ex: filtrar por <= MEDIUM)
    max_energy_level: Optional[EnergyLevel] = None

    # Filtro para o motor de dependências
    is_blocked: Optional[bool] = None

    # Filtro para tarefas recorrentes
    is_recurring: Optional[bool] = None

    tags: List[str] = field(default_factory=list)
    only_roots: bool = False


@dataclass(kw_only=True)
class UserFilter(BaseFilter):
    """Encapsulates search criteria for querying Users.

    Useful for an admin panel or for searching users to share projects with.
    """
    username: Optional[str] = None
    is_active: Optional[bool] = None
