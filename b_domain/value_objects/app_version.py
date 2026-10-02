"""The app's version, as the devices of one account compare it."""

import re
from dataclasses import dataclass

_VERSION: re.Pattern[str] = re.compile(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?")


@dataclass(frozen=True, order=True)
class AppVersion:
    """``major.minor.patch``. Every device of an account runs the same
    ``major.minor`` (its **series**): fixes (the patch) may differ, a newer
    series changes what the rules write (owner's decision, 2026-10-02).
    """

    major: int
    minor: int
    patch: int = 0

    @classmethod
    def parse(cls, text: str | None) -> "AppVersion | None":
        """A version from text ("0.30.0", "0.30"); None when there is none or
        it is not one (anything after the numbers is ignored)."""
        found = _VERSION.match(text or "")
        if found is None:
            return None
        return cls(int(found[1]), int(found[2]), int(found[3] or 0))

    @property
    def series(self) -> tuple[int, int]:
        """``(major, minor)``: what must match across an account's devices."""
        return (self.major, self.minor)

    def is_behind(self, other: "AppVersion") -> bool:
        """Whether this one is an older series than ``other``."""
        return self.series < other.series

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
