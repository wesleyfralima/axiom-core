from datetime import datetime
from typing import Protocol


class ClockProvider(Protocol):
    """Contract for providing a system or mocked clock instance."""

    def now(self) -> datetime:
        """Return the current datetime.

        Returns:
            datetime: Current system or custom-defined time.
        """
