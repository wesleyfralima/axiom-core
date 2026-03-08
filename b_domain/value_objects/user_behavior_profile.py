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
    # (Importância relativa no ranking)
    # ---------------------------------------------------------
    w_complexity: float = 2.0
    w_duration: float = 1.5
    w_energy: float = 2.5
    w_priority: float = 2.0

    # ---------------------------------------------------------
    # ESCALAS NORMALIZADAS DO SCORE
    # (Usadas para transformar valores absolutos em score)
    # ---------------------------------------------------------
    max_complexity_score: float = 10.0
    max_duration_score: float = 5.0
    max_energy_score: float = 10.0

    # ---------------------------------------------------------
    # LIMITES COGNITIVOS HUMANOS
    # ---------------------------------------------------------
    ultradian_limit: int = 90
    warmup_duration_limit: int = 10

    # ---------------------------------------------------------
    # DINÂMICA DE MOMENTUM
    # (Motivação comportamental)
    # ---------------------------------------------------------
    momentum_base_reward: float = 0.10
    momentum_decay_gap_minutes: int = 20
    momentum_decay_penalty: float = 0.15
    skip_penalty: float = 0.10

    # ---------------------------------------------------------
    # CONTRIBUIÇÕES PARA GANHO DE MOMENTUM
    # ---------------------------------------------------------
    momentum_energy_weight: float = 0.04
    momentum_complexity_weight: float = 0.03

    # ---------------------------------------------------------
    # FADIGA COGNITIVA
    # (Impacto de tarefas na energia)
    # ---------------------------------------------------------
    energy_fatigue_weight: float = 1.0
    complexity_fatigue_weight: float = 1.0

    # ---------------------------------------------------------
    # RECUPERAÇÃO DE ENERGIA
    # ---------------------------------------------------------
    rest_recovery_minutes_per_level: int = 15
    power_nap_min_minutes: int = 10

    # ---------------------------------------------------------
    # EXPLORAÇÃO DO MOTOR
    # (Anti-estagnação)
    # ---------------------------------------------------------
    exploration_noise: float = 0.5
