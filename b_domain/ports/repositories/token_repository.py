from abc import ABC, abstractmethod


class TokenRepository(ABC):
    """Contract for local token persistence.

    This repository is intended for client-side applications (like axiom-cli)
    to store, retrieve, and clear the current user's authentication token.
    """

    @abstractmethod
    async def save(self, token: str) -> None:
        """Save an authentication token securely.

        Args:
            token (str): The raw token string to be stored.
        """

    @abstractmethod
    async def load(self) -> str | None:
        """Load the currently stored authentication token.

        Returns:
            Optional[str]: The stored token if available, otherwise None.
        """

    @abstractmethod
    async def clear(self) -> None:
        """Clear the stored authentication token (e.g., on logout)."""
