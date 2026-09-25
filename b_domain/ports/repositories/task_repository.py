import builtins
from abc import ABC, abstractmethod
from collections.abc import Iterable

from a_core import BaseRepository, IdPrefix, tracks_entity
from b_domain.entities import Task
from b_domain.ports.repositories.filters import TaskFilter
from b_domain.value_objects.identifiers import TaskId, UserId


class TaskRepository(ABC, BaseRepository):
    """Contract for persistence operations on tasks.

    Any database adapter (e.g., SQLiteTaskRepository, PostgresTaskRepository)
    must implement these methods to be injected via the UnitOfWork.
    """

    @abstractmethod
    @tracks_entity
    async def add(self, task: Task) -> Task:
        """Persist a new task.

        Args:
            task (Task): Domain task entity to be added.

        Returns:
            Task: The persisted task entity.
        """

    @abstractmethod
    async def update(self, task: Task) -> Task:
        """Update an existing task.

        Args:
            task (Task): The task entity with updated values.

        Returns:
            Task: The updated task entity.
        """

    @abstractmethod
    async def update_many(self, tasks: list[Task]) -> list[Task]:
        """Update multiple tasks in a single persistence operation.

        Useful for cascading effects such as unlocking dependencies.

        Args:
            tasks (List[Task]): List of task entities to update.

        Returns:
            List[Task]: The updated task entities.
        """

    @abstractmethod
    async def delete(self, task_id: TaskId) -> None:
        """Permanently remove a task.

        Args:
            task_id (TaskId): The ID of the task to delete.
        """

    @abstractmethod
    @tracks_entity
    async def get_by_id(
        self, task_id: TaskId, user_id: UserId | None = None
    ) -> Task | None:
        """Retrieve a task by its exact ID.

        If user_id is provided, the repository must ensure the task belongs
        to that user (security scoping).

        Args:
            task_id (TaskId): The task ID.
            user_id (Optional[UserId]): The ID of the user who owns the task.

        Returns:
            Optional[Task]: Domain task if found, otherwise None.
        """

    @abstractmethod
    @tracks_entity
    async def list(self, filters: TaskFilter) -> list[Task]:
        """Return a paginated list of tasks based on provided filters.

        Implementations MUST respect the `limit` and `offset` attributes
        present in the BaseFilter to prevent memory overloads.

        Args:
            filters (TaskFilter): The filter criteria, including pagination.

        Returns:
            List[Task]: Task entities matching the filters.
        """

    @abstractmethod
    async def count(self, filters: TaskFilter) -> int:
        """Return the total count of tasks matching the filters.

        Implementations MUST ignore `limit` and `offset` when counting,
        returning the absolute number of matching rows. Used alongside
        `list` to build paginated API responses.

        Args:
            filters (TaskFilter): The filter criteria.

        Returns:
            int: Total number of tasks matching the filters.
        """

    @abstractmethod
    @tracks_entity
    async def get_subtasks(
        self, parent_id: TaskId, limit: int = 100, offset: int = 0
    ) -> builtins.list[Task]:
        """Retrieve direct children of a task.

        Includes basic pagination to protect the system from massive subtask lists.

        Args:
            parent_id (TaskId): The parent task ID.
            limit (int): Maximum number of subtasks to return.
            offset (int): Number of subtasks to skip.

        Returns:
            List[Task]: Subtasks of the given parent.
        """

    @abstractmethod
    @tracks_entity
    async def find_by_id_prefix(
        self, id_prefix: IdPrefix, user_id: UserId | None = None
    ) -> builtins.list[Task]:
        """Find tasks by matching an ID prefix.

        Args:
            id_prefix (IdPrefix): Prefix string to match against task IDs.
            user_id (UserId, optional): Scope search to a specific user.

        Returns:
            List[Task]: Tasks whose IDs start with the given prefix.
        """

    @abstractmethod
    @tracks_entity
    async def find_tasks_blocked_by(self, target_id: TaskId) -> builtins.list[Task]:
        """Retrieve all tasks that depend on the given task ID.

        Args:
            target_id (TaskId): The ID of the blocking task.

        Returns:
            List[Task]: Tasks that have target_id in their depends_on set.
        """

    @abstractmethod
    async def task_ids_from_id_prefixes(
        self, partial_ids: Iterable[IdPrefix]
    ) -> builtins.list[TaskId]:
        """Retrieve TaskId objects from a list of ID prefixes.

        This method resolves each provided `IdPrefix` into its corresponding
        `TaskId`. It guarantees a strict 1:1 mapping: every prefix must match
        exactly one task identifier. This is useful for cases where only partial
        IDs are available (e.g., user input, autocomplete) and the system needs
        to resolve them into full task identifiers.

        Args:
            partial_ids (Iterable[IdPrefix]): Iterable of ID prefix objects to
                resolve into full TaskIds.

        Returns:
            List[TaskId]: List of TaskIds whose IDs start with the given prefix.

        Raises:
            ValueError: If any ID prefix does not correspond to exactly one TaskId.
        """
        raise NotImplementedError
