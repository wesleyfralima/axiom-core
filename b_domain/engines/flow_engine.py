import random
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from a_core import ValueObject
from b_domain.entities import Task
from b_domain.value_objects.enums import MomentumTrend, TaskStatus
from b_domain.value_objects.flow_state import UserFlowState
from b_domain.value_objects.user_behavior_profile import UserBehaviorProfile


class FlowDecisionType(str, Enum):
    """Represents the types of flow decisions in the task engine.

    These decision types guide how the system responds to user state
    and task availability during a work session.

    Attributes:
        TASK_EXECUTION (str): Suggests execution of a real task from the backlog.
        SYSTEM_BREAK (str): Mandatory break enforced by ultradian rhythm.
        FRICTION_INTERVENTION (str): Suggests breaking a task due to excessive skips.
        BACKLOG_EXHAUSTED (str): Indicates no pending tasks remain, but session time is available.
        SESSION_COMPLETE (str): Marks the end of the user’s planned session.
    """
    TASK_EXECUTION = "task_execution"  # Suggestion of a real backlog task
    SYSTEM_BREAK = "system_break"  # Mandatory pause (Ultradian rhythm)
    FRICTION_INTERVENTION = "friction_reset"  # Suggestion to break task (too many skips)
    BACKLOG_EXHAUSTED = "backlog_exhausted"  # No pending tasks available, but session time remains
    SESSION_COMPLETE = "session_complete"  # End of planned session


@dataclass(frozen=True)
class FlowDecision(ValueObject):
    """Encapsulates the decision intelligence of the flow engine.

    A `FlowDecision` represents the outcome of the engine’s reasoning
    about what should happen next in a user’s workflow. It can suggest
    task execution, breaks, interventions, or session completion.

    Attributes:
        decision_type (FlowDecisionType): The type of decision made by the engine.
        task (Optional[Task]): The task associated with the decision, if applicable.
        reason (str): Explanation or rationale for the decision.
        score (float): Confidence score or priority weight for the decision.
    """
    decision_type: FlowDecisionType
    task: Optional[Task]
    reason: str
    score: float = 0.0


