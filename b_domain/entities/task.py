from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, date, datetime
from typing import Any, Optional
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from a_core import Entity, UniqueId
from a_core.exceptions import InvalidStateTransition, ValidationException
from b_domain.events.task_events import (
    TaskArchivedEvent,
    TaskCancelledEvent,
    TaskCompletedEvent,
    TaskCreatedEvent,
    TaskDeletedEvent,
    TaskEditedEvent,
    TaskPausedEvent,
    TaskReopenedEvent,
    TaskRestoredEvent,
    TaskStartedEvent,
    TaskUndoneEvent,
)
from b_domain.exceptions.recurrence import NotRecurringTaskError
from b_domain.value_objects import Description, Priority, TaskId, TaskStatus, Title
from b_domain.value_objects.dates import DueDate, build_axiom_date
from b_domain.value_objects.enums import EnergyLevel, TaskComplexity
from b_domain.value_objects.identifiers import ContextId, UserId
from b_domain.value_objects.recurrences import RecurrenceRule
from b_domain.value_objects.recurrences._serial import (
    axiom_date_from_dict,
    axiom_date_to_dict,
    rule_from_dict,
    rule_to_dict,
)

# The namespace of the occurrence IDs: never change it, or the next
# occurrences made before and after the change stop matching
_OCCURRENCE_NAMESPACE = uuid5(
    NAMESPACE_URL, "https://github.com/wesleyfralima/axiom-core#occurrence"
)


def occurrence_id(series_id: TaskId, due: DueDate) -> TaskId:
    """The ID of a series' occurrence due at ``due``, the same on every device.

    Two devices that complete the same occurrence offline both create the
    next one; with this ID it is one row, and sync merges it.
    """
    moment: datetime = due.value if due.is_floating else due.value.astimezone(UTC)
    return TaskId(
        uuid5(
            _OCCURRENCE_NAMESPACE, f"{series_id}|{due.kind.value}|{moment.isoformat()}"
        )
    )


