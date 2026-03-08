from dataclasses import dataclass
from typing import Optional

from b_domain.value_objects import UserId
from b_domain.value_objects.identifiers import ContextId


@dataclass
class SwitchContextRequest:
    user_id: UserId
    context_id: Optional[ContextId]  # None desativa o filtro
