from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import random
from typing import List, Optional

from a_core import ValueObject
from b_domain.entities import Task
from b_domain.value_objects.enums import MomentumTrend, TaskStatus
from b_domain.value_objects.flow_state import UserFlowState


@dataclass(frozen=True, kw_only=True)
class EngineConfig(ValueObject):
    """Hiper-parâmetros que regulam a sensibilidade do motor."""

    w_complexity: float = 2.0
    w_duration: float = 1.5
    w_energy: float = 2.5
    w_priority: float = 2.0

    ultradian_limit: int = 90
    warmup_duration_limit: int = 10

    max_complexity_score: float = 10.0
    max_duration_score: float = 5.0
    max_energy_score: float = 10.0

    exploration_noise: float = 0.5


class FlowDecisionType(str, Enum):
    TASK_EXECUTION = "task_execution"  # Sugestão de tarefa real do backlog
    SYSTEM_BREAK = "system_break"  # Pausa obrigatória (Ritmo Ultradiano)
    FRICTION_INTERVENTION = "friction_reset"  # Sugestão de quebra de tarefa (Muitos Skips)
    BACKLOG_EXHAUSTED = "backlog_exhausted"  # Sem tarefas pendentes, mas com tempo de sessão
    SESSION_COMPLETE = "session_complete"  # Fim do tempo planejado pelo usuário


@dataclass(frozen=True)
class FlowDecision(ValueObject):
    """Encapsula a inteligência do motor para o chamador."""
    decision_type: FlowDecisionType
    task: Optional[Task]
    reason: str
    score: float = 0.0


