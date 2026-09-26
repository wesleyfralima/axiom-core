"""Finding a holiday region by what the user types: a code or a name.

``BR``, ``bra``, ``Brasil`` (close to "Brazil"), ``BR-SP``, ``BR-sao paulo``:
case and accents never matter.
"""

import difflib
import unicodedata

from b_domain.ports.providers.holiday_provider import HolidayProvider
from b_domain.value_objects.work_calendar import HolidayRegion


def find_regions(provider: HolidayProvider, query: str) -> list[HolidayRegion]:
    """The regions whose code or name matches ``query``.

    Without a dash, among the countries; with one (``BR-SP``, ``br-paulo``),
    among that country's subdivisions. An exact code comes first, then the
    codes and names that contain the text; with none of those, the names
    that are close to it or start close to it (a typo, another language's
    spelling: "Brasil", "bras").

    Args:
        provider (HolidayProvider): Who knows the regions.
        query (str): What the user typed.

    Returns:
        list[HolidayRegion]: The matches, best first (may be empty).
    """
    text: str = _plain(query)
    if not text:
        return []
    country, dash, sub = text.partition("-")
    candidates: list[HolidayRegion]
    if dash:
        candidates = provider.regions(country.upper())
        text = sub
    else:
        candidates = provider.regions()
    if not text:
        return candidates

    def short(region: HolidayRegion) -> str:
        return _plain(region.code.rpartition("-")[2])

    exact: list[HolidayRegion] = [r for r in candidates if short(r) == text]
    containing: list[HolidayRegion] = [
        r
        for r in candidates
        if r not in exact and (text in short(r) or text in _plain(r.name))
    ]
    if exact or containing:
        return exact + containing

    # Close: to the whole name ("brasil" ~ "brazil") or to its start ("bras")
    scored: list[tuple[float, HolidayRegion]] = []
    for region in candidates:
        name: str = _plain(region.name)
        score: float = max(_similar(text, name), _similar(text, name[: len(text)]))
        if score >= _CLOSE:
            scored.append((score, region))
    scored.sort(key=lambda pair: -pair[0])
    return [region for _, region in scored[:3]]


_CLOSE: float = 0.75
"""How similar a name must be to count as a typo of the text (0 to 1)."""


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _plain(text: str) -> str:
    """Lower case, no accents, single spaces: "São  Paulo" → "sao paulo"."""
    decomposed: str = unicodedata.normalize("NFKD", text)
    stripped: str = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())
