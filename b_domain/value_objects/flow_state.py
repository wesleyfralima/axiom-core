from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Optional

from a_core.base import ValueObject
from b_domain.value_objects import UserId, ContextId
from b_domain.value_objects.enums import EnergyLevel, MomentumTrend, TaskComplexity
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile


@dataclass(frozen=True, kw_only=True)
class UserFlowState(ValueObject):
    """
    Representa a 'consciência' do sistema sobre a condição do utilizador.
    Unifica a lógica comportamental de momentum com a precisão de tempo real.
    """

    user_id: UserId
    active_context_id: Optional[ContextId] = None

    # --- Âncoras de Tempo Real ---
    session_ends_at: datetime  # Quando o utilizador planeja parar
    focus_started_at: datetime  # Quando o bloco atual de foco começou

    # --- Dimensões Biopsicológicas ---
    current_energy: EnergyLevel

    # --- Momentum Dinâmico ---
    momentum_streak: int = 0
    momentum_score: float = 0.0  # 0.0 a 1.0
    last_completion_at: Optional[datetime] = None

    # --- Configurações de Sessão ---
    session_target_minutes: Optional[int] = None
    consecutive_skips: int = 0

    # ------------------------------------------------------------------
    # PROPRIEDADES DINÂMICAS (Tempo Real)
    # ------------------------------------------------------------------

    def get_available_minutes(self, now: datetime) -> int:
        """Calcula quanto tempo real resta até o fim da sessão."""
        if now >= self.session_ends_at:
            return 0
        delta: timedelta = self.session_ends_at - now
        return int(delta.total_seconds() // 60)

    def get_continuous_focus_minutes(self, now: datetime) -> int:
        """Calcula o tempo de foco ininterrupto para gatilho de pausa."""
        delta: timedelta = now - self.focus_started_at
        return int(delta.total_seconds() // 60)

    @property
    def momentum_trend(self) -> MomentumTrend:
        """Identifica a `MomentumTrend` com base no `momentum_score`."""
        if self.momentum_score >= 0.8:
            return MomentumTrend.RISING
        if self.momentum_score >= 0.4:
            return MomentumTrend.STABLE
        if self.momentum_score > 0:
            return MomentumTrend.FALLING
        return MomentumTrend.STAGNANT

    # ------------------------------------------------------------------
    # TRANSIÇÕES DE ESTADO (Imutabilidade)
    # ------------------------------------------------------------------

    def record_completion(
            self,
            now: datetime,
            energy: EnergyLevel,
            complexity: TaskComplexity,
            profile: UserBehaviorProfile,
    ) -> "UserFlowState":
        """
        Aumenta o Momentum (Dopamine) e drena a Energia (Fuel).
        """

        # 1. CÁLCULO DE MOMENTUM (Dopamina/Velocidade)
        interval_penalty = 0.0
        if self.last_completion_at:
            gap = (now - self.last_completion_at).total_seconds() / 60
            if gap > 20:
                interval_penalty = 0.15

        # Recompensa Ponderada: Tarefas difíceis geram mais momentum
        base_reward = profile.momentum_base_reward
        energy_bonus = energy.value * 0.04
        complexity_bonus = complexity.value * 0.03

        increment = base_reward + energy_bonus + complexity_bonus - interval_penalty
        new_momentum = min(1.0, self.momentum_score + increment)

        # 2. CÁLCULO DE DIMINUIÇÃO DE ENERGIA (Bateria)
        # Regra: Se a tarefa exigiu esforço Real (Energia ≥ Balanced)
        # ou esforço Mental (Complexidade ≥ Medium), o usuário se cansa.
        new_energy_val = self.current_energy.value

        # Esforço total da tarefa
        effort_load = energy.value + complexity.value

        # Se o esforço for significativo (ex: ≥ 4), reduzimos um nível de energia
        # HIGH (3) -> BALANCED (2) -> LOW (1)
        if effort_load >= 4:
            new_energy_val = max(EnergyLevel.LOW.value, new_energy_val - 1)

        return replace(
            self,
            momentum_streak=self.momentum_streak + 1,
            momentum_score=max(0.0, new_momentum),
            current_energy=EnergyLevel(new_energy_val),  # Atualiza a energia aqui!
            last_completion_at=now,
            consecutive_skips=0,
        )

    def record_skip(self, profile: UserBehaviorProfile) -> "UserFlowState":
        """Penalidade por recusa de sugestão (Hook Model)."""
        return replace(
            self,
            momentum_score=max(0.0, self.momentum_score - profile.skip_penalty),
            consecutive_skips=self.consecutive_skips + 1,
        )

    def reset_skips(self) -> "UserFlowState":
        """Redefine a quantidade de skips para zero."""
        return replace(self, consecutive_skips=0)

    def record_abandon(self) -> "UserFlowState":
        """Quebra total de fluxo."""
        return self.reset_momentum()

    def reset_momentum(self) -> "UserFlowState":
        """Redefine streak e score, mas mantém as âncoras de tempo da sessão."""
        return replace(self, momentum_streak=0, momentum_score=0.0)

    def update_context(self, now: datetime, context_id: ContextId) -> "UserFlowState":
        """Muda o contexto e reinicia o cronômetro de foco (Refresh cognitivo)."""
        return replace(
            self,
            active_context_id=context_id,
            focus_started_at=now
        )

    def renew_focus(self, now: datetime) -> "UserFlowState":
        """Redefine o cronômetro de foco (Tempo). Útil para intervenções cognitivas."""
        return replace(self, focus_started_at=now)

    def record_rest(self, minutes_rested: int) -> "UserFlowState":
        """
        Registra uma pausa e recupera o nível de energia proporcionalmente.
        Heurística: 15 minutos de descanso = +1 Nível de Energia.
        """

        # Cálculo da proporção (mínimo de 0 ganho)
        energy_gain: int = minutes_rested // 15

        # Bônus de "Power Nap": Se descansou entre 10 e 14 min,
        # garantido ao menos 1 nível de recuperação.
        if energy_gain == 0 and minutes_rested >= 10:
            energy_gain = 1

        # Supõe-se que o usuário não consiga atingir o
        # nível máximo de energia (EnergyLevel.PEAK) após
        # descansos, atingindo no máximo EnergyLevel.HIGH
        new_energy_val: int = min(
            EnergyLevel.HIGH.value,
            self.current_energy.value + energy_gain,
        )

        return replace(
            self,
            current_energy=EnergyLevel(new_energy_val),
            focus_started_at=self.focus_started_at  # Mantemos o foco, o renew_focus cuidará disso
        )
