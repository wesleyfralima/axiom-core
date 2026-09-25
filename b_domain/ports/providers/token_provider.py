from typing import Any, Protocol


class TokenProvider(Protocol):
    """Contract for generating and reading access tokens."""

    def create_access_token(self, data: dict[str, Any]) -> str:
        """Creates a signed token containing the payload."""

    def decode_access_token(self, token: str) -> dict[str, Any]:
        """Decodes and validates the token.

        Returns:
            Dict[str, Any]: The payload data (e.g., user_id, sub).

        Raises:
            InvalidTokenError: If token is malformed or signature fails.
            ExpiredTokenError: If token is valid but has expired.
        """
