from dataclasses import dataclass
from typing import Generic, Optional

from a_core.application.dtos import TResponse


@dataclass(frozen=True)
class Result(Generic[TResponse]):
    is_success: bool
    value: Optional[TResponse] = None
    error: Optional[str] = None
