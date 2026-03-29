from datetime import datetime, timezone
from uuid import uuid4

from b_domain.entities import Task
from b_domain.value_objects import RecurrenceInterval, DueDate, UserId, Title
from b_domain.value_objects.dates import AxiomDate
from b_domain.value_objects.recurrences.simple import SimpleIntervalRule


# ============================================================
# Helpers
# ============================================================

def create_task_with_recurrence(
        due_date: datetime,
        interval: int = 1,
        freq=RecurrenceInterval.DAILY,
        is_floating: bool = True,
        tz_name: str = "UTC",
        end_date: datetime = None
) -> Task:
    """Helper para criar uma tarefa com recorrência rapidamente."""

    # ------------------------------------------------------------------
    # 1. Construir AxiomDate corretamente
    # ------------------------------------------------------------------

    if is_floating:
        start_axiom = AxiomDate.floating(
            due_date.replace(tzinfo=None),
            tz_name,
        )
    else:
        if due_date.tzinfo is None:
            due_date = due_date.replace(tzinfo=timezone.utc)
        start_axiom = AxiomDate.fixed(due_date)

    # ------------------------------------------------------------------
    # 2. Converter end_date (se existir)
    # ------------------------------------------------------------------

    end_axiom = None
    if end_date:
        if is_floating:
            end_axiom = AxiomDate.floating(
                end_date.replace(tzinfo=None),
                tz_name,
            )
        else:
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            end_axiom = AxiomDate.fixed(end_date)

    # ------------------------------------------------------------------
    # 3. Criar regra de recorrência
    # ------------------------------------------------------------------

    recurrence = SimpleIntervalRule(
        frequency=freq,
        interval=interval,
        start_date=start_axiom,
        end_date=end_axiom
    )

    # ------------------------------------------------------------------
    # 4. DueDate (mantém compatibilidade com seu domínio atual)
    # ------------------------------------------------------------------

    if is_floating:
        due = DueDate.floating(
            due_date.replace(tzinfo=None),
            tz_name,
        )
    else:
        due = DueDate.fixed(due_date)

    # ------------------------------------------------------------------
    # 5. Criar Task
    # ------------------------------------------------------------------

    return Task.create(
        now=datetime.now(),
        user_id=UserId(uuid4()),
        title=Title("Test Task"),
        due_date=due.value,
        is_floating=is_floating,
        tz_name=tz_name,
        recurrence=recurrence
    )


# ============================================================
# Testes: create_next_occurrence
# ============================================================

def test_next_occurrence_simple_daily():
    """
    Cenário: Tarefa vence hoje (01/Jan). Concluo hoje.
    Expectativa: Próxima tarefa para amanhã (02/Jan).
    """

    # 01/Jan às 09:00
    due_dt = datetime(2026, 1, 1, 9, 0)
    now = datetime(2026, 1, 1, 10, 0)  # 1 hora depois do vencimento

    task = create_task_with_recurrence(due_dt)

    next_task = task.create_next_occurrence(now=now)

    assert next_task is not None
    assert next_task.due_date.value == datetime(2026, 1, 2, 9, 0)
    assert next_task.due_date.is_floating is True


def test_next_occurrence_catch_up_logic():
    """
    Cenário: Tarefa venceu há 5 dias (05/Jan). Hoje é 10/Jan.
    Expectativa: O sistema deve pular 06, 07, 08, 09, 10 e agendar para 11/Jan.
    (Pois 10/Jan 09:00 já passou em relação ao 'now' 10/Jan 10:00).
    """
    due_dt = datetime(2026, 1, 5, 9, 0)
    now = datetime(2026, 1, 10, 10, 0)

    task = create_task_with_recurrence(due_dt)

    # catch_up=True é o padrão
    next_task = task.create_next_occurrence(now=now, catch_up=True)

    assert next_task is not None
    assert next_task.due_date.value == datetime(2026, 1, 11, 9, 0)


def test_next_occurrence_strict_mode_financial():
    """
    Cenário: Tarefa venceu há 5 dias (05/Jan). Hoje é 10/Jan.
    Expectativa: catch_up=False (Modo Financeiro).
    O sistema deve criar a EXATA próxima ocorrência sequencial (06/Jan), mesmo atrasada.
    """
    due_dt = datetime(2026, 1, 5, 9, 0)
    now = datetime(2026, 1, 10, 10, 0)

    task = create_task_with_recurrence(due_dt)

    # Desativa o catch-up
    next_task = task.create_next_occurrence(now=now, catch_up=False)

    assert next_task is not None
    assert next_task.due_date.value == datetime(2026, 1, 6, 9, 0)  # Atrasada


def test_recurrence_ends_by_date():
    """
    Cenário: A recorrência tem data fim (Until).
    Expectativa: Retornar None quando passar da data.
    """
    due_dt = datetime(2026, 1, 1, 9, 0)
    end_date = datetime(2026, 1, 1, 23, 59)  # Termina hoje
    now = datetime(2026, 1, 1, 10, 0)

    task = create_task_with_recurrence(due_dt, end_date=end_date)

    # A próxima seria 02/Jan, mas 02/Jan > EndDate
    next_task = task.create_next_occurrence(now=now)

    assert next_task is None


def test_timezone_consistency_fixed_task():
    """
    Cenário: Tarefa Fixed (UTC).
    Expectativa: A próxima tarefa deve nascer também como Fixed (UTC).
    """
    due_dt = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

    task = create_task_with_recurrence(due_dt, is_floating=False)

    next_task = task.create_next_occurrence(now=now)

    assert next_task is not None
    assert next_task.due_date.is_floating is False
    assert next_task.due_date.value.tzinfo is not None  # Deve ser Aware
    assert next_task.due_date.value == datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)


def test_timezone_comparison_mixed_inputs():
    """
    Cenário: Tarefa Floating (Naive) vs 'now' Aware (UTC).
    Expectativa: O sistema deve normalizar internamente e não quebrar com TypeError.
    """

    # Tarefa Floating às 09:00
    due_dt = datetime(2026, 1, 5, 9, 0)

    # 'Agora' é 13:00 UTC (que seria '10:00' em SP '-3').
    # Se a tarefa é Floating, ela vence às 09:00 locais.
    # 10:00 (Agora) > 09:00 (Vencimento). Então a de hoje já passou.
    # A próxima deve ser dia 11.
    now_aware = datetime(2026, 1, 10, 13, 0, tzinfo=timezone.utc)

    task = create_task_with_recurrence(due_dt, is_floating=True)

    next_task = task.create_next_occurrence(now=now_aware, catch_up=True)

    assert next_task is not None
    assert next_task.due_date.is_floating is True
    assert next_task.due_date.value == datetime(2026, 1, 11, 9, 0)  # Naive
