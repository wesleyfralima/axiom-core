import inspect
from functools import wraps
from typing import Callable, Any

from a_core.ddd.entities import Entity


def tracks_entity(method: Callable):
    """Decorator that automatically registers repository results in the Unit of Work.

    This ensures that any entity retrieved by repository methods (e.g., `get_by_id`)
    is tracked by the Unit of Work for change detection and persistence.

    Args:
        method (Callable): The repository method being decorated.

    Returns:
        Callable: Wrapped method that tracks returned entities.
    """

    @wraps(method)
    async def wrapper(self: "BaseRepository", *args, **kwargs):

        # Execute the original repository method
        result: Any = await method(self, *args, **kwargs)

        # If the result is an entity or list of entities, track them
        if result:
            if isinstance(result, list):
                for item in result:
                    self._track(item)
            else:
                self._track(result)

        return result

    # Marker attribute: indicates this method is safely tracked
    wrapper._is_tracked = True
    return wrapper


class BaseRepository:
    """Base class for repositories with automatic entity tracking.

    Ensures that any repository method responsible for retrieving or
    adding entities is decorated with `@tracks_entity`. This guarantees
    that entities are tracked by the Unit of Work for change detection
    and persistence.
    """

    def __init__(self, seen_entities: set):
        """Initialize the repository.

        Args:
            seen_entities (set): A shared set of entities tracked by the Unit of Work.
        """
        self._seen_entities = seen_entities

    def _track(self, entity: Entity):
        """Track an entity if it supports domain events.

        Entities with a `pull_events` method are added to the Unit of Work's
        tracked set, enabling event dispatch and persistence.
        """
        if hasattr(entity, "pull_events"):
            self._seen_entities.add(entity)

    def __init_subclass__(cls, **kwargs):
        """Validate repository subclass methods at definition time.

        This hook inspects all coroutine methods in subclasses. If a method
        appears to be a query or mutation (e.g., starts with `get`, `find`,
        `list`, or `add`) but is not decorated with `@tracks_entity`, an
        error is raised to enforce architectural consistency.
        """

        super().__init_subclass__(**kwargs)

        # Inspector: scans the class for coroutine methods
        for name, method in inspect.getmembers(cls, predicate=inspect.iscoroutinefunction):

            # Ignore private methods or those inherited from BaseRepository
            if name.startswith("_") or name in dir(BaseRepository):
                continue

            # Enforce tracking for repository methods
            if name.startswith(("get", "find", "list", "add")):
                if not getattr(method, "_is_tracked", False):
                    raise TypeError(
                        f"[ARCHITECTURE ERROR] The method '{cls.__name__}.{name}' "
                        f"must be decorated with @tracks_entity to ensure tracking."
                    )