class FlowEngine:
    """Orchestrates the flow of task execution decisions.

    The engine follows a hierarchy of needs to determine the next action:
    1. Session time limits
    2. Biological rhythms (ultradian breaks)
    3. Behavioral friction (resistance due to skips)
    4. Backlog availability
    5. Task ranking and selection
    """

    def get_next_action(
            self,
            candidate_tasks: List[Task],
            state: UserFlowState,
            profile: UserBehaviorProfile,
            now: datetime,
    ) -> FlowDecision:
        """Determine the next action in the flow.

        Applies a hierarchy of checks to decide whether to end the session,
        enforce a biological break, intervene due to friction, handle an empty
        backlog, or suggest an optimal task.

        Args:
            candidate_tasks (List[Task]): List of candidate tasks from the backlog.
            state (UserFlowState): Current state of the user’s flow.
            profile (UserBehaviorProfile): Learned behavioral profile of the user.
            now (datetime): Current timestamp.

        Returns:
            FlowDecision: The decision outcome, which may be a task suggestion,
            break, intervention, or session completion.
        """

        # 1. Session time limit
        if decision := self._check_session_limit(state, now):
            return decision

        # 2. Ultradian rhythm (biological break)
        if decision := self._check_ultradian_rhythm(state, profile, now):
            return decision

        available_candidates: list[Task] = self._filter_available_tasks(candidate_tasks, now)

        # If no candidates are available, retry with skipped tasks
        if not available_candidates:
            available_candidates = self._filter_available_tasks(candidate_tasks, now, min_skip_min=0)

        # 3. Behavioral friction (resistance)
        if decision := self._check_friction_resistance(available_candidates, state, profile, now):
            return decision

        # 4. Backlog availability
        if not available_candidates:
            return self._handle_empty_backlog(state, now)

        # 5. Task ranking
        return self._suggest_optimal_task(available_candidates, state, profile, now)

    def calculate_flow_score(
            self,
            task: Task,
            state: UserFlowState,
            profile: UserBehaviorProfile,
            now: datetime,
    ) -> float:
        """Calculate the flow score for a given task.

        The score is based on multiple pillars:
        - Energy alignment
        - Complexity fit (capacity + preference)
        - Duration fit (temporal window + preference)
        - Priority value
        - Momentum multiplier
        - Break friction penalties

        Args:
            task (Task): The task to evaluate.
            state (UserFlowState): Current state of the user’s flow.
            profile (UserBehaviorProfile): Learned behavioral profile of the user.
            now (datetime): Current timestamp.

        Returns:
            float: The computed flow score for the task.
        """

        # 1. Absolute veto: if task doesn’t fit in remaining session
        available = state.get_available_minutes(now)
        if task.estimated_duration_minutes > available:
            return -1000.0

        # 2. Sustainable capacity limits
        if task.estimated_duration_minutes > profile.max_sustainable_duration:
            return -500.0
        if task.complexity.value > profile.max_sustainable_complexity:
            return -500.0

        # 3. Cognitive window: time until next ultradian break
        focus_time = state.get_continuous_focus_minutes(now)
        time_to_break = profile.ultradian_limit - focus_time
        target_window = min(available, max(1, time_to_break))

        # Break friction penalty
        break_friction = 1.0
        if task.estimated_duration_minutes > time_to_break:
            if time_to_break <= 0:
                break_friction = 0.1
            else:
                break_friction = 0.5 * (time_to_break / task.estimated_duration_minutes)

        # Pillar 1 — Energy
        energy_diff: int = state.current_energy.value - task.required_energy_level.value
        if energy_diff < 0:
            energy_score = energy_diff * 2.5
        elif energy_diff == 0:
            energy_score = profile.max_energy_score
        else:
            energy_score = profile.max_energy_score - (energy_diff * 0.2)

        # Pillar 2 — Complexity
        user_capacity: float = 2 + (state.momentum_score * 3)
        comp_diff: float = user_capacity - task.complexity.value
        if comp_diff < 0:
            capacity_score = comp_diff * 3.0
        else:
            capacity_score = profile.max_complexity_score - (comp_diff * 0.5)

        preferred_complexity: float = profile.preferred_task_complexity
        complexity_distance: float = abs(task.complexity.value - preferred_complexity)
        preference_score: float = profile.max_complexity_score / (
                1 + complexity_distance / preferred_complexity
        )
        complexity_score: float = 0.6 * capacity_score + 0.4 * preference_score

        # Pillar 3 — Duration
        duration_ratio: float = task.estimated_duration_minutes / target_window
        duration_fit_score: float = profile.max_duration_score / (
                1 + abs(duration_ratio - 1.0)
        )
        preferred_duration: float = max(1.0, profile.preferred_task_duration)
        duration_distance: float = abs(task.estimated_duration_minutes - preferred_duration)
        duration_preference_score: float = profile.max_duration_score / (
                1 + duration_distance / preferred_duration
        )
        duration_score: float = 0.7 * duration_fit_score + 0.3 * duration_preference_score

        # Pillar 4 — Priority
        priority_score: float = float(task.priority.value)

        # Base score
        base_score: float = (
                (profile.w_energy * energy_score) +
                (profile.w_complexity * complexity_score) +
                (profile.w_duration * duration_score) +
                (profile.w_priority * priority_score)
        )

        # Momentum multiplier
        momentum_mult: float = self._get_momentum_multiplier(task, state, profile)
        final_score: float = base_score * momentum_mult

        # Break friction adjustment
        if final_score > 0:
            final_score *= break_friction
        else:
            final_score /= max(0.1, break_friction)

        return final_score

    @staticmethod
    def _get_momentum_multiplier(
            task: Task,
            state: UserFlowState,
            profile: UserBehaviorProfile,
    ) -> float:
        """Calculate the momentum multiplier for a task.

        Adjusts the task’s score based on the current momentum trend
        of the user. Momentum reflects behavioral inertia, rising flow,
        stable deep work, or falling fatigue. Each trend modifies the
        multiplier differently to encourage or discourage certain tasks.

        Args:
            task (Task): The task being evaluated.
            state (UserFlowState): Current state of the user’s flow.
            profile (UserBehaviorProfile): Learned behavioral profile of the user.

        Returns:
            float: The momentum multiplier applied to the task score.
        """

        # 1. Total inertia → Quick wins
        if state.momentum_trend == MomentumTrend.STAGNANT:
            if task.estimated_duration_minutes <= min(
                    float(profile.warmup_duration_limit),
                    profile.preferred_task_duration * 0.5
            ):
                return 2.0  # Bonus for micro tasks
            return 0.3  # Penalty for long tasks

        # 2. Rising momentum → Leverage progress
        if state.momentum_trend == MomentumTrend.RISING:
            if task.priority.value >= 3:
                return 1.2
            return 1.05

        # 3. Stable flow → Deep work
        if state.momentum_trend == MomentumTrend.STABLE:
            if task.estimated_duration_minutes >= profile.preferred_task_duration:
                return 1.2
            return 1.0

        # 4. Falling momentum → Reduce load
        if state.momentum_trend == MomentumTrend.FALLING:
            if task.complexity.value <= profile.preferred_task_complexity:
                return 1.1
            return 0.6

        # Default multiplier
        return 1.0

    # ------------------------------------------------------------------
    # TASK CREATION METHODS (SYSTEM INTERVENTIONS)
    # ------------------------------------------------------------------

    @staticmethod
    def _create_ultradian_break(state: UserFlowState, now: datetime) -> Task:
        """Create a system task for an ultradian recovery break.

        This intervention enforces a mandatory pause when the user’s
        continuous focus time exceeds the ultradian limit, signaling
        cognitive fatigue and the need for recovery.

        Args:
            state (UserFlowState): Current state of the user’s flow.
            now (datetime): Current timestamp.

        Returns:
            Task: A system-generated task representing a recovery break.
        """
        focus_time = state.get_continuous_focus_minutes(now)
        return Task.create_system_task(
            title="Recovery Break",
            duration=45,
            reason=f"Deep focus limit reached ({focus_time}min). Your cognitive battery needs to recharge.",
            user_id=state.user_id
        )

    @staticmethod
    def _create_friction_intervention(target_task: Task, state: UserFlowState) -> Task:
        """Create a system task to reduce friction after repeated skips.

        This intervention suggests a micro-focus activity to help the user
        start a task that has been repeatedly refused, lowering resistance
        and encouraging gradual engagement.

        Args:
            target_task (Task): The task that has been repeatedly skipped.
            state (UserFlowState): Current state of the user’s flow.

        Returns:
            Task: A system-generated micro-focus task.
        """
        return Task.create_system_task(
            title=f"Micro-focus: {target_task.title.value}",
            duration=5,
            reason="Multiple refusals detected. Let’s just organize the start of this task?",
            user_id=state.user_id
        )

    @staticmethod
    def _create_planning_task(state: UserFlowState, available_min: int) -> Task:
        """Create a system task for planning when backlog is empty.

        This intervention uses available session time to encourage the user
        to organize upcoming tasks and prepare for future flow cycles.

        Args:
            state (UserFlowState): Current state of the user’s flow.
            available_min (int): Available minutes remaining in the session.

        Returns:
            Task: A system-generated planning task.
        """
        return Task.create_system_task(
            title="Flow Planning",
            duration=min(10, available_min),
            reason="Backlog is empty in the current context. Use this time to organize next steps.",
            user_id=state.user_id
        )

    # ------------------------------------------------------------------
    # CHECKER LOGIC (VALIDATION METHODS)
    # ------------------------------------------------------------------

    @staticmethod
    def _check_session_limit(state: UserFlowState, now: datetime) -> Optional[FlowDecision]:
        """Check if the session time limit has been reached.

        Args:
            state (UserFlowState): Current user flow state.
            now (datetime): Current timestamp.

        Returns:
            Optional[FlowDecision]: A decision marking session completion
            if no time remains, otherwise None.
        """

        if state.get_available_minutes(now) <= 0:
            return FlowDecision(
                decision_type=FlowDecisionType.SESSION_COMPLETE,
                task=None,
                reason="Planned session time has been exhausted."
            )
        return None

    def _check_ultradian_rhythm(
            self,
            state: UserFlowState,
            profile: UserBehaviorProfile,
            now: datetime,
    ) -> Optional[FlowDecision]:
        """Check if the ultradian rhythm limit has been exceeded.

        Enforces a mandatory break when continuous focus time surpasses
        the user’s ultradian limit.

        Args:
            state (UserFlowState): Current user flow state.
            profile (UserBehaviorProfile): Learned behavioral profile of the user.
            now (datetime): Current timestamp.

        Returns:
            Optional[FlowDecision]: A decision to enforce a system break
            if the limit is reached, otherwise None.
        """

        focus_time: int = state.get_continuous_focus_minutes(now)

        if focus_time >= profile.ultradian_limit:
            return FlowDecision(
                decision_type=FlowDecisionType.SYSTEM_BREAK,
                task=self._create_ultradian_break(state, now),
                reason=f"Ultradian limit of {profile.ultradian_limit} minutes reached."
            )
        return None

    def _check_friction_resistance(
            self,
            tasks: List[Task],
            state: UserFlowState,
            profile: UserBehaviorProfile,
            now: datetime,
    ) -> Optional[FlowDecision]:
        """Check if friction resistance requires intervention.

        If the user has consecutively skipped multiple tasks, the engine
        proposes a friction intervention to reduce entry barriers.

        Args:
            tasks (List[Task]): Candidate tasks to evaluate.
            state (UserFlowState): Current user flow state.
            profile (UserBehaviorProfile): Learned behavioral profile of the user.
            now (datetime): Current timestamp.

        Returns:
            Optional[FlowDecision]: A friction intervention decision if
            conditions are met, otherwise None.
        """

        if getattr(state, 'consecutive_skips', 0) >= 3:
            best_task = self._rank_and_pick(tasks, state, profile, now)
            if best_task and best_task.estimated_duration_minutes > 15:
                return FlowDecision(
                    decision_type=FlowDecisionType.FRICTION_INTERVENTION,
                    task=self._create_friction_intervention(best_task, state),
                    reason="Friction intervention: reducing entry barrier due to consecutive refusals."
                )
        return None

    def _handle_empty_backlog(self, state: UserFlowState, now: datetime) -> FlowDecision:
        """Handle the case when the backlog is empty.

        Creates a planning task to use remaining session time productively.

        Args:
            state (UserFlowState): Current user flow state.
            now (datetime): Current timestamp.

        Returns:
            FlowDecision: A decision to create a planning task.
        """

        available_min: int = state.get_available_minutes(now)
        return FlowDecision(
            decision_type=FlowDecisionType.BACKLOG_EXHAUSTED,
            task=self._create_planning_task(state, available_min),
            reason="Backlog exhausted but session time still available."
        )

    def _suggest_optimal_task(
            self,
            tasks: List[Task],
            state: UserFlowState,
            profile: UserBehaviorProfile,
            now: datetime,
    ) -> FlowDecision:
        """Select the most suitable task for execution.

        Filters tasks based on available time and active context,
        ranks them, and returns the best candidate. If no task fits,
        returns a backlog exhausted decision.

        Args:
            tasks (List[Task]): Candidate tasks to evaluate.
            state (UserFlowState): Current user flow state.
            profile (UserBehaviorProfile): Learned behavioral profile of the user.
            now (datetime): Current timestamp.

        Returns:
            FlowDecision: Decision object indicating either a task to execute
            or that no viable task remains.
        """

        available_min: int = state.get_available_minutes(now)

        valid_tasks: list[Task] = [
            t for t in tasks
            if t.estimated_duration_minutes <= available_min
               and (
                       state.active_context_id is None
                       or t.context_id == state.active_context_id
               )
        ]

        if not valid_tasks:
            return FlowDecision(
                decision_type=FlowDecisionType.BACKLOG_EXHAUSTED,
                task=None,
                reason="No pending task fits the remaining session time."
            )

        best_task: Task = self._rank_and_pick(valid_tasks, state, profile, now)

        return FlowDecision(
            decision_type=FlowDecisionType.TASK_EXECUTION,
            task=best_task,
            reason="Best match for current energy and momentum.",
            score=self.calculate_flow_score(best_task, state, profile, now)
        )

    def _rank_and_pick(
            self,
            tasks: List[Task],
            state: UserFlowState,
            profile: UserBehaviorProfile,
            now: datetime
    ) -> Optional[Task]:
        """Rank candidate tasks and select the best one.

        Each task is scored using `calculate_flow_score`, with added
        exploration noise to introduce controlled randomness. Diversity
        penalties are applied if the task complexity is too similar to
        the last executed task, encouraging variety.

        Args:
            tasks (List[Task]): Candidate tasks to evaluate.
            state (UserFlowState): Current user flow state.
            profile (UserBehaviorProfile): Learned behavioral profile of the user.
            now (datetime): Current timestamp.

        Returns:
            Optional[Task]: The highest-scoring task, or None if no tasks are available.
        """

        best_task = None
        best_score = float('-inf')

        for task in tasks:
            score: float = self.calculate_flow_score(task, state, profile, now)

            # Exploration noise (controlled randomness)
            score += random.uniform(
                -profile.exploration_noise * 0.5,
                profile.exploration_noise * 0.5
            )

            # Diversity penalty: discourage repeating similar complexity
            if state.last_task_complexity is not None:
                if abs(task.complexity.value - state.last_task_complexity.value) < 1:
                    score -= profile.diversity_penalty

            if score > best_score:
                best_score = score
                best_task = task

        return best_task

    @staticmethod
    def _filter_available_tasks(tasks: List[Task], now: datetime, min_skip_min: int = 15) -> List[Task]:
        """Filter tasks based on skip cooldown.

        Removes tasks that were skipped too recently, enforcing a
        cooldown period before they can be reconsidered. Pending tasks
        are always included.

        Args:
            tasks (List[Task]): Candidate tasks to filter.
            now (datetime): Current timestamp.
            min_skip_min (int): Minimum cooldown in minutes for skipped tasks (default 15).

        Returns:
            List[Task]: Filtered list of tasks that are eligible for execution.
        """

        filtered: list[Task] = []

        for t in tasks:
            if t.status == TaskStatus.SKIPPED and t.last_skipped_at:
                minutes_since_skip: float = (now - t.last_skipped_at).total_seconds() / 60
                if minutes_since_skip < min_skip_min:  # Skip cooldown
                    continue
            filtered.append(t)

        return filtered
