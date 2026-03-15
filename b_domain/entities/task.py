from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional, List, Set

from a_core import Entity
from a_core.exceptions import InvalidStateTransition, ValidationException
from b_domain.events.task_events import TaskCompletedEvent
from b_domain.value_objects import TaskId, Title, Description, TaskStatus, Priority
from b_domain.value_objects.dates import DueDate
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity
from b_domain.value_objects.identifiers import UserId, ContextId
from b_domain.value_objects.recurrences import RecurrenceRule


@dataclass(kw_only=True)
class Task(Entity):
    """Represents a Task entity with business rules and validation."""

    # Identifications
    id: TaskId
    user_id: UserId

    # Basic fields
    description: Description
    priority: Priority
    status: TaskStatus
    title: Title

    # Optional relationships
    due_date: DueDate = field(default_factory=DueDate.empty)
    parent_id: Optional[TaskId] = None
    recurrence: Optional[RecurrenceRule] = None

    context_id: Optional[ContextId] = None

    # Grafo de dependências: IDs de outras tarefas que bloqueiam esta
    depends_on: Set[TaskId] = field(default_factory=set)

    # Nível de energia necessário (GTD-style)
    # Pode ser um Enum: LOW, MEDIUM, HIGH
    required_energy_level: EnergyLevel = EnergyLevel.BALANCED
    complexity: TaskComplexity = TaskComplexity.MEDIUM
    estimated_duration_minutes: int = 30

    # --- Campos Comportamentais (Telemetria) ---
    success_count: int = 0
    attempt_count: int = 0
    average_duration_minutes: int = 0
    last_skipped_at: Optional[datetime] = None

    is_system_generated: bool = False

    # Subtasks list is not persisted directly as a column,
    # but is useful for hydrating the object in memory
    _subtasks: List['Task'] = field(default_factory=list, repr=False)

    def __hash__(self) -> int:
        """
        Torna a Entidade hashable baseando-se apenas na sua identidade única.
        Isso permite que a Task seja usada em sets (como no Unit of Work).
        """
        return hash(self.id)

    @classmethod
    def create(
            cls,
            now: datetime,
            user_id: UserId,
            title: Title,
            description: Description = Description(""),
            priority: Priority = Priority.MEDIUM,
            required_energy_level: EnergyLevel = EnergyLevel.BALANCED,
            context_id: Optional[ContextId] = None,
            parent_id: Optional[TaskId] = None,
            recurrence: Optional[RecurrenceRule] = None,
            due_date: Optional[datetime] = None,
            is_floating: bool = True,
            tz_name: str = "UTC",
            complexity: TaskComplexity = TaskComplexity.MEDIUM,
            estimated_duration_minutes: int = 30,
            success_count: int = 0,
            attempt_count: int = 0,
            average_duration_minutes: int = 0,
    ) -> 'Task':
        """Factory method to create a new clean Task.

        Args:
            now (datetime): the current time.
            user_id (str): User ID.
            title (str): Task title.
            description (str, optional): Task description. Defaults to "".
            priority (str, optional): Task priority. Defaults to "medium".
            required_energy_level (int): Energy required (1=Low, 2=Medium, 3=High).
            context_id (Optional[ContextId]): The focus context (e.g., 'Work', 'Home').
            parent_id (Optional[TaskId], optional): Parent task ID. Defaults to None.
            recurrence (Optional[RecurrenceRule], optional): Recurrence rule. Defaults to None.
            due_date (Optional[datetime], optional): Due date. Defaults to None.
            is_floating (bool): Task floating. Defaults to True.
            tz_name (str): Time zone. Defaults to "UTC".
            complexity (TaskComplexity): Task complexity. Defaults to "medium".
            estimated_duration_minutes (int): Task estimated duration minutes. Defaults to 30.
            success_count (int): Task success count. Defaults to 0.
            attempt_count (int): Task attempt count. Defaults to 0.
            average_duration_minutes (int): Task average (real) duration minutes. Defaults to 0.

        Returns:
            Task: A new Task instance.
        """

        due: DueDate

        if due_date is None:
            due = DueDate.empty()
        elif is_floating:
            due = DueDate.floating(due_date, tz_name)
        else:
            due = DueDate.fixed(due_date)

        if recurrence and due.value:
            # Ensure recurrence aligns with the task's due date type.
            # If they differ, enforce consistency between floating/fixed rules.
            if due.is_floating and recurrence.start_date.tzinfo is not None:
                raise ValidationException(
                    "Floating task must have a naive recurrence start_date"
                )
            if not due.is_floating and recurrence.start_date.tzinfo is None:
                raise ValidationException(
                    "Fixed task must have an aware (UTC) recurrence start_date"
                )

        return cls(
            id=TaskId(),
            user_id=user_id,
            title=title,
            description=description,
            status=TaskStatus.PENDING,
            priority=Priority(priority),
            required_energy_level=EnergyLevel(required_energy_level),
            context_id=context_id,
            due_date=due,
            created_at=now,
            updated_at=now,
            parent_id=parent_id,
            recurrence=recurrence,
            complexity=complexity,
            estimated_duration_minutes=estimated_duration_minutes,
            success_count=success_count,
            attempt_count=attempt_count,
            average_duration_minutes=average_duration_minutes,
        )

    @classmethod
    def create_system_task(cls, title: str, duration: int, reason: str, user_id: UserId) -> "Task":
        """Factory para criar uma tarefa de pausa que não existe no DB."""
        return cls(
            id=TaskId(),  # ID temporário, não será persistido
            user_id=user_id,
            title=Title(title),
            description=Description(reason),
            status=TaskStatus.PENDING,
            priority=Priority.HIGH,
            required_energy_level=EnergyLevel.LOW,
            estimated_duration_minutes=duration,
            is_system_generated=True,
        )

    def is_suitable_for(self, current_energy: EnergyLevel) -> bool:
        """Verifica se a tarefa cabe no nível de energia atual do usuário."""
        return self.required_energy_level <= current_energy

    def add_dependency(self, target_id: TaskId):
        if target_id == self.id:
            raise ValidationException("A task cannot depend on itself.")
        self.depends_on.add(target_id)

    def remove_dependency(self, target_id: TaskId):
        self.depends_on.discard(target_id)

    @property
    def is_blocked(self) -> bool:
        """Uma tarefa está bloqueada se houver alguma dependência pendente."""
        return len(self.depends_on) > 0

    def create_next_occurrence(self, now: datetime, catch_up: bool = True) -> Optional['Task']:
        """Generate the next occurrence of this task.

        Depending on the mode, either generates the strict sequential next
        occurrence (financial use case) or skips overdue occurrences until
        a future one is found (habit use case).

        Args:
            now (datetime): Current timestamp used for comparison and task creation.
            catch_up (bool, optional):
                - If True (default), skips overdue occurrences and creates the next
                  future occurrence (habit mode).
                - If False, creates the strict sequential next occurrence regardless
                  of whether it is in the past (financial mode).

        Returns:
            Optional[Task]: A new Task entity representing the next occurrence,
            or None if recurrence has ended (e.g., reached count or until).
        """

        if not self.recurrence or not self.due_date.value:
            return None

        # 1. Initial reference
        next_dt: datetime | None
        last_reference: datetime | None = self.due_date.value

        # -------------------------------------------------------
        # Strategy 1: Strict mode (Financial)
        # -------------------------------------------------------
        if not catch_up:
            next_dt = self.recurrence.get_next_occurrence(last_occurrence=last_reference)
            if next_dt:
                return self._recreate_task_with_date(now, next_dt)
            else:
                return None

        # -------------------------------------------------------
        # Strategy 2: Catch-up mode (Habit)
        # -------------------------------------------------------
        while True:
            next_dt = self.recurrence.get_next_occurrence(last_occurrence=last_reference)

            # End of recurrence (Count/Until reached)
            if not next_dt:
                return None

            # Normalize timezone for comparison
            comparison_now: datetime = now
            if next_dt.tzinfo is None and now.tzinfo is not None:
                comparison_now = now.replace(tzinfo=None)
            elif next_dt.tzinfo is not None and now.tzinfo is None:
                comparison_now = now.replace(tzinfo=next_dt.tzinfo)

            # Found a future date?
            if next_dt > comparison_now:
                return self._recreate_task_with_date(now, next_dt)

            # Otherwise, continue iterating
            last_reference = next_dt

    def _recreate_task_with_date(self, now: datetime, new_date: datetime) -> 'Task':
        """Private helper to clone the task with a new due date.

        Preserves floating vs fixed semantics when reconstructing the DueDate
        and ensures recurrence continues in the new task.

        Args:
            now (datetime): Current timestamp used for task creation.
            new_date (datetime): The next occurrence date.

        Returns:
            Task: A new Task entity with updated due date.
        """

        # Rebuild DueDate VO preserving floating/fixed semantics
        if self.due_date.is_floating:
            new_due_vo = DueDate.floating(new_date, source_tz=self.due_date.timezone)
        else:
            new_due_vo = DueDate.fixed(new_date)

        new_recurrence = replace(self.recurrence, start_date=new_due_vo.value)

        return Task.create(
            now=now,
            user_id=self.user_id,
            title=self.title,
            description=self.description,
            priority=self.priority,
            due_date=new_due_vo.value,
            is_floating=new_due_vo.is_floating,
            tz_name=new_due_vo.timezone,
            parent_id=self.parent_id,
            recurrence=new_recurrence,
        )

    def next_occurrence_due_date(self) -> Optional['DueDate']:
        """Return the next due date based on recurrence rules.

        Determines the next occurrence from the current due date and
        reconstructs a new DueDate object while preserving metadata
        such as floating/aware status and timezone.

        Returns:
            Optional[DueDate]: The next due date if recurrence applies,
            otherwise None.
        """

        if not self.recurrence or not self.due_date.value:
            return None

        # RecurrenceRule returns a datetime (naive or aware depending on input)
        next_dt: datetime | None = self.recurrence.get_next_occurrence(
            last_occurrence=self.due_date.value,
        )

        if not next_dt:
            return None

        # Reconstruction: preserve metadata from the original DueDate
        if self.due_date.is_floating:
            # next_dt will already be naive from RecurrenceRule
            return DueDate.floating(next_dt, source_tz=self.due_date.timezone)
        else:
            # next_dt will already be aware (UTC) from RecurrenceRule
            return DueDate.fixed(next_dt)

    def rename(self, now: datetime, new_title: str) -> None:
        """Update the task title.

        Args:
            now (datetime): The current time.
            new_title (str): New title text.
        """
        self.title = Title(new_title)
        self._touch(now)

    def update_description(self, now: datetime, new_description: str) -> None:
        """Update the task description."""
        self.description = Description(new_description)
        self._touch(now)

    def change_status(self, now: datetime, new_status: "TaskStatus"):
        if not self.status.can_transition_to(new_status):
            raise InvalidStateTransition(
                f"Cannot change task status from {self.status} to {new_status}"
            )
        self.status = new_status
        self._touch(now)

    def update_priority(self, now: datetime, new_priority: Priority) -> None:
        """Update the task priority.

        Args:
            now (datetime): Current time.
            new_priority (str): New priority value.
        """
        self.priority = new_priority
        self._touch(now)

    def update_due_date(
            self,
            now: datetime,
            new_dt: Optional[datetime],
            is_floating: bool = True,
            tz_name: Optional[str] = None
    ) -> None:
        """
        Atualiza o prazo da tarefa utilizando as factories do DueDate.

        Args:
            now: Timestamp para o updated_at.
            new_dt: O novo datetime bruto vindo do DTO.
            is_floating: Define se a nova data deve ser tratada como Floating ou Fixed.
            tz_name: Nome IANA do timezone (obrigatório se for floating).
        """

        if new_dt is None:
            self.due_date = DueDate.empty()
            self._touch(now)
            return

        try:
            if is_floating:
                # O DueDate.floating espera um naive datetime e uma string de TZ
                # Se o DTO enviou aware, normalizamos para naive conforme a regra do DueDate
                naive_dt = new_dt if new_dt.tzinfo is None else new_dt.replace(tzinfo=None)

                # Usamos o tz_name fornecido ou o da própria tarefa como fallback
                effective_tz = tz_name or self.due_date.timezone or "UTC"
                self.due_date = DueDate.floating(naive_dt, effective_tz)
            else:
                # Para Fixed, o DueDate.fixed exige que seja aware
                aware_dt = new_dt
                if aware_dt.tzinfo is None:
                    # Se vier naive, assumimos UTC ou o TZ da tarefa para tornar aware
                    aware_dt = aware_dt.replace(tzinfo=timezone.utc)

                self.due_date = DueDate.fixed(aware_dt)

            self._touch(now)

        except ValidationException as e:
            # Relançamos para que o UseCase capture e trate como erro de negócio
            raise e

    def mark_as_done(self, now: datetime, actual_minutes: int = 0) -> None:
        """Mark the task as completed."""
        self.change_status(now, TaskStatus.DONE)
        self.add_event(TaskCompletedEvent(
            task_id=self.id,
            user_id=self.user_id,
            estimated_minutes=self.estimated_duration_minutes,
            actual_minutes=actual_minutes,
            energy_level_used=self.required_energy_level,
            task_complexity=self.complexity,
        ))

    def mark_as_cancelled(self, now: datetime) -> None:
        """Mark the task as cancelled."""
        self.change_status(now, TaskStatus.CANCELLED)

    def reopen(self, now: datetime) -> None:
        """Reopen the task (set status back to pending)."""
        self.change_status(now, TaskStatus.REOPENED)

    def archive(self, now: datetime) -> None:
        """Archive the task."""
        self.change_status(now, TaskStatus.ARCHIVED)

    def add_subtask(self, subtask: 'Task') -> None:
        """Add a subtask in memory.

        Args:
            subtask (Task): The subtask to add.

        Raises:
            InvalidStateTransition: If the subtask does not belong to this parent task.
        """
        if subtask.parent_id != self.id:
            raise InvalidStateTransition("Subtask does not belong to this parent task.")
        self._subtasks.append(subtask)

    @property
    def is_subtask(self) -> bool:
        """Check if this task is a subtask.

        Returns:
            bool: True if it has a parent, False otherwise.
        """
        return self.parent_id is not None
