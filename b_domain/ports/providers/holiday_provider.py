from collections.abc import Mapping
from datetime import date
from typing import Protocol


class HolidayProvider(Protocol):
    """Contract for the public holidays of a region.

    A region is a country's ISO 3166 code, optionally followed by one of its
    subdivisions: ``BR``, ``BR-SP``, ``US-CA``. The core keeps no holiday
    tables; whoever implements this does.
    """

    def supports(self, region: str) -> bool:
        """Whether ``region`` is one this provider knows.

        Args:
            region (str): The region, already upper case (``BR-SP``).

        Returns:
            bool: True if its holidays can be listed.
        """

    def holidays(self, region: str, year: int) -> Mapping[date, str]:
        """The region's public holidays in ``year``.

        Args:
            region (str): The region (``BR-SP``).
            year (int): The year.

        Returns:
            Mapping[date, str]: Each holiday's date and name; empty for a
            region the provider does not know.
        """

    def region_for_timezone(self, timezone: str) -> str | None:
        """The country of an IANA time zone, when the provider supports it.

        Only a suggestion for the user to confirm: a time zone can span
        several countries' conventions.

        Args:
            timezone (str): An IANA time zone (``America/Sao_Paulo``).

        Returns:
            str | None: The country's code (``BR``), or None.
        """
