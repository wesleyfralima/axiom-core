from enum import Enum, IntEnum
from functools import cache


class TaskStatus(str, Enum):
    """Enumeration of possible Task statuses."""

    # --- Gestão e Intenção (Axiom Pro) ---
    SOMEDAY = "someday"  # No backlog, mas fora do alcance do Flow Engine (incubação)
    PENDING = "pending"  # Ativa para o Flow Engine, aguardando execução
    BLOCKED = "blocked"  # Aguardando dependência externa

    # --- Fluxo (Axiom Flow) ---
    SUGGESTED = "suggested"

    # --- Execução ---
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"  # Interrupção temporária (preserva contexto de momentum)

    # --- Conclusão ---
    DONE = "done"

    # --- Feedback de Fluxo (Podem ser invisíveis no Pro) ---
    SKIPPED = "skipped"  # O usuário recusou a sugestão do Flow
    DEFERRED = "deferred"  # O usuário começou, mas "devolveu" para a lista
    ABANDONED = "abandoned"  # O usuário abandonou ou o sistema inferiu que ele parou sem avisar

    CANCELLED = "cancelled"
    REOPENED = "reopened"  # Reativada após conclusão ou cancelamento
    ARCHIVED = "archived"  # Estado terminal, não há volta

    @classmethod
    @cache
    def _get_transitions(cls) -> dict["TaskStatus", set["TaskStatus"]]:
        """Caches and returns the state machine transitions.

        Using a cached class method avoids recreating the dictionary
        on every check, while circumventing Python's limitation of
        referencing enum members during class creation.
        """

        return {
            cls.SOMEDAY: {
                cls.PENDING, cls.CANCELLED, cls.ARCHIVED,
            },

            cls.PENDING: {
                cls.SUGGESTED, cls.IN_PROGRESS, cls.DONE,
                cls.CANCELLED, cls.ARCHIVED, cls.BLOCKED,
                cls.SOMEDAY, cls.SKIPPED, cls.ABANDONED,
            },

            cls.BLOCKED: {
                cls.PENDING, cls.CANCELLED,
            },

            cls.SUGGESTED: {
                cls.IN_PROGRESS, cls.DONE, cls.SKIPPED,
                cls.PENDING, cls.CANCELLED,
            },

            cls.IN_PROGRESS: {
                cls.DONE, cls.PAUSED, cls.DEFERRED,
                cls.ABANDONED, cls.CANCELLED, cls.PENDING,
            },

            cls.PAUSED: {
                cls.IN_PROGRESS, cls.DONE, cls.DEFERRED,
                cls.ABANDONED,
            },

            cls.SKIPPED: {
                cls.PENDING, cls.DONE, cls.ARCHIVED,
            },

            cls.DEFERRED: {
                cls.PENDING,
            },

            cls.ABANDONED: {
                cls.PENDING, cls.ARCHIVED, cls.CANCELLED,
            },

            cls.DONE: {
                cls.REOPENED, cls.ARCHIVED,
            },

            cls.CANCELLED: {
                cls.REOPENED, cls.ARCHIVED,
            },

            cls.REOPENED: {
                cls.PENDING, cls.SUGGESTED, cls.IN_PROGRESS,
                cls.DONE,
            },

            cls.ARCHIVED: set(),  # Estado Terminal
        }

    def can_transition_to(self, new_status: "TaskStatus") -> bool:
        """Check if a task can transition from the current status to a new status."""

        # Se for o mesmo status, geralmente permitimos como um "no-op" (sem efeito)
        if self == new_status:
            return True

        transitions = self._get_transitions()
        return new_status in transitions[self]


class Priority(IntEnum):
    """Enumeration of priority levels for Tasks or Projects.

    Supports native Python comparison (e.g., Priority.CRITICAL > Priority.LOW).
    """

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def __str__(self) -> str:
        return self.name.capitalize()


class RecurrenceInterval(str, Enum):
    """Enumeration of possible recurrence intervals for Tasks."""
    HOURLY = "HO"
    DAILY = "DA"
    WEEKLY = "WE"
    MONTHLY = "MO"
    YEARLY = "YE"


class EnergyLevel(IntEnum):
    """
    Representa o esforço cognitivo ou físico necessário para uma tarefa.
    Baseado na metodologia GTD (Getting Things Done).
    """

    DRAINED = 1  # "Modo Zumbi": Só microtasks de < 2 min
    LOW = 2  # Tarefas administrativas leves
    BALANCED = 3  # Trabalho padrão, reuniões
    HIGH = 4  # Foco sério, produção ativa
    PEAK = 5  # "God Mode": Resolução de problemas complexos / Deep Work

    def __str__(self) -> str:
        return self.name.capitalize()


class TaskComplexity(IntEnum):
    """
    Representa o nível de complexidade de uma tarefa.
    """

    VERY_LOW = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    VERY_HIGH = 5

    def __str__(self) -> str:
        return self.name.capitalize()


class MomentumTrend(str, Enum):
    RISING = "rising"  # Usuário está "on fire", pode aumentar complexidade
    STABLE = "stable"  # Fluxo mantido
    FALLING = "falling"  # Alerta de fadiga, sugerir tarefas mais fáceis
    STAGNANT = "stagnant"  # Inércia total, precisa de uma "Quick Win" (Microtask)