@dataclass(kw_only=True, eq=False)
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
    due_date: DueDate | None = None
    parent_id: TaskId | None = None
    recurrence: RecurrenceRule | None = None

    context_id: ContextId | None = None

    # Free labels, lower case, no "#" (normalize_tags)
    tags: frozenset[str] = field(default_factory=frozenset)

    # Dependency graph: IDs of other tasks that block this one
    depends_on: set[TaskId] = field(default_factory=set)

    # Required energy level (GTD-style)
    # Could be an Enum: LOW, MEDIUM, HIGH
    required_energy_level: EnergyLevel = EnergyLevel.BALANCED
    complexity: TaskComplexity = TaskComplexity.MEDIUM
    estimated_duration_minutes: int = 30

    # --- Campos Comportamentais (Telemetria) ---
    success_count: int = 0
    attempt_count: int = 0
    average_duration_minutes: int = 0
    last_skipped_at: datetime | None = None
    # When it was last completed (cleared on reopen)
    completed_at: datetime | None = None
    # When it was deleted: a tombstone, restorable until it is purged
    deleted_at: datetime | None = None
    # The series a recurring task belongs to: the first occurrence's ID,
    # carried to each next one (kept when the task stops repeating)
    series_id: TaskId | None = None

    is_system_generated: bool = False

    # External calendar integration
    calendar_event_id: str | None = None
    calendar_id: str | None = None
    calendar_link: str | None = None
    last_synced_at: datetime | None = None

    # Subtasks list is not persisted directly as a column,
    # but is useful for hydrating the object in memory
    _subtasks: list["Task"] = field(default_factory=list, repr=False)

    @classmethod
    def create(
        cls,
        now: datetime,
        user_id: UserId,
        title: Title,
        description: Description = Description(""),
        priority: Priority = Priority.MEDIUM,
        required_energy_level: EnergyLevel = EnergyLevel.BALANCED,
        context_id: ContextId | None = None,
        parent_id: TaskId | None = None,
        depends_on: set[TaskId] | None = None,
        recurrence: RecurrenceRule | None = None,
        due_date: datetime | None = None,
        is_floating: bool = True,
        tz_name: str | None = None,
        complexity: TaskComplexity = TaskComplexity.MEDIUM,
        estimated_duration_minutes: int = 30,
        success_count: int = 0,
        attempt_count: int = 0,
        average_duration_minutes: int = 0,
        caused_by: UniqueId | None = None,
        series_id: TaskId | None = None,
        tags: frozenset[str] | None = None,
        task_id: TaskId | None = None,
    ) -> "Task":
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
            depends_on (Optional[Set[TaskId]], optional): List of IDs of
                tasks that this depends on.
            recurrence (Optional[RecurrenceRule], optional): Recurrence rule.
                Defaults to None.
            due_date (Optional[datetime], optional): Due date. Defaults to None.
            is_floating (bool): Task floating. Defaults to True.
            tz_name (str): Time zone. Defaults to "UTC".
            complexity (TaskComplexity): Task complexity. Defaults to "medium".
            estimated_duration_minutes (int): Task estimated duration minutes.
                Defaults to 30.
            success_count (int): Task success count. Defaults to 0.
            attempt_count (int): Task attempt count. Defaults to 0.
            average_duration_minutes (int): Task average (real) duration minutes.
                Defaults to 0.
            tags (frozenset[str] | None): Its tags, already normalized.
            task_id (TaskId | None): Its ID, when it must be a known one (the
                next occurrence, ``occurrence_id``); a new one otherwise.

        Returns:
            Task: A new Task instance.
        """

        if due_date:
            due: DueDate | None = DueDate.from_params(
                due_date,
                is_floating,
                tz_name or "UTC",
            )
        else:
            due = None

        if recurrence and due is not None:
            # Ensure recurrence aligns with the task's due date type.
            # If they differ, enforce consistency between floating/fixed rules.
            if due.is_floating and not recurrence.start_date.is_floating:
                raise ValidationException(
                    "Floating task must have a floating recurrence start_date"
                )
            if due.is_fixed and not recurrence.start_date.is_fixed:
                raise ValidationException(
                    "Fixed task must have a fixed recurrence start_date"
                )

        if depends_on is None:
            depends_on = set()

        created: Task = cls(
            id=task_id or TaskId(),
            user_id=user_id,
            title=title,
            description=description,
            status=TaskStatus.BLOCKED if depends_on else TaskStatus.PENDING,
            priority=Priority(priority),
            required_energy_level=EnergyLevel(required_energy_level),
            context_id=context_id,
            tags=tags or frozenset(),
            due_date=due,
            created_at=now,
            updated_at=now,
            parent_id=parent_id,
            depends_on=depends_on,
            recurrence=recurrence,
            complexity=complexity,
            estimated_duration_minutes=estimated_duration_minutes,
            success_count=success_count,
            attempt_count=attempt_count,
            average_duration_minutes=average_duration_minutes,
        )

        # A new series starts with its first occurrence; the next ones carry it
        if recurrence is not None:
            created.series_id = series_id or created.id

        created.add_event(
            TaskCreatedEvent(
                occurred_at=now,
                title=str(created.title),
                task_id=created.id,
                due_date=created.due_date.materialize() if created.due_date else None,
                user_id=created.user_id,
                caused_by=caused_by,
            )
        )

        return created

    @classmethod
    def create_system_task(
        cls, title: str, duration: int, reason: str, user_id: UserId
    ) -> "Task":
        """Factory for a break task that does not exist in the DB."""
        return cls(
            id=TaskId(),  # temporary ID, never persisted
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
        """Check whether the task fits the user's current energy level."""
        return self.required_energy_level <= current_energy

    def add_dependency(self, target_id: TaskId, now: datetime) -> None:
        if target_id == self.id:
            raise ValidationException("A task cannot depend on itself.")
        self.depends_on.add(target_id)
        self.change_status(now=now, new_status=TaskStatus.BLOCKED)

    def remove_dependency(self, target_id: TaskId, now: datetime) -> None:
        self.depends_on.discard(target_id)
        if not self.depends_on:
            self.change_status(now, TaskStatus.PENDING)

    @property
    def is_blocked(self) -> bool:
        """A task is blocked if any of its dependencies is still pending."""
        return len(self.depends_on) > 0

    def upcoming_occurrences(
        self,
        now: datetime,
        until: datetime,
        limit: int = 400,
        *,
        include_sub_daily: bool = False,
        at_least: int = 0,
    ) -> list[datetime]:
        """The occurrences that will follow this one, up to ``until``.

        They do not exist yet: each is created when the previous one closes.
        Only occurrences still ahead (after ``now``) are projected — a past
        one would be skipped on completion anyway — and rules that repeat
        within the day (hourly) are not projected.

        Args:
            now (datetime): The current instant (aware).
            until (datetime): The last instant to include (aware).
            limit (int): The most occurrences to return.
            include_sub_daily (bool): Project hourly rules too.
            at_least (int): Go past ``until`` if needed to return this many
                (when the series has them).

        Returns:
            list[datetime]: The occurrences, in the rule's own kind (naive
            wall-clock time for a floating task, aware for a fixed one).
        """
        if not self.recurrence or not self.due_date:
            return []
        if self.recurrence.is_sub_daily and not include_sub_daily:
            return []
        if self.recurrence.count is not None:
            # The ones left after this one
            limit = min(limit, max(self.recurrence.count - 1, 0))

        start: datetime = self._in_due_kind(now)
        end: datetime = self._in_due_kind(until)
        occurrences: list[datetime] = []
        # The rule is fed its own values; comparisons use the due date's kind
        last: datetime = self.due_date.value
        previous: datetime = self._in_due_kind(last)

        while len(occurrences) < limit:
            upcoming: datetime | None = self.recurrence.get_next_occurrence(last)
            if upcoming is None:
                break
            current: datetime = self._in_due_kind(upcoming)
            if current <= previous or (current > end and len(occurrences) >= at_least):
                break
            if current > start:
                occurrences.append(current)
            last, previous = upcoming, current

        return occurrences

    def _in_due_kind(self, moment: datetime) -> datetime:
        """A datetime as the due date compares: wall-clock time or UTC.

        Aware values are converted; a naive one is already wall-clock time
        (in the due date's zone).
        """
        assert self.due_date is not None
        zone: ZoneInfo = ZoneInfo(self.due_date.timezone or "UTC")
        if self.due_date.is_floating:
            if moment.tzinfo is None:
                return moment
            return moment.astimezone(zone).replace(tzinfo=None)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=zone)
        return moment.astimezone(UTC)

    def create_next_occurrence(
        self,
        now: datetime,
        catch_up: bool = True,
        caused_by: UniqueId | None = None,
    ) -> Optional["Task"]:
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

        if not self.recurrence or not self.due_date:
            return None

        # count is how many occurrences are left, this one included: the
        # one with count 1 is the last
        if self.recurrence.count is not None and self.recurrence.count <= 1:
            return None

        # 1. Initial reference
        next_dt: datetime | None
        last_reference: datetime | None = self.due_date.value

        # -------------------------------------------------------
        # Strategy 1: Strict mode (Financial)
        # -------------------------------------------------------
        if not catch_up:
            next_dt = self.recurrence.get_next_occurrence(
                last_occurrence=last_reference
            )
            if next_dt:
                return self._recreate_task_with_date(now, next_dt, caused_by)
            else:
                return None

        # -------------------------------------------------------
        # Strategy 2: Catch-up mode (Habit)
        # -------------------------------------------------------
        while True:
            next_dt = self.recurrence.get_next_occurrence(
                last_occurrence=last_reference
            )

            # End of recurrence (Count/Until reached)
            if not next_dt:
                return None

            # Normalize timezone for comparison
            comparison_now: datetime = self.recurrence.normalize_comparison_date(now)
            if next_dt > comparison_now:
                return self._recreate_task_with_date(now, next_dt, caused_by)

            # Otherwise, continue iterating
            last_reference = next_dt

    def _recreate_task_with_date(
        self, now: datetime, new_date: datetime, caused_by: UniqueId | None = None
    ) -> "Task":
        """Private helper to clone the task with a new due date.

        Preserves floating vs fixed semantics when reconstructing the DueDate
        and ensures recurrence continues in the new task.

        Args:
            now (datetime): Current timestamp used for task creation.
            new_date (datetime): The next occurrence date.

        Returns:
            Task: A new Task entity with updated due date.
        """

        if self.due_date is None:
            # No original due date: nothing to rebuild or replicate
            raise ValueError(
                "A task with no due date can't be recreated by _recreate_task_with_date"
            )

        # 1. Extract the semantics straight from the original date
        is_floating: bool = self.due_date.is_floating
        tz_name: str = self.due_date.timezone or "UTC"

        # 2. Rebuild the DueDate VO
        if is_floating:
            new_dd: DueDate = DueDate.floating(
                new_date.replace(tzinfo=None),
                source_tz=tz_name,
            )
        else:
            new_dd = DueDate.fixed(new_date)

        # 3. Update the recurrence cleanly
        new_rr: RecurrenceRule | None = None
        if self.recurrence is not None:
            new_rr = replace(
                self.recurrence,
                start_date=build_axiom_date(
                    dt=new_dd.value,
                    is_floating=is_floating,
                    tz=tz_name,
                ),
                # One occurrence fewer left (count includes the current one)
                count=(
                    self.recurrence.count - 1
                    if self.recurrence.count is not None
                    else None
                ),
            )

        # 4. Call Task.create with the dynamically extracted parameters.
        # Everything the user defined for the series carries over; whatever
        # belongs to this occurrence (status, counters, calendar) starts over.
        # Its ID comes from the series and the date: the same on every device.
        series_id: TaskId = self.series_id or self.id
        return Task.create(
            task_id=occurrence_id(series_id, new_dd),
            now=now,
            user_id=self.user_id,
            title=self.title,
            description=self.description,
            priority=self.priority,
            required_energy_level=self.required_energy_level,
            context_id=self.context_id,
            parent_id=self.parent_id,
            depends_on=set(self.depends_on),
            recurrence=new_rr,
            due_date=new_dd.value,
            is_floating=is_floating,
            tz_name=tz_name,
            complexity=self.complexity,
            estimated_duration_minutes=self.estimated_duration_minutes,
            average_duration_minutes=self.average_duration_minutes,
            caused_by=caused_by,
            series_id=series_id,
            tags=self.tags,
        )

    def next_occurrence_due_date(self) -> Optional["DueDate"]:
        """Return the next due date based on recurrence rules.

        Determines the next occurrence from the current due date and
        reconstructs a new DueDate object while preserving metadata
        such as floating/aware status and timezone.

        Returns:
            Optional[DueDate]: The next due date if recurrence applies,
            otherwise None.
        """

        if not self.recurrence or self.due_date is None:
            return None

        # RecurrenceRule returns a datetime (naive or aware depending on input)
        next_dt: datetime | None = self.recurrence.get_next_occurrence(
            last_occurrence=self.due_date.value,
        )

        if not next_dt:
            return None

        # Reconstruction: preserve metadata from the original DueDate
        if self.due_date.is_floating and self.due_date.timezone:
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

    def change_status(
        self, now: datetime, new_status: "TaskStatus", allow_same: bool = True
    ) -> None:
        if not self.status.can_transition_to(new_status, allow_same):
            raise InvalidStateTransition(
                f"Cannot change task status from {self.status} to {new_status}"
            )
        self.status = new_status
        self._touch(now)

    def start(self, now: datetime) -> None:
        """Start working on the task: it is in progress (a timer runs).

        The use case opens the ``TimeEntry``; the entity only changes state.

        Raises:
            InvalidStateTransition: If the task cannot start now (closed,
                waiting on other tasks, already in progress…).
        """
        if self.status == TaskStatus.IN_PROGRESS:
            raise InvalidStateTransition("The task is already in progress.")
        if self.is_blocked:
            raise InvalidStateTransition(
                "The task is waiting on other tasks: finish those first."
            )
        if self.status.is_closed:
            raise InvalidStateTransition(
                f"The task is {self.status}: reopen it to work on it again."
            )
        previous: dict[str, Any] = self.snapshot()
        if self.status in (TaskStatus.SOMEDAY, TaskStatus.REOPENED):
            # Neither goes straight to "in progress" in the state machine
            self.change_status(now, TaskStatus.PENDING)
        self.change_status(now, TaskStatus.IN_PROGRESS, allow_same=False)
        self.add_event(
            TaskStartedEvent(
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                context_id=self.context_id,
                previous=previous,
            )
        )

    def pause(
        self, now: datetime, minutes: int, caused_by: UniqueId | None = None
    ) -> None:
        """Stop working on the task for now (its timer stops).

        Args:
            now (datetime): When.
            minutes (int): How long the session that ends lasted.
            caused_by (UniqueId | None): The start of another task that
                paused this one (undoing that start resumes this one).

        Raises:
            InvalidStateTransition: If the task is not in progress.
        """
        if self.status != TaskStatus.IN_PROGRESS:
            raise InvalidStateTransition(
                f"The task is not in progress (it is {self.status})."
            )
        previous: dict[str, Any] = self.snapshot()
        self.change_status(now, TaskStatus.PAUSED, allow_same=False)
        self.add_event(
            TaskPausedEvent(
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                minutes=minutes,
                previous=previous,
                caused_by=caused_by,
            )
        )

    def record_duration(self, minutes: int) -> None:
        """Keep the measured time of a completion: the running average (which
        becomes the next occurrence's estimate) and the count."""
        if minutes <= 0:
            return
        total: int = self.average_duration_minutes * self.success_count + minutes
        self.success_count += 1
        self.average_duration_minutes = round(total / self.success_count)

    def change_recurrence(self, now: datetime, rule: RecurrenceRule | None) -> None:
        """Repeat the task by another rule, or stop repeating it.

        The due date stays: this occurrence keeps it, and the occurrences
        after it follow the new rule.

        Raises:
            ValidationException: If the rule is floating and the due date is
                fixed, or the other way around.
        """
        if (
            rule is not None
            and self.due_date is not None
            and rule.start_date.is_floating != self.due_date.is_floating
        ):
            raise ValidationException(
                "The rule and the due date must both be fixed or both floating."
            )
        self.recurrence = rule
        if rule is not None and self.series_id is None:
            self.series_id = self.id
        self._touch(now)

    def set_tags(self, now: datetime, tags: frozenset[str]) -> None:
        """Replace the task's tags (already normalized: ``normalize_tags``)."""
        self.tags = frozenset(tags)
        self._touch(now)

    def use_business_days(self, is_business_day: Callable[[date], bool]) -> None:
        """Count the rule's business days with the user's calendar.

        Not a change to the task: the rule stays equal (the calendar is not
        part of it), nothing is recorded and ``updated_at`` stays.
        """
        if self.recurrence is not None:
            self.recurrence = self.recurrence.with_business_days(is_business_day)

    def move_to_context(self, now: datetime, context_id: ContextId | None) -> None:
        """Put the task in a context, or in none."""
        self.context_id = context_id
        self._touch(now)

    def update_energy(self, now: datetime, level: EnergyLevel) -> None:
        """Change the energy the task asks for."""
        self.required_energy_level = level
        self._touch(now)

    def update_estimate(self, now: datetime, minutes: int) -> None:
        """Change how long the task is expected to take.

        Raises:
            ValidationException: If it is not 1 minute or more.
        """
        if minutes < 1:
            raise ValidationException("An estimate is 1 minute or more.")
        self.estimated_duration_minutes = minutes
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
        new_dt: datetime | None,
        is_floating: bool = True,
        tz_name: str | None = None,
    ) -> None:
        """Replace the due date, built the same way ``create`` builds it.

        Args:
            now: Timestamp for ``updated_at``.
            new_dt: The new raw datetime, or None to remove the due date.
            is_floating: Whether the new date is floating (wall-clock time) or
                fixed (an instant).
            tz_name: IANA time zone of ``new_dt``. Defaults to the current due
                date's time zone, then to UTC. A naive ``new_dt`` for a fixed
                date is read in this zone.
        """

        if new_dt is None:
            self.due_date = None
            self._touch(now)
            return

        current_tz: str | None = self.due_date.timezone if self.due_date else None
        effective_tz: str = tz_name or current_tz or "UTC"

        self.due_date = DueDate.from_params(new_dt, is_floating, effective_tz)
        self._touch(now)

    def mark_as_done(self, now: datetime, actual_minutes: int = 0) -> None:
        """Mark the task as completed."""
        previous: dict[str, Any] = self.snapshot()
        self.change_status(now, TaskStatus.DONE, allow_same=False)
        self.completed_at = now
        self.add_event(
            TaskCompletedEvent(
                previous=previous,
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                estimated_minutes=self.estimated_duration_minutes,
                actual_minutes=actual_minutes,
                energy_level_used=self.required_energy_level,
                task_complexity=self.complexity,
            )
        )

    def mark_as_cancelled(self, now: datetime, end_series: bool = False) -> None:
        """Cancel the task: the user decided not to do it.

        For a recurring task, cancelling skips only this occurrence — the
        ``TaskCancelledEvent`` makes the next one — unless ``end_series`` says
        the whole series ends here.

        Args:
            now (datetime): Current time.
            end_series (bool): End the series instead of skipping one
                occurrence. Only for a recurring task.

        Raises:
            NotRecurringTaskError: If ``end_series`` is asked of a task that
                does not repeat.
            InvalidStateTransition: If the task is already closed.
        """
        if end_series and self.recurrence is None:
            raise NotRecurringTaskError()
        if self.status.is_closed:
            raise InvalidStateTransition(f"The task is already {self.status}.")
        previous: dict[str, Any] = self.snapshot()
        self.change_status(now, TaskStatus.CANCELLED, allow_same=False)
        self.add_event(
            TaskCancelledEvent(
                previous=previous,
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                end_series=end_series,
            )
        )

    def reopen(self, now: datetime) -> None:
        """Bring a done or cancelled task back to the open ones.

        A recurring occurrence already handed its series on when it closed
        (the next occurrence exists, or the series ended there), so the
        reopened one becomes a one-off task: closing it again must not start
        a second copy of the series.

        Raises:
            InvalidStateTransition: If the task is not done or cancelled.
        """
        if self.status is TaskStatus.ARCHIVED:
            raise InvalidStateTransition("An archived task cannot be reopened.")
        if not self.status.is_closed:
            raise InvalidStateTransition(
                "The task is already open: only a done or cancelled task can be "
                "reopened."
            )
        previous: dict[str, Any] = self.snapshot()
        self.change_status(now, TaskStatus.REOPENED, allow_same=False)
        self.recurrence = None
        self.completed_at = None
        self.add_event(
            TaskReopenedEvent(
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                previous=previous,
            )
        )

    def archive(self, now: datetime) -> None:
        """Put a closed task away for good (no way back).

        Raises:
            InvalidStateTransition: If the task is not done or cancelled.
        """
        if self.status is TaskStatus.ARCHIVED:
            raise InvalidStateTransition("The task is already archived.")
        if not self.status.is_closed:
            raise InvalidStateTransition(
                "The task is still open: only a done or cancelled task can be archived."
            )
        previous: dict[str, Any] = self.snapshot()
        self.change_status(now, TaskStatus.ARCHIVED, allow_same=False)
        self.add_event(
            TaskArchivedEvent(
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                previous=previous,
            )
        )

    def record_edit(
        self,
        now: datetime,
        changes: dict[str, tuple[str | None, str | None]],
        previous: dict[str, Any] | None = None,
    ) -> None:
        """Record what an edit changed, for the history.

        The edit itself is made by the other methods (``rename``,
        ``update_due_date``…); the use case knows which of them it called and
        says what changed, as text, once per edit.

        Args:
            now (datetime): When the edit happened.
            changes (dict): Field → ``(before, after)``; nothing is recorded
                when it is empty.
            previous (dict | None): ``snapshot()`` taken before the edit, so
                it can be undone.
        """
        if not changes:
            return
        self.add_event(
            TaskEditedEvent(
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                changes={name: [old, new] for name, (old, new) in changes.items()},
                previous=previous,
            )
        )

    def mark_deleted(self, now: datetime) -> None:
        """Delete the task: a tombstone, restorable until it is purged.

        Raises:
            InvalidStateTransition: If it is already deleted.
        """
        if self.deleted_at is not None:
            raise InvalidStateTransition("The task is already deleted.")
        previous: dict[str, Any] = self.snapshot()
        self.deleted_at = now
        self._touch(now)
        self.add_event(
            TaskDeletedEvent(
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                title=str(self.title),
                previous=previous,
            )
        )

    def restore(self, now: datetime) -> None:
        """Bring a deleted task back, as it was.

        Raises:
            InvalidStateTransition: If it is not deleted.
        """
        if self.deleted_at is None:
            raise InvalidStateTransition("The task is not deleted.")
        self.deleted_at = None
        self._touch(now)
        self.add_event(
            TaskRestoredEvent(occurred_at=now, task_id=self.id, user_id=self.user_id)
        )

    def come_back_as(self, fresh: "Task") -> None:
        """A deleted occurrence comes back, made again as ``fresh``.

        The next occurrence's ID is known ahead (``occurrence_id``): an undo
        of a completion takes it away, and completing again makes the same
        row. It takes all of ``fresh`` — its fields and its events (its
        creation) — so the history and an undo see it as new.

        Raises:
            InvalidStateTransition: If it is not deleted.
            ValidationException: If ``fresh`` is another task.
        """
        if self.deleted_at is None:
            raise InvalidStateTransition("The task is not deleted.")
        if fresh.id != self.id:
            raise ValidationException("Only the same task can come back.")
        for name in (f.name for f in fields(self)):
            if name != "_domain_events":
                setattr(self, name, getattr(fresh, name))
        for event in fresh.pull_events():
            self.add_event(event)

    def snapshot(self) -> dict[str, Any]:
        """What the user can change, as JSON-safe data — to undo a change."""
        return {
            "status": str(self.status),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "title": str(self.title),
            "description": str(self.description),
            "priority": self.priority.value,
            "energy": self.required_energy_level.value,
            "context_id": str(self.context_id) if self.context_id else None,
            "due": axiom_date_to_dict(self.due_date) if self.due_date else None,
            "recurrence": rule_to_dict(self.recurrence) if self.recurrence else None,
            "series_id": str(self.series_id) if self.series_id else None,
            "estimate": self.estimated_duration_minutes,
            "tags": sorted(self.tags),
        }

    def revert_to(
        self,
        now: datetime,
        snapshot: dict[str, Any] | None,
        undoes: UniqueId,
        action: str,
        running: bool = False,
    ) -> None:
        """Undo a change: the task goes back to ``snapshot``.

        Undo is not a transition: the task simply is what it was (the state
        machine does not apply). Without a snapshot — undoing its creation —
        the task is taken away (a tombstone, like a delete).

        Args:
            now (datetime): When the undo happens.
            snapshot (dict | None): ``snapshot()`` from before the change.
            undoes (UniqueId): The history entry undone (its event's id).
            action (str): What is undone ("completed", "edited"…).
            running (bool): Its timer runs again (undoing a pause): "in
                progress" stays so.
        """
        if snapshot is None:
            self.deleted_at = now
        else:
            status: TaskStatus = TaskStatus(snapshot["status"])
            # Undo never starts a timer: "in progress" comes back paused
            self.status = (
                TaskStatus.PAUSED
                if status == TaskStatus.IN_PROGRESS and not running
                else status
            )
            self.completed_at = _instant(snapshot.get("completed_at"))
            self.deleted_at = _instant(snapshot.get("deleted_at"))
            self.title = Title(snapshot["title"])
            self.description = Description(snapshot["description"])
            self.priority = Priority(snapshot["priority"])
            self.required_energy_level = EnergyLevel(snapshot["energy"])
            self.context_id = (
                ContextId.from_string(snapshot["context_id"])
                if snapshot.get("context_id")
                else None
            )
            self.due_date = (
                axiom_date_from_dict(snapshot["due"], DueDate)
                if snapshot.get("due")
                else None
            )
            self.recurrence = (
                rule_from_dict(snapshot["recurrence"])
                if snapshot.get("recurrence")
                else None
            )
            if "estimate" in snapshot:
                self.estimated_duration_minutes = int(snapshot["estimate"])
            if "tags" in snapshot:
                self.tags = frozenset(snapshot["tags"])
            if "series_id" in snapshot:
                self.series_id = (
                    TaskId.from_string(snapshot["series_id"])
                    if snapshot["series_id"]
                    else None
                )
        self._touch(now)
        self.add_event(
            TaskUndoneEvent(
                occurred_at=now,
                task_id=self.id,
                user_id=self.user_id,
                undoes=undoes,
                action=action,
            )
        )

    def add_subtask(self, subtask: "Task") -> None:
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

    def needs_calendar_sync(self) -> bool:
        """Checks if the task has local changes not yet sent to the calendar."""
        if not self.calendar_event_id:
            return True
        if not self.last_synced_at:
            return True
        return self.updated_at > self.last_synced_at

    def mark_as_synced(
        self,
        now: datetime,
        external_id: str,
        calendar_id: str,
        link: str | None = None,
    ) -> None:
        """Mark this task as synced with an external calendar.

        This method should be called by the Service after a successful
        synchronization with the CalendarProvider.

        Args:
            now (datetime): The current time.
            external_id (str): The identifier of the event in the external calendar.
            calendar_id (str): The identifier of the calendar in the external calendar.
            link (str, optional): The link to the external calendar event.
                Defaults to None.
        """
        self.calendar_event_id = external_id
        self.calendar_id = calendar_id
        self.calendar_link = link
        self.last_synced_at = now
        self._touch(now)

    def mark_as_unsynced(self, now: datetime) -> None:
        """Remove the link between this task and the external calendar.

        Useful if the event was deleted externally or if the user disables
        synchronization.
        """
        self.calendar_event_id = None
        self._touch(now)

    @property
    def has_calendar_event(self) -> bool:
        """Check whether this task is linked to an external calendar event.

        Returns:
            bool: True if the task has an associated external calendar event,
            False otherwise.
        """
        return self.calendar_event_id is not None


def _instant(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
