from b_domain.entities import Context
from b_domain.value_objects.identifiers import ContextId
from c_application.dtos.context_dtos import ContextOutputDTO


class ContextMapper:
    """Maps Context entities to the DTOs the interfaces receive."""

    @staticmethod
    def to_output[T: ContextOutputDTO](
        context: Context,
        dto_class: type[T],
        active_context_id: ContextId | None = None,
    ) -> T:
        """Map a Context entity to a ContextOutputDTO (or a subclass of it).

        Args:
            context (Context): The entity to map.
            dto_class (type[T]): The DTO class to build; use cases return their
                own subclass so each one has a presenter of its own.
            active_context_id (ContextId | None): The user's active context,
                to fill ``is_active``.

        Returns:
            T: The mapped DTO.
        """
        return dto_class(
            id=str(context.id),
            name=context.name,
            icon=context.icon,
            description=context.description,
            is_active=context.id == active_context_id,
        )
