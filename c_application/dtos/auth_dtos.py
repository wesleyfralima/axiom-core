from dataclasses import dataclass, field

from a_core import DTO


@dataclass(frozen=True)
class LoginInputDTO(DTO):
    """Data Transfer Object for user login requests."""
    username: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class TokenOutputDTO(DTO):
    """Data Transfer Object for successful authentication responses."""
    access_token: str
    token_type: str = "bearer"
