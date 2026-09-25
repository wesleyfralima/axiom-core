from b_domain.value_objects.recurrences import RecurrenceRule
from c_application.utils.string_utils import (
    join_naturally,
    ordinal_phrase,
    ordinal_weekday_phrase,
)

# Invertemos o WEEKDAY_MAP para facilitar a busca por índice
WEEKDAY_LABELS = {
    v: k.capitalize()
    for k, v in {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6,
    }.items()
}

# Invertemos o INTERVALS_MAP ou usamos um mapeamento direto de códigos
FREQ_INFO = {
    "DA": ("day", "days"),
    "WE": ("week", "weeks"),
    "MO": ("month", "months"),
    "YE": ("year", "years"),
}


def format_task_recurrence(recurrence: RecurrenceRule) -> str | None:
    """Format a recurrence rule into a human-readable string."""

    if not recurrence:
        return None

    # --- 1. Frequência e Intervalo ---
    freq_str: str | None = getattr(recurrence, "frequency", None)
    if freq_str is None:
        return None

    unit_singular, unit_plural = FREQ_INFO.get(freq_str, ("period", "periods"))

    interval = recurrence.interval or 1
    if interval == 1:
        phrase = f"Every {unit_singular}"
    else:
        phrase = f"Every {interval} {unit_plural}"

    parts: list[str] = [phrase]

    # --- 2. Dias da Semana ---
    if hasattr(recurrence, "by_week_days") and recurrence.by_week_days:
        days = [
            f"{WEEKDAY_LABELS.get(d, str(d))}s" for d in sorted(recurrence.by_week_days)
        ]

        day_prefix = "on"
        if hasattr(recurrence, "by_set_pos") and recurrence.by_set_pos:
            day_prefix += f" {ordinal_weekday_phrase(recurrence.by_set_pos)}"

        parts.append(f"{day_prefix} {join_naturally(days)}")

    # --- 3. Dias do Mês ---
    if hasattr(recurrence, "by_month_days") and recurrence.by_month_days:
        days = [str(d) for d in sorted(recurrence.by_month_days)]
        parts.append(f"on days {join_naturally(days)}")

    # --- 4. Dia Útil (Nth Business Day) ---
    if hasattr(recurrence, "nth_business_day") and recurrence.nth_business_day:
        # Usamos o ordinal_phrase que revisamos para unificar o estilo
        b_phrase = ordinal_phrase(recurrence.nth_business_day)
        parts.append(f"on the {b_phrase} business day")

    # --- 5. Limites (Count ou End Date) ---
    if recurrence.count:
        parts.append(f"for {recurrence.count} times")
    elif recurrence.end_date:
        parts.append(
            f"until {recurrence.end_date.value:%Y-%m-%d} {recurrence.end_date.timezone}"
        )

    # Unimos tudo com espaços e adicionamos o ponto final
    return " ".join(parts).strip() + "."
