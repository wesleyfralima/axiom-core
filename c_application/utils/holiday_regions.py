"""Finding a holiday region by what the user types: a code or a name.

``BR``, ``bra``, ``Brasil`` (close to "Brazil"), ``BR-SP``, ``BR-sao paulo``:
case and accents never matter.
"""

from a_core.text import fold
from b_domain.ports.providers.holiday_provider import HolidayProvider
from b_domain.value_objects.work_calendar import HolidayRegion


def find_regions(provider: HolidayProvider, query: str) -> list[HolidayRegion]:
    """The regions whose code or name matches ``query``.

    Without a dash, among the countries; with one (``BR-SP``, ``br-paulo``),
    among that country's subdivisions. An exact code comes first, then the
    codes and names that contain the text; with none of those, the names
    a typo away from it or from its start (another language's spelling:
    "Brasil", "bras").

    Args:
        provider (HolidayProvider): Who knows the regions.
        query (str): What the user typed.

    Returns:
        list[HolidayRegion]: The matches, best first (may be empty).
    """
    text: str = fold(query)
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
        return fold(region.code.rpartition("-")[2])

    exact: list[HolidayRegion] = [r for r in candidates if short(r) == text]
    containing: list[HolidayRegion] = [
        r
        for r in candidates
        if r not in exact and (text in short(r) or text in fold(r.name))
    ]
    if exact or containing:
        return exact + containing

    # Close: a typo away from the whole name ("brasil" → "brazil") or from
    # its start ("bras" → "braz…")
    allowed: int = 1 if len(text) <= 5 else 2
    scored: list[tuple[int, HolidayRegion]] = []
    for region in candidates:
        name: str = fold(region.name)
        edits: int = min(_edits(text, name), _edits(text, name[: len(text)]))
        if edits <= allowed:
            scored.append((edits, region))
    scored.sort(key=lambda pair: pair[0])
    return [region for _, region in scored[:3]]


def _edits(a: str, b: str) -> int:
    """How many letters to add, remove or change to turn ``a`` into ``b``."""
    previous: list[int] = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current: list[int] = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]
