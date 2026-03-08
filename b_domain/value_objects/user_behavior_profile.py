from dataclasses import dataclass

from a_core.base import ValueObject


@dataclass(frozen=True, kw_only=True)
class UserBehaviorProfile(ValueObject):
    """
    Representa os parâmetros comportamentais aprendidos do usuário.

    Diferente do UserFlowState (estado momentâneo),
    este objeto descreve como o usuário tende a se comportar
    ao longo do tempo.
    """

    # ---------------------------------------------------------
    # PESOS DO FLOW ENGINE
    # ---------------------------------------------------------
    w_complexity: float = 2.0
    w_duration: float = 1.5
    w_energy: float = 2.5
    w_priority: float = 2.0

    # ---------------------------------------------------------
    # PARÂMETROS COGNITIVOS
    # ---------------------------------------------------------
    ultradian_limit: int = 90
    warmup_duration_limit: int = 10

    # ---------------------------------------------------------
    # COMPORTAMENTO DE MOMENTUM
    # ---------------------------------------------------------
    momentum_base_reward: float = 0.10
    skip_penalty: float = 0.10

    # ---------------------------------------------------------
    # RECUPERAÇÃO DE ENERGIA
    # ---------------------------------------------------------
    rest_recovery_minutes_per_level: int = 15

    # ---------------------------------------------------------
    # EXPLORAÇÃO DO MOTOR
    # ---------------------------------------------------------
    exploration_noise: float = 0.5
