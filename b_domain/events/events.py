from dataclasses import dataclass
from typing import Optional

from a_core.base import DomainEvent
from b_domain.value_objects.enums import EnergyLevel
from b_domain.value_objects.identifiers import ContextId, TaskId, UserId


@dataclass(frozen=True, kw_only=True)
class TaskStartedEvent(DomainEvent):
    task_id: TaskId
    user_id: UserId
    context_id: ContextId
    momentum_at_start: float


@dataclass(frozen=True, kw_only=True)
class TaskCompletedEvent(DomainEvent):
    """Disparado quando uma tarefa é concluída com sucesso pelo usuário."""
    task_id: TaskId
    user_id: UserId
    estimated_minutes: int
    actual_minutes: int
    energy_level_used: EnergyLevel


@dataclass(frozen=True, kw_only=True)
class TaskAbandonedEvent(DomainEvent):
    """Disparado quando o usuário desiste de uma tarefa em andamento."""
    task_id: TaskId
    user_id: UserId
    time_spent_minutes: int
    reason: str = "manual_skip"  # A razão inferida (ex: timeout, manual_skip)


@dataclass(frozen=True, kw_only=True)
class FlowMomentumBrokenEvent(DomainEvent):
    """Disparado quando o sistema detecta que a sequência (streak) do usuário foi zerada."""
    user_id: UserId
    last_streak_count: int


@dataclass(frozen=True, kw_only=True)
class RewardEarnedEvent(DomainEvent):
    user_id: UserId
    reward_type: str  # "streak_milestone", "performance_bonus"
    value: int


@dataclass(frozen=True, kw_only=True)
class ContextSwitchedEvent(DomainEvent):
    """
    Disparado quando o contexto ativo do usuário é alterado.
    Essencial para o Context Engine aprender padrões de transição.
    """
    user_id: UserId
    old_context_id: Optional[ContextId]
    new_context_id: ContextId
    # 'manual' ou 'automatic' (ex: por geofencing ou horário)
    trigger_type: str = "manual"
