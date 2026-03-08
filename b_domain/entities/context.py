from dataclasses import dataclass

from a_core.base import Entity
from b_domain.value_objects import UserId


@dataclass(kw_only=True)
class Context(Entity):
    """
    Representa o 'onde' ou 'como' uma tarefa deve ser realizada.
    Ex: 'Rua', 'Trabalho', 'Focado'.
    """

    user_id: UserId
    name: str
    icon: str = "🏷️"
    description: str = ""

    @classmethod
    def create(cls, user_id: UserId, name: str, icon: str = "🏷️") -> "Context":
        return cls(
            user_id=user_id,
            name=name,
            icon=icon
        )