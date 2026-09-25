import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from a_core.ddd.entities import Entity

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


def tracks_entity[**P, R](
    method: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    """Decorator to automatically register fetched or mutated entities into the UoW."""

    @wraps(method)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:

        self: BaseRepository = cast(BaseRepository, args[0])
        result: R = await method(*args, **kwargs)

        if result:
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, Entity):
                        self._track(item)
            elif isinstance(result, Entity):
                self._track(result)

        return result

    # Adicionamos o atributo dinamicamente.
    # setattr works around the type system here, since this is
    # an infrastructure decorator.
    setattr(wrapper, "_is_tracked", True)  # noqa: B010

    return wrapper


class BaseRepository:
    """Base repository enforcing automatic entity tracking for the Unit of Work."""

    def __init__(self, seen_entities: set[Entity]) -> None:
        self._seen_entities: set[Entity] = seen_entities

    def _track(self, entity: Entity) -> None:
        """Register an entity instance into the shared tracked set."""
        self._seen_entities.add(entity)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Enforce architectural constraints on subclass methods at definition time."""

        super().__init_subclass__(**kwargs)

        for name, method in inspect.getmembers(
            cls, predicate=inspect.iscoroutinefunction
        ):
            # Ignore 'private' methods or those inherited from BaseRepository
            if name.startswith("_") or name in dir(BaseRepository):
                continue

            # Ensure all public query/mutation methods are explicitly tracked
            if name.startswith(("get", "find", "list", "add")):
                if not getattr(method, "_is_tracked", False):
                    raise TypeError(
                        f"[ARCHITECTURE ERROR] The method '{cls.__name__}.{name}' "
                        f"must be decorated with @tracks_entity to ensure tracking."
                    )