class FlowEngine:
    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()

    def get_next_action(self, candidate_tasks: List[Task], state: UserFlowState, now: datetime) -> FlowDecision:
        """
        Orquestrador do Fluxo: Segue a hierarquia de necessidades
        (Tempo → Biologia → Fricção → Backlog).
        """

        # 1. Limite de Tempo da Sessão
        if decision := self._check_session_limit(state, now):
            return decision
        # 2. Ritmo Ultradiano (Pausa Bio)
        if decision := self._check_ultradian_rhythm(state, now):
            return decision

        available_candidates: list[Task] = self._filter_available_tasks(candidate_tasks, now)

        # Se não há nenhuma candidata, tenta pegar as skipped
        if not available_candidates:
            available_candidates = self._filter_available_tasks(candidate_tasks, now, min_skip_min=0)

        # 3. Resistência Comportamental (Fricção)
        if decision := self._check_friction_resistance(available_candidates, state, now):
            return decision

        # 4. Disponibilidade de Backlog
        if not available_candidates:
            return self._handle_empty_backlog(state, now)

        # 5. Ranking de Tarefas Reais
        return self._suggest_optimal_task(available_candidates, state, now)

    def calculate_flow_score(self, task: Task, state: UserFlowState, now: datetime) -> float:

        # 1. VETO ABSOLUTO: Se não cabe no resto da sessão, score mínimo.
        available = state.get_available_minutes(now)
        if task.estimated_duration_minutes > available:
            return -1000.0

        # 2. JANELA COGNITIVA: Tempo até a próxima pausa ultradiana
        focus_time = state.get_continuous_focus_minutes(now)
        time_to_break = self.config.ultradian_limit - focus_time

        # Se a pausa já deveria ter ocorrido, time_to_break fica negativo.
        # Usamos max(1, ...) para evitar divisões por zero.
        target_window = min(available, max(1, time_to_break))

        # 3. PENALIDADE DE RITMO (Break Friction)
        # Se a tarefa estourar a janela de pausa, criamos um freio (0,0 a 1,0)
        break_friction = 1.0
        if task.estimated_duration_minutes > time_to_break:
            if time_to_break <= 0:
                break_friction = 0.1  # Pausa já passou do tempo: penalidade máxima
            else:
                # Penalidade proporcional: quanto mais estoura, menor o multiplicador
                break_friction = 0.5 * (time_to_break / task.estimated_duration_minutes)

        # 4. PILAR: ENERGIA (Físico)
        energy_diff = state.current_energy.value - task.required_energy_level.value
        if energy_diff < 0:
            energy_score = energy_diff * 2.5  # Penalidade por falta de energia
        elif energy_diff == 0:
            energy_score = self.config.max_energy_score
        else:
            energy_score = self.config.max_energy_score - (energy_diff * 0.2)

        # 5. PILAR: COMPLEXIDADE (Cognitivo)
        # Capacidade aumenta com o momentum_score (de 2 a 5)
        user_capacity = 2 + (state.momentum_score * 3)
        comp_diff = user_capacity - task.complexity.value
        if comp_diff < 0:
            complexity_score = comp_diff * 3.0  # Penalidade por "overload" cognitivo
        else:
            complexity_score = self.config.max_complexity_score - (comp_diff * 0.5)

        # 6. PILAR: DURAÇÃO (Encaixe na Janela)
        # Comparamos com a target_window (menor tempo entre pausa e fim da sessão)
        duration_ratio = task.estimated_duration_minutes / target_window
        # Se ratio > 1, a tarefa é maior que a janela: score cai.
        duration_score = self.config.max_duration_score / max(1.0, duration_ratio)

        # 7. PILAR: PRIORIDADE (Valor de Negócio)
        priority_score = float(task.priority.value)

        # 8. CÁLCULO DO BASE SCORE
        base_score = (
                (self.config.w_energy * energy_score) +
                (self.config.w_complexity * complexity_score) +
                (self.config.w_duration * duration_score) +
                (self.config.w_priority * priority_score)
        )

        # 9. MULTIPLICADORES (Momentum e Fricção)
        # O Momentum ajusta a inércia (Warmup vs Flow)
        momentum_mult = self._get_momentum_multiplier(task, state)

        final_score = base_score * momentum_mult

        # PROTEÇÃO: Só aplicamos break_friction se o score for positivo.
        # Se a tarefa já é ruim (negativa), a fricção não deve "ajudá-la" a subir.
        if final_score > 0:
            final_score *= break_friction
        else:
            # Se for negativa e estourar a pausa, pioramos ela ainda mais
            final_score /= max(0.1, break_friction)

        return final_score

    def _get_momentum_multiplier(self, task: Task, state: UserFlowState) -> float:
        """Extraído para limpar o método principal."""

        if state.momentum_trend == MomentumTrend.STAGNANT:
            if task.estimated_duration_minutes <= self.config.warmup_duration_limit:
                return 2.0  # Bônus para Quick Wins
            return 0.3  # Penalidade para tarefas longas sem ritmo

        if state.momentum_trend == MomentumTrend.RISING and task.priority.value >= 3:
            return 1.2  # Bônus de hiper-foco

        return 1.0

    # ------------------------------------------------------------------
    # MÉTODOS DE CRIAÇÃO DE TAREFAS (SYSTEM INTERVENTIONS)
    # ------------------------------------------------------------------

    @staticmethod
    def _create_ultradian_break(state: UserFlowState, now: datetime) -> Task:
        focus_time = state.get_continuous_focus_minutes(now)
        return Task.create_system_task(
            title="Pausa de Recuperação",
            duration=45,
            reason=f"Limite de foco profundo atingido ({focus_time}min). Sua bateria cognitiva precisa recarregar.",
            user_id=state.user_id
        )

    @staticmethod
    def _create_friction_intervention(target_task: Task, state: UserFlowState) -> Task:
        return Task.create_system_task(
            title=f"Micro-foco: {target_task.title.value}",
            duration=5,
            reason="Múltiplas recusas detectadas. Vamos apenas organizar o início desta tarefa?",
            user_id=state.user_id
        )

    @staticmethod
    def _create_planning_task(state: UserFlowState, available_min: int) -> Task:
        return Task.create_system_task(
            title="Planejamento de Fluxo",
            duration=min(10, available_min),
            reason="Backlog vazio no contexto atual. Use este tempo para organizar os próximos passos.",
            user_id=state.user_id
        )

    # ------------------------------------------------------------------
    # LÓGICA DE VERIFICAÇÃO (CHECKERS)
    # ------------------------------------------------------------------
    @staticmethod
    def _check_session_limit(state: UserFlowState, now: datetime) -> Optional[FlowDecision]:
        if state.get_available_minutes(now) <= 0:
            return FlowDecision(
                decision_type=FlowDecisionType.SESSION_COMPLETE,
                task=None,
                reason="O tempo planejado para esta sessão esgotou."
            )
        return None

    def _check_ultradian_rhythm(self, state: UserFlowState, now: datetime) -> Optional[FlowDecision]:

        focus_time = state.get_continuous_focus_minutes(now)

        if focus_time >= self.config.ultradian_limit:
            return FlowDecision(
                decision_type=FlowDecisionType.SYSTEM_BREAK,
                task=self._create_ultradian_break(state, now),
                reason=f"Limite Ultradiano de {self.config.ultradian_limit}min atingido."
            )
        return None

    def _check_friction_resistance(self, tasks: List[Task], state: UserFlowState, now: datetime) -> FlowDecision | None:
        if getattr(state, 'consecutive_skips', 0) >= 3:
            # Pegamos a melhor tarefa real para propor a quebra dela
            best_task = self._rank_and_pick(tasks, state, now)
            if best_task and best_task.estimated_duration_minutes > 15:
                return FlowDecision(
                    decision_type=FlowDecisionType.FRICTION_INTERVENTION,
                    task=self._create_friction_intervention(best_task, state),
                    reason="Intervenção de Fricção: Reduzindo barreira de entrada devido a recusas consecutivas."
                )
        return None

    def _handle_empty_backlog(self, state: UserFlowState, now: datetime) -> FlowDecision:
        available_min = state.get_available_minutes(now)
        return FlowDecision(
            decision_type=FlowDecisionType.BACKLOG_EXHAUSTED,
            task=self._create_planning_task(state, available_min),
            reason="Backlog exaurido mas tempo de sessão ainda disponível."
        )

    def _suggest_optimal_task(self, tasks: List[Task], state: UserFlowState, now: datetime) -> FlowDecision:
        """Selects the most suitable task for execution given the user's current state.

        The method filters tasks based on available time and active context,
        then ranks the valid tasks to pick the best match. If no task fits,
        it returns a decision indicating that the backlog is exhausted.

        Args:
            tasks (List[Task]): Candidate tasks to evaluate.
            state (UserFlowState): Current user flow state, including context and time.
            now (datetime): Current timestamp used to calculate availability.

        Returns:
            FlowDecision: Decision object indicating either a task to execute
            or that no viable task remains.
        """

        available_min: int = state.get_available_minutes(now)

        # Viability filter:
        # Even though tasks should already be pre-filtered by the repository,
        # we ensure here that only tasks fitting the remaining time and active context are considered.
        valid_tasks: list[Task] = [
            t for t in tasks
            if t.estimated_duration_minutes <= available_min and t.context_id == state.active_context_id
        ]

        if not valid_tasks:
            return FlowDecision(
                decision_type=FlowDecisionType.BACKLOG_EXHAUSTED,
                task=None,
                reason="No pending task fits the remaining session time."
            )

        # Rank tasks and pick the best candidate according to state and current time.
        best_task: Task = self._rank_and_pick(valid_tasks, state, now)

        return FlowDecision(
            decision_type=FlowDecisionType.TASK_EXECUTION,
            task=best_task,
            reason="Best match for your current energy and momentum.",
            score=self.calculate_flow_score(best_task, state, now)
        )

    def _rank_and_pick(self, tasks: List[Task], state: UserFlowState, now: datetime) -> Optional[Task]:
        best_task = None
        best_score = float('-inf')

        for task in tasks:
            score = self.calculate_flow_score(task, state, now)

            # EXPLORATION NOISE (pequena aleatoriedade controlada)
            score += random.uniform(
                -self.config.exploration_noise,
                self.config.exploration_noise
            )

            if score > best_score:
                best_score = score
                best_task = task

        return best_task

    @staticmethod
    def _filter_available_tasks(tasks: List[Task], now: datetime, min_skip_min: int = 15) -> List[Task]:
        """
        Remove tarefas que foram puladas recentemente (Cool-off de 15 min).
        Tarefas PENDING passam direto. Tarefas SKIPPED esperam o tempo.
        """

        filtered: list[Task] = []

        for t in tasks:
            if t.status == TaskStatus.SKIPPED and t.last_skipped_at:
                minutes_since_skip: float = (now - t.last_skipped_at).total_seconds() // 60
                if minutes_since_skip < min_skip_min:  # "Geladeira" de 15 minutos
                    continue
            filtered.append(t)

        return filtered
