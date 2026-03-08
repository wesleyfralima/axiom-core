from abc import ABC, abstractmethod
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from b_domain.entities import Task
    from b_domain.ports.repositories.filters import TaskFilter
    from b_domain.value_objects.identifiers import TaskId, UserId


class TaskRepository(ABC):
    """Contract for Task persistence.

    Any database adapter (e.g., SQLiteTaskRepository, PostgresTaskRepository)
    must implement these methods to be injected via the UnitOfWork.
    """

    @abstractmethod
    async def add(self, task: "Task") -> None:
        """Persist a new task.

        Args:
            task (Task): The domain task entity to be added.
        """

    @abstractmethod
    async def update(self, task: "Task") -> None:
        """Update an existing task.

        Args:
            task (Task): The task entity with updated values.
        """

    @abstractmethod
    async def update_many(self, tasks: List["Task"]) -> None:
        """
        Atualiza múltiplas tarefas em uma única operação de persistência.
        Ideal para processar efeitos em cascata como desbloqueio de dependências.
        """

    @abstractmethod
    async def delete(self, task_id: "TaskId") -> None:
        """Permanently remove a task.

        Args:
            task_id (TaskId): The ID of the task to delete.
        """

    @abstractmethod
    async def get_by_id(self, task_id: "TaskId", user_id: Optional["UserId"] = None) -> Optional["Task"]:
        """Retrieve a task by its exact ID.

        If user_id is provided, the repository must ensure the task belongs
        to that user (security scoping).

        Args:
            task_id (TaskId): The task ID.
            user_id (Optional[UserId]): The ID of the user who owns the task.

        Returns:
            Optional[Task]: The instantiated domain task if found, otherwise None.
        """

    @abstractmethod
    async def list(self, filters: "TaskFilter") -> List["Task"]:
        """Return a paginated list of tasks based on provided filters.

        The implementation MUST respect the `limit` and `offset` attributes
        present in the BaseFilter to prevent memory overloads.

        Args:
            filters (TaskFilter): The filter criteria, including pagination.

        Returns:
            List[Task]: A list of task entities matching the filters.
        """

    @abstractmethod
    async def count(self, filters: "TaskFilter") -> int:
        """Return the total count of tasks matching the filters.

        The implementation MUST ignore the `limit` and `offset` attributes
        when counting, returning the total absolute number of matching rows.
        This is used alongside `list` to build paginated API responses.

        Args:
            filters (TaskFilter): The filter criteria.

        Returns:
            int: Total number of tasks matching the filters.
        """

    @abstractmethod
    async def get_subtasks(self, parent_id: "TaskId", limit: int = 100, offset: int = 0) -> List["Task"]:
        """Retrieve direct children of a task.

        Includes basic pagination to protect the system from massive subtask lists.

        Args:
            parent_id (TaskId): The parent task ID.
            limit (int): Maximum number of subtasks to return.
            offset (int): Number of subtasks to skip.

        Returns:
            List[Task]: A list of subtasks.
        """

    @abstractmethod
    async def find_by_id_prefix(self, id_prefix: str, user_id: "UserId" = None) -> List["Task"]:
        ...

    @abstractmethod
    async def find_tasks_blocked_by(self, target_id: "TaskId") -> List["Task"]:
        """Retrieve all tasks that depend on the given task ID.

        Args:
            target_id (TaskId): The ID of the blocking task.

        Returns:
            List[Task]: Tasks that have target_id in their depends_on set.
        """
